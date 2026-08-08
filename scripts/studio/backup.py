"""
backup.py — Dandy Studio incremental backup.

Backs up all configs, episode metadata (no audio), social templates,
and jingles index into archive/backups/YYYYMMDD_HHMMSS.zip

Usage:
    python scripts/studio/backup.py
    python scripts/studio/backup.py --label "before-social-rebuild"
"""
from __future__ import annotations

import argparse
import json
import sys
import zipfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKUP_DIR = ROOT / "archive" / "backups"

# What gets backed up — paths relative to ROOT
INCLUDE_GLOBS = [
    "config/**/*.json",
    "config/**/*.py",
    "episodes/**/script.json",
    "episodes/**/script_versions/*.json",
    "episodes/**/config.json",
    "episodes/**/ads/*.json",
    "episodes/**/slideshow.json",
    "episodes/**/ad_cards.json",
    "episodes/**/status.json",
    "episodes/**/production_metadata.json",
    "episodes/.drafts/**/*.json",
    "social/templates/**",
    "social/ad_cards.json",
    "audio/jingles/**",
    "docs/**/*.md",
    "CHANGELOG.md",
    ".gitignore",
    "requirements.txt",
]

# Never include these even if matched above
EXCLUDE_SUFFIXES = {".mp3", ".mp4", ".wav", ".pt", ".png", ".jpg", ".jpeg", ".gif", ".zip"}


def collect_files() -> list[Path]:
    files = []
    for glob in INCLUDE_GLOBS:
        for p in ROOT.glob(glob):
            if p.is_file() and p.suffix.lower() not in EXCLUDE_SUFFIXES:
                files.append(p)
    return sorted(set(files))


def run(label: str = "") -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    slug = f"_{label}" if label else ""
    zip_path = BACKUP_DIR / f"backup_{stamp}{slug}.zip"

    files = collect_files()
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in files:
            zf.write(f, f.relative_to(ROOT))
        # Write manifest
        manifest = {
            "timestamp": stamp,
            "label": label,
            "file_count": len(files),
            "files": [str(f.relative_to(ROOT)) for f in files],
        }
        zf.writestr("_backup_manifest.json", json.dumps(manifest, indent=2))

    size_kb = zip_path.stat().st_size // 1024
    print(f"Backup created: {zip_path.name}  ({len(files)} files, {size_kb} KB)")
    return zip_path


def prune_old(keep: int = 20) -> None:
    backups = sorted(BACKUP_DIR.glob("backup_*.zip"))
    if len(backups) > keep:
        for old in backups[:-keep]:
            old.unlink()
            print(f"Pruned old backup: {old.name}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Dandy Studio backup")
    parser.add_argument("--label", default="", help="Optional label for this backup")
    parser.add_argument("--keep", type=int, default=20, help="Max backups to keep (default 20)")
    args = parser.parse_args()

    try:
        run(args.label)
        prune_old(args.keep)
    except Exception as e:
        print(f"Backup failed: {e}", file=sys.stderr)
        sys.exit(1)
