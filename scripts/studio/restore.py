"""
restore.py — Restore from a named restore point.

Extracts the snapshot archive back into the project.
Does NOT restore git history — use `git checkout restore/<name>` for code.

Usage:
    python scripts/studio/restore.py --list
    python scripts/studio/restore.py --name "20260416_141200_before-social-v2"
    python scripts/studio/restore.py --name "20260416_141200_before-social-v2" --dry-run
"""
from __future__ import annotations

import argparse
import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RP_DIR = ROOT / "archive" / "restore_points"


def list_points() -> None:
    if not RP_DIR.exists():
        print("No restore points found.")
        return
    points = sorted(RP_DIR.iterdir(), reverse=True)
    print(f"\n{'RESTORE POINT':<45} {'COMMIT':<10} {'FILES':<8} MESSAGE")
    print("-" * 85)
    for p in points:
        mp = p / "manifest.json"
        if not mp.exists():
            continue
        m = json.loads(mp.read_text())
        commit = m.get("git_commit", "")[:8]
        fc = m.get("file_count", "?")
        msg = m.get("message", "")[:35]
        print(f"{m['rp_name']:<45} {commit:<10} {str(fc):<8} {msg}")
    print()


def restore(name: str, dry_run: bool = False) -> None:
    rp_dir = RP_DIR / name
    if not rp_dir.exists():
        # Try prefix match
        matches = [p for p in RP_DIR.iterdir() if p.name.endswith(f"_{name}") or p.name == name]
        if len(matches) == 1:
            rp_dir = matches[0]
        elif len(matches) > 1:
            print("Multiple matches — be more specific:")
            for m in matches:
                print(f"  {m.name}")
            sys.exit(1)
        else:
            print(f"Restore point not found: {name}")
            sys.exit(1)

    manifest_path = rp_dir / "manifest.json"
    zip_path = rp_dir / "snapshot.zip"

    if not zip_path.exists():
        print(f"Snapshot archive missing: {zip_path}")
        sys.exit(1)

    manifest = json.loads(manifest_path.read_text())
    print(f"\nRestore point: {manifest['rp_name']}")
    print(f"  Created:  {manifest['timestamp']}")
    print(f"  Commit:   {manifest.get('git_commit', '')[:8]}")
    print(f"  Git tag:  {manifest.get('git_tag', '')}")
    print(f"  Files:    {manifest.get('file_count', '?')}")
    print(f"  Message:  {manifest.get('message', '')}")

    if dry_run:
        print("\nDRY RUN — files that would be restored:")
        with zipfile.ZipFile(zip_path) as zf:
            for name in sorted(zf.namelist()):
                if name != "_backup_manifest.json":
                    print(f"  {name}")
        return

    confirm = input("\nRestore these files? This will overwrite current versions. [y/N] ").strip().lower()
    if confirm != "y":
        print("Aborted.")
        return

    restored = 0
    with zipfile.ZipFile(zip_path) as zf:
        for member in zf.infolist():
            if member.filename == "_backup_manifest.json":
                continue
            target = ROOT / member.filename
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(zf.read(member.filename))
            restored += 1

    print(f"\nRestored {restored} files from {manifest['rp_name']}")
    print(f"Note: To restore code to this state — git checkout {manifest.get('git_tag', '')}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Dandy Studio restore")
    parser.add_argument("--name", default="", help="Restore point name (or partial match)")
    parser.add_argument("--list", action="store_true", help="List all restore points")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be restored without doing it")
    args = parser.parse_args()

    if args.list:
        list_points()
    elif args.name:
        restore(args.name, args.dry_run)
    else:
        parser.print_help()
