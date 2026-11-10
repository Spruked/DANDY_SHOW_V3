"""Generated dialogue stays separate from the active script until acceptance."""
import hashlib
import json
from datetime import datetime, timezone
from uuid import uuid4

from ...core.safety import contained_path, validate_id, file_lock, atomic_json
from ..storage import episode_store as store


def script_fingerprint(episode_id):
    return hashlib.sha256(json.dumps(store.load_script(episode_id).get('script', []),
                                    sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def saved_context(episode_id, version_id=None):
    folder = store.episode_dir(episode_id) / 'context_packages'
    if version_id is not None and (not isinstance(version_id, str) or not version_id.startswith('context_')):
        raise ValueError('Select a saved context version')
    path = contained_path(folder, validate_id(version_id) + '.json') if version_id else folder / 'latest.json'
    if not path.is_file():
        raise ValueError('Build and review a context package before generating')
    package = json.loads(path.read_text(encoding='utf-8'))
    if package.get('episode_id') != episode_id:
        raise ValueError('Context package belongs to another episode')
    characters = package.get('show_bible', [])
    if len(characters) != 2 or {c.get('speaker') for c in characters} != {'phil', 'jim'} or any(not c.get('persona') for c in characters):
        raise ValueError('Rebuild context with both complete canonical personas before generating')
    if not package.get('sources'):
        raise ValueError('Saved context has no source evidence')
    return package


def save_draft(episode_id, package, script, source_hash, sample=False):
    draft_id = 'draft_' + uuid4().hex
    warnings = []
    import re
    for index, line in enumerate(script, 1):
        name = line['speaker']
        if re.match(rf'^(?:you know,\s*|hey,?\s*|listen,?\s*)?{name}[,!?:]', line['text'], re.I):
            warnings.append(f'Turn {index}: {name} appears to address himself; review character identity')
    draft = {'draft_id': draft_id, 'episode_id': episode_id, 'status': 'sample' if sample else 'draft',
             'sample': sample, 'context_version_id': package['version_id'],
             'context_sha256': hashlib.sha256(json.dumps(package, sort_keys=True, ensure_ascii=False).encode()).hexdigest(),
             'source_script_hash': source_hash, 'created_at': datetime.now(timezone.utc).isoformat(),
             'script': script, 'word_count': sum(len(line['text'].split()) for line in script),
             'script_sha256': hashlib.sha256(json.dumps(script, sort_keys=True, ensure_ascii=False).encode()).hexdigest(),
             'review_warnings': warnings, 'writer_engine': 'nemotron'}
    path = store.episode_dir(episode_id) / 'generated_drafts' / f'{draft_id}.json'
    atomic_json(path, draft)
    from ..storage.vault_store import preserve_files
    preserve_files([path], 'generated dialogue draft saved; active script unchanged')
    return draft


def latest_draft(episode_id):
    paths = sorted((store.episode_dir(episode_id) / 'generated_drafts').glob('draft_*.json'),
                   key=lambda path: path.stat().st_mtime_ns, reverse=True)
    return json.loads(paths[0].read_text(encoding='utf-8')) if paths else None


def accept_draft(episode_id, draft_id):
    folder = store.episode_dir(episode_id)
    path = contained_path(folder / 'generated_drafts', validate_id(draft_id) + '.json')
    if not path.is_file():
        raise ValueError('Generated draft was not found')
    draft = json.loads(path.read_text(encoding='utf-8'))
    if draft.get('episode_id') != episode_id or hashlib.sha256(json.dumps(draft.get('script'), sort_keys=True, ensure_ascii=False).encode()).hexdigest() != draft.get('script_sha256'):
        raise ValueError('Generated draft integrity check failed')
    if draft.get('sample'):
        raise ValueError('Diagnostic samples cannot replace an episode script')
    with file_lock(folder / 'episode-update'):
        if draft.get('accepted_version_id'):
            return draft
        if script_fingerprint(episode_id) != draft['source_script_hash']:
            raise ValueError('Episode script changed after generation; review the draft before importing it manually')
        result = store._save_canonical_snapshot(episode_id, draft['script'], project_active=True, save_legacy_version=True)
        draft.update(status='accepted', accepted_version_id=result['version_id'], accepted_at=datetime.now(timezone.utc).isoformat())
        atomic_json(path, draft)
    return draft
