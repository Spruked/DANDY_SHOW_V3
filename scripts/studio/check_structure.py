"""
check_structure.py — Dandy Studio folder discipline validator.

Catches files in wrong places before they cause confusion.
Run manually or automatically via the pre-commit hook.

Usage:
    python scripts/studio/check_structure.py
    python scripts/studio/check_structure.py --fix   (moves known-bad files)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# Files that should never sit at project root
ROOT_DISALLOWED_EXTENSIONS = {".jsx", ".tsx", ".css", ".html"}
ROOT_DISALLOWED_NAMES = {
    "social_visual.py", "social_slideshow.py", "social_adcards.py",
    "slideshow_renderer.py", "social-tab.css",
}

# Required directories — must exist
REQUIRED_DIRS = [
    "backend/app/api",
    "backend/app/services/social",
    "backend/app/schemas",
    "frontend/src/components",
    "frontend/src/styles",
    "config",
    "episodes",
    "audio/jingles",
    "social/templates",
    "social/renders",
    "archive/backups",
    "archive/restore_points",
    "scripts/studio",
    "docs",
    "logs",
    "staging",
]

# Files that must exist
REQUIRED_FILES = [
    "config/config.json",
    "config/voices.json",
    "requirements.txt",
    ".gitignore",
    "CHANGELOG.md",
    "backend/app/main.py",
    "frontend/src/App.jsx",
    "frontend/src/main.jsx",
]

# Episode subfolder rules — every episode dir must have these
EPISODE_REQUIRED = ["config.json", "script.json", "status.json"]


def check_root_loose(errors: list, warnings: list) -> None:
    for f in ROOT.iterdir():
        if not f.is_file():
            continue
        if f.suffix.lower() in ROOT_DISALLOWED_EXTENSIONS:
            errors.append(f"Loose file at root: {f.name}  (should be in frontend/src/components/ or similar)")
        if f.name in ROOT_DISALLOWED_NAMES:
            errors.append(f"Misplaced backend file at root: {f.name}")


def check_required_dirs(errors: list, warnings: list) -> None:
    for d in REQUIRED_DIRS:
        if not (ROOT / d).exists():
            warnings.append(f"Missing expected directory: {d}")


def check_required_files(errors: list, warnings: list) -> None:
    for f in REQUIRED_FILES:
        if not (ROOT / f).exists():
            warnings.append(f"Missing expected file: {f}")


def check_episodes(errors: list, warnings: list) -> None:
    episodes_root = ROOT / "episodes"
    if not episodes_root.exists():
        return
    for ep_dir in episodes_root.iterdir():
        if not ep_dir.is_dir() or ep_dir.name.startswith("."):
            continue
        for req in EPISODE_REQUIRED:
            if not (ep_dir / req).exists():
                warnings.append(f"Episode {ep_dir.name} missing: {req}")


def check_audio_jingles(errors: list, warnings: list) -> None:
    jingles_dir = ROOT / "audio" / "jingles"
    if not jingles_dir.exists():
        return
    # Warn about large audio files in wrong place
    for f in (ROOT / "audio").rglob("*.mp3"):
        if "jingles" not in str(f) and "sfx" not in str(f) and "ads" not in str(f):
            warnings.append(f"Audio file outside expected subfolder: {f.relative_to(ROOT)}")


def run(fix: bool = False) -> bool:
    errors: list[str] = []
    warnings: list[str] = []

    check_root_loose(errors, warnings)
    check_required_dirs(errors, warnings)
    check_required_files(errors, warnings)
    check_episodes(errors, warnings)
    check_audio_jingles(errors, warnings)

    if warnings:
        print("WARNINGS:")
        for w in warnings:
            print(f"  WARN  {w}")

    if errors:
        print("ERRORS (must fix):")
        for e in errors:
            print(f"  ERR   {e}")
        return False

    if not errors and not warnings:
        print("Structure check passed.")

    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Dandy Studio structure checker")
    parser.add_argument("--fix", action="store_true", help="Attempt to auto-fix known issues")
    args = parser.parse_args()

    ok = run(args.fix)
    sys.exit(0 if ok else 1)
