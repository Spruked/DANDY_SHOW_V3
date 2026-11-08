"""Content-addressed local artifacts with AIMS append-only snapshot receipts.

Working files remain in place. AIMS is the receipt authority; blobs are evidence,
and status.json is a rebuildable UI projection. No cognitive pruning is used.
"""
import hashlib
import json
import os
import shutil
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path

from ...core.paths import PROJECT_ROOT
from ...core.safety import atomic_json, contained_path, file_lock


def digest(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(chunk)
    return value.hexdigest()


class DandyVault:
    def __init__(self, project_root=PROJECT_ROOT, config=None):
        self.project = Path(project_root).resolve()
        self.config = config or json.loads((self.project / 'config/vault.json').read_text(encoding='utf-8'))
        self.root = contained_path(self.project, self.config['vault_root'])
        self.aims = contained_path(self.project, self.config['aims_store'])
        if self.root == self.project or self.aims == self.project or self.root == self.aims:
            raise ValueError('Vault and AIMS storage require separate dedicated directories')
        self.state_path = self.root / 'status.json'

    def _ledger(self):
        from memory_core.long_term import LongTermMemory
        return LongTermMemory(self.aims, matrix_id='dandy_artifacts', security_mode='visual')

    def _excluded(self, path):
        path = Path(path)
        relative = path.relative_to(self.project)
        names = relative.parts
        return (path.is_symlink() or path.resolve().is_relative_to(self.root)
                or path.resolve().is_relative_to(self.aims)
                or not path.resolve().is_relative_to(self.project)
                or any(n in {'.git', 'node_modules', '__pycache__', '.venv', 'build', 'dist'}
                       or n.startswith('.venv-') or n.endswith('.egg-info') for n in names)
                or path.suffix in {'.lock', '.tmp', '.pyc', '.key', '.ledger', '.sqlite'}
                or path.name.startswith('.env') or path.name.endswith('.keys.json'))

    def project_files(self):
        files = set()
        for name in self.config['project_paths']:
            path = contained_path(self.project, name)
            if path.is_file() and not self._excluded(path):
                files.add(path)
            elif path.is_dir():
                for current, directories, names in os.walk(path, followlinks=False):
                    base = Path(current)
                    directories[:] = [name for name in directories if not self._excluded(base / name)]
                    for name in names:
                        item = base / name
                        if not self._excluded(item):
                            files.add(item)
        return sorted(files)

    def _blob(self, source):
        """Copy/hash a stable input and never overwrite an existing evidence blob."""
        folder = self.root / 'tmp'
        folder.mkdir(parents=True, exist_ok=True)
        before = source.stat()
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=folder, delete=False) as output, source.open('rb') as stream:
                temporary = Path(output.name)
                value = hashlib.sha256()
                for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                    value.update(chunk); output.write(chunk)
                output.flush(); os.fsync(output.fileno())
            after = source.stat()
            if (before.st_mtime_ns, before.st_size, before.st_ino) != (after.st_mtime_ns, after.st_size, after.st_ino):
                raise RuntimeError(f'File changed while preserving it; retry: {source.name}')
            sha = value.hexdigest()
            destination = self.root / 'objects' / sha[:2] / sha
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists():
                if digest(destination) != sha:
                    raise RuntimeError(f'Vault object integrity failure: {sha}')
            else:
                os.replace(temporary, destination)
            return {'sha256': sha, 'size_bytes': after.st_size}
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def capture(self, paths=None, reason='automatic project snapshot'):
        from memory_core.long_term import EntryType
        with file_lock(self.root / 'capture', timeout=30):
            atomic_json(self.state_path, {**self.status(), 'status': 'snapshotting'})
            files = self.project_files() if paths is None else sorted(set(Path(p).resolve() for p in paths))
            manifest = {}
            for path in files:
                if not path.is_relative_to(self.project) or self._excluded(path):
                    raise ValueError('Requested artifact is outside the permitted project scope')
                manifest[path.relative_to(self.project).as_posix()] = self._blob(path)
            ledger = self._ledger()  # verifies persisted ledger before committing a receipt
            payload = {'schema_version': 1, 'event': 'dandy_snapshot', 'files': manifest,
                       'scope': 'project' if paths is None else 'artifacts'}
            identity = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
            existing = next((e for e in reversed(ledger.entries) if e.content.get('snapshot_hash') == identity), None)
            entry = existing or ledger.write_entry(EntryType.SYSTEM_EVENT,
                         {**payload, 'snapshot_hash': identity, 'reason': reason}, writer_id='dandy_studio')
            receipt = {'snapshot_id': entry.entry_id, 'snapshot_hash': identity, 'entry_hash': entry.hash,
                       'file_count': len(manifest), 'size_bytes': sum(f['size_bytes'] for f in manifest.values()),
                       'security_mode': ledger.security_mode, 'scope': payload['scope']}
            prior = self.status()
            atomic_json(self.state_path, {**prior, 'status': 'protected', 'last_error': None,
                        'last_snapshot_at': datetime.now(timezone.utc).isoformat(), 'latest_receipt': receipt,
                        **({'latest_project_receipt': receipt} if paths is None else {})})
            return receipt

    def status(self):
        if self.state_path.exists():
            return json.loads(self.state_path.read_text(encoding='utf-8'))
        return {'status': 'pending', 'last_error': None}

    def record_error(self, error):
        atomic_json(self.state_path, {**self.status(), 'status': 'error', 'last_error': str(error)})

    def verify(self):
        """Read/replay the ledger and verify every referenced historical object."""
        with file_lock(self.root / 'capture', timeout=30):
            ledger = self._ledger()
            objects = {record['sha256'] for e in ledger.entries
                       if e.content.get('event') == 'dandy_snapshot' for record in e.content['files'].values()}
            problems = []
            for sha in sorted(objects):
                path = self.root / 'objects' / sha[:2] / sha
                if not path.exists() or digest(path) != sha:
                    problems.append(sha)
            result = {'valid': not problems, 'ledger_entries': ledger.total_entries,
                      'objects_checked': len(objects), 'damaged_or_missing_objects': problems,
                      'security_mode': ledger.security_mode}
            atomic_json(self.state_path, {**self.status(), 'last_verification': result,
                        'verified_at': datetime.now(timezone.utc).isoformat(),
                        **({'status': 'error', 'last_error': 'Vault object verification failed'} if problems else {})})
            return result

    def restore(self, snapshot_id, destination):
        destination = Path(destination).resolve()
        if destination.exists():
            raise ValueError('Restore destination must be a new directory; existing files are never overwritten')
        with file_lock(self.root / 'capture', timeout=30):
            entry = self._ledger().read_entry(entry_id=snapshot_id)
            if entry is None or entry.content.get('event') != 'dandy_snapshot':
                raise ValueError('Snapshot not found')
            restored = 0
            for name, record in entry.content['files'].items():
                target = contained_path(destination, name)
                sha = record['sha256']
                blob = self.root / 'objects' / sha[:2] / sha
                if not blob.exists() or digest(blob) != sha:
                    raise RuntimeError(f'Cannot restore damaged vault object: {sha}')
                target.parent.mkdir(parents=True, exist_ok=True)
                with target.open('xb') as output, blob.open('rb') as source:
                    shutil.copyfileobj(source, output)
                restored += 1
            return {'destination': str(destination), 'restored_files': restored, 'snapshot_id': snapshot_id}


def preserve_files(paths, reason):
    """Immediate write-through for significant artifacts; temp test storage is isolated."""
    paths = [Path(p).resolve() for p in paths]
    if not paths or any(not p.is_relative_to(PROJECT_ROOT.resolve()) for p in paths):
        return None
    vault = DandyVault()
    if not vault.config.get('enabled', True):
        return None
    try:
        return vault.capture(paths, reason)
    except Exception as exc:
        vault.record_error(exc)
        raise RuntimeError(f'Working files retained, but vault preservation failed: {exc}') from exc


class VaultWatcher:
    def __init__(self, vault):
        self.vault = vault
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self.run, name='dandy-vault', daemon=True)

    def start(self):
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        self.thread.join(timeout=3)

    def run(self):
        previous = None
        while not self.stop_event.is_set():
            try:
                files = self.vault.project_files()
                signature = [(str(p), p.stat().st_size, p.stat().st_mtime_ns) for p in files]
                if signature != previous:
                    self.vault.capture(reason='automatic project snapshot')
                    previous = signature
            except Exception as exc:
                self.vault.record_error(exc)
            self.stop_event.wait(max(5, self.vault.config.get('sync_interval_seconds', 30)))
