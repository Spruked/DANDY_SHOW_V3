"""
backup.py — Dandy Studio incremental backup.

Backs up configs, complete episodes, media assets, audio and social outputs into archive/backups/YYYYMMDD_HHMMSS.zip

Usage:
    python scripts/studio/backup.py
    python scripts/studio/backup.py --label "before-social-rebuild"
"""
from __future__ import annotations

import argparse
import json
import re
import os
import sys
import zipfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKUP_DIR = ROOT / "archive" / "backups"

# What gets backed up — paths relative to ROOT
INCLUDE_GLOBS = ["config/**/*", "episodes/**/*", "social/**/*", "audio/**/*", "assets/**/*",
                 "introclip*.mp3", "docs/**/*.md", "requirements*.txt", "frontend/package*.json"]
EXCLUDE_SUFFIXES = {".lock", ".tmp"}


def collect_files() -> list[Path]:
    files = []
    for glob in INCLUDE_GLOBS:
        for p in ROOT.glob(glob):
            if p.is_file() and p.suffix.lower() not in EXCLUDE_SUFFIXES:
                files.append(p)
    return sorted(set(files))


def run(label: str = "") -> Path:
    if label and not re.fullmatch(r"[A-Za-z0-9_-]+", label):
        raise ValueError("Invalid backup label")
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    slug = f"_{label}" if label else ""
    zip_path = BACKUP_DIR / f"backup_{stamp}{slug}.zip"

    files = collect_files()
    with zipfile.ZipFile(str(zip_path) + ".tmp", "w", zipfile.ZIP_DEFLATED) as zf:
        for f in files:
            if f.is_symlink() or not f.resolve().is_relative_to(ROOT.resolve()):
                raise ValueError("Backup source escapes project")
            zf.write(f, f.relative_to(ROOT))
        # Write manifest
        manifest = {
            "timestamp": stamp,
            "label": label,
            "file_count": len(files),
            "files": [str(f.relative_to(ROOT)) for f in files],
        }
        zf.writestr("_backup_manifest.json", json.dumps(manifest, indent=2))

    with zipfile.ZipFile(str(zip_path) + ".tmp") as zf:
        if zf.testzip():
            raise RuntimeError("Backup integrity check failed")
    os.replace(str(zip_path) + ".tmp", zip_path)
    size_kb = zip_path.stat().st_size // 1024
    print(f"Backup created: {zip_path.name}  ({len(files)} files, {size_kb} KB)")
    return zip_path


def restore_archive(archive: Path, destination: Path) -> None:
    """Restore to a NEW empty directory for validation; never overwrite the studio."""
    destination = destination.resolve()
    if destination.exists() and any(destination.iterdir()):
        raise ValueError("Restore destination must be empty")
    with zipfile.ZipFile(archive) as zf:
        if zf.testzip():
            raise ValueError("Backup integrity check failed")
        targets = []
        for member in zf.infolist():
            relative = member.filename.replace("\\", "/")
            target = (destination / relative).resolve()
            if not target.is_relative_to(destination) or ":" in relative:
                raise ValueError("Unsafe archive path")
            if (member.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError("Archive symlinks are not supported")
            targets.append((member, target))
        for member, target in targets:
            if member.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(member) as source, target.open("wb") as out:
                    import shutil
                    shutil.copyfileobj(source, out)


def prune_old(keep: int = 20) -> None:
    if keep < 1:
        raise ValueError("keep must be at least 1")
    backups = sorted(BACKUP_DIR.glob("backup_*.zip"))
    if len(backups) > keep:
        for old in backups[:-keep]:
            old.unlink()
            print(f"Pruned old backup: {old.name}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Dandy Studio backup")
    parser.add_argument("--restore", type=Path, help="Archive to restore into a new empty directory")
    parser.add_argument("--destination", type=Path)
    parser.add_argument("--label", default="", help="Optional label for this backup")
    parser.add_argument("--keep", type=int, default=20, help="Max backups to keep (default 20)")
    args = parser.parse_args()

    try:
        if args.restore:
            if not args.destination:
                raise ValueError("--destination is required for restore")
            restore_archive(args.restore, args.destination)
        else:
            if args.keep < 1:
                raise ValueError("keep must be at least 1")
            run(args.label)
            prune_old(args.keep)
    except Exception as e:
        print(f"Backup failed: {e}", file=sys.stderr)
        sys.exit(1)
