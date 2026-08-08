"""
restore_point.py — Create a named restore point.

A restore point = git tag + backup archive.
Stored in archive/restore_points/{name}/

Usage:
    python scripts/studio/restore_point.py --name "before-social-v2"
    python scripts/studio/restore_point.py --name "pre-pitch-demo" --message "Ready for investor demo"
    python scripts/studio/restore_point.py --list
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import zipfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RP_DIR = ROOT / "archive" / "restore_points"

sys.path.insert(0, str(ROOT / "scripts" / "studio"))
from backup import collect_files


def git(cmd: list[str]) -> str:
    result = subprocess.run(
        ["git"] + cmd, cwd=ROOT, capture_output=True, text=True
    )
    return result.stdout.strip()


def create(name: str, message: str = "") -> Path:
    if not name:
        raise ValueError("Restore point name required")

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    rp_name = f"{stamp}_{name}"
    rp_dir = RP_DIR / rp_name
    rp_dir.mkdir(parents=True, exist_ok=True)

    # 1. Archive all tracked data
    files = collect_files()
    zip_path = rp_dir / "snapshot.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in files:
            zf.write(f, f.relative_to(ROOT))

    # 2. Git tag
    commit = git(["rev-parse", "HEAD"])
    tag = f"restore/{rp_name}"
    msg = message or f"Restore point: {name}"
    git(["tag", "-a", tag, "-m", msg])

    # 3. Write restore manifest
    manifest = {
        "name": name,
        "timestamp": stamp,
        "rp_name": rp_name,
        "git_commit": commit,
        "git_tag": tag,
        "message": msg,
        "file_count": len(files),
    }
    (rp_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))

    size_kb = zip_path.stat().st_size // 1024
    print(f"Restore point created: {rp_name}")
    print(f"  Git tag:  {tag}")
    print(f"  Commit:   {commit[:8]}")
    print(f"  Archive:  {zip_path.name} ({size_kb} KB, {len(files)} files)")
    return rp_dir


def list_points() -> None:
    if not RP_DIR.exists() or not any(RP_DIR.iterdir()):
        print("No restore points found.")
        return
    points = sorted(RP_DIR.iterdir(), reverse=True)
    print(f"{'NAME':<45} {'COMMIT':<10} {'MESSAGE'}")
    print("-" * 80)
    for p in points:
        manifest_path = p / "manifest.json"
        if not manifest_path.exists():
            continue
        m = json.loads(manifest_path.read_text())
        commit = m.get("git_commit", "")[:8]
        msg = m.get("message", "")[:40]
        print(f"{m['rp_name']:<45} {commit:<10} {msg}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Dandy Studio restore points")
    parser.add_argument("--name", default="", help="Name for the restore point")
    parser.add_argument("--message", default="", help="Description of this restore point")
    parser.add_argument("--list", action="store_true", help="List all restore points")
    args = parser.parse_args()

    if args.list:
        list_points()
    elif args.name:
        try:
            create(args.name, args.message)
        except Exception as e:
            print(f"Failed: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        parser.print_help()
