"""Repo-wide production asset library.

Dandy keeps reusable media in the repository and indexes it at request time.
Files are never copied into a database. The catalog provides stable IDs over
repo-relative paths so the Episodes UI can call reusable SFX, jingles, ad beds,
music, images, voice clips, and documents from one Assets control.
"""

from __future__ import annotations

import hashlib
import mimetypes
from pathlib import Path
from typing import Any, Dict, List, Optional

from ...core.paths import PROJECT_ROOT


LIBRARY_ROOT = PROJECT_ROOT / "asset_library"

# Existing canonical folders remain first-class. asset_library/ is the new
# general drop zone for anything reusable across episodes.
_SCAN_ROOTS = (
    (LIBRARY_ROOT, None),
    (PROJECT_ROOT / "audio" / "sfx", "sfx"),
    (PROJECT_ROOT / "audio" / "jingles", "jingle"),
    (PROJECT_ROOT / "audio" / "ads", "ad"),
    (PROJECT_ROOT / "social" / "assets", "image"),
    (PROJECT_ROOT / "social" / "templates", "image"),
)

_AUDIO_EXTS = {".mp3", ".wav", ".ogg", ".flac", ".aac", ".m4a"}
_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg"}
_VIDEO_EXTS = {".mp4", ".mov", ".webm", ".mkv"}
_DOCUMENT_EXTS = {".txt", ".md", ".json", ".csv", ".pdf", ".doc", ".docx", ".rtf", ".html", ".htm"}


def ensure_library_roots() -> None:
    for name in ("sfx", "jingles", "ads", "music", "voice", "images", "documents", "misc"):
        (LIBRARY_ROOT / name).mkdir(parents=True, exist_ok=True)


def _asset_id(path: Path) -> str:
    rel = path.resolve().relative_to(PROJECT_ROOT.resolve()).as_posix().lower()
    return "lib_" + hashlib.sha1(rel.encode("utf-8")).hexdigest()[:14]


def _asset_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in _AUDIO_EXTS:
        return "audio"
    if suffix in _IMAGE_EXTS:
        return "image"
    if suffix in _VIDEO_EXTS:
        return "video"
    if suffix in _DOCUMENT_EXTS:
        return "document"
    return "file"


def _role_for(path: Path, fixed_role: Optional[str]) -> str:
    if fixed_role:
        return fixed_role
    try:
        rel = path.resolve().relative_to(LIBRARY_ROOT.resolve())
        first = rel.parts[0].lower() if len(rel.parts) > 1 else "misc"
    except Exception:
        return "misc"
    aliases = {
        "jingles": "jingle",
        "ads": "ad",
        "images": "image",
        "documents": "document",
    }
    return aliases.get(first, first)


def _record(path: Path, fixed_role: Optional[str]) -> Dict[str, Any]:
    resolved = path.resolve()
    rel = resolved.relative_to(PROJECT_ROOT.resolve()).as_posix()
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    stat = path.stat()
    return {
        "asset_id": _asset_id(path),
        "source": "library",
        "scope": "global",
        "role": _role_for(path, fixed_role),
        "asset_type": _asset_type(path),
        "label": path.stem.replace("_", " ").replace("-", " ").strip(),
        "original_name": path.name,
        "filename": path.name,
        "relative_path": rel,
        "stored_path": str(resolved),
        "content_type": mime,
        "size_bytes": stat.st_size,
        "modified_at": stat.st_mtime,
        "description": f"Reusable repo asset: {rel}",
    }


def list_library_assets(query: str = "", role: str = "") -> List[Dict[str, Any]]:
    ensure_library_roots()
    query_norm = str(query or "").strip().lower()
    role_norm = str(role or "").strip().lower()
    seen: set[str] = set()
    assets: List[Dict[str, Any]] = []

    for root, fixed_role in _SCAN_ROOTS:
        if not root.exists():
            continue
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.name.startswith("."):
                continue
            try:
                record = _record(path, fixed_role)
            except (OSError, ValueError):
                continue
            if record["asset_id"] in seen:
                continue
            if role_norm and str(record.get("role", "")).lower() != role_norm:
                continue
            haystack = " ".join(
                str(record.get(k, ""))
                for k in ("label", "filename", "relative_path", "role", "asset_type")
            ).lower()
            if query_norm and query_norm not in haystack:
                continue
            seen.add(record["asset_id"])
            assets.append(record)

    assets.sort(key=lambda item: (str(item.get("role", "")), str(item.get("label", "")).lower()))
    return assets


def load_library_asset(asset_id: str) -> Optional[Dict[str, Any]]:
    if not str(asset_id or "").startswith("lib_"):
        return None
    for asset in list_library_assets():
        if asset.get("asset_id") == asset_id:
            return asset
    return None


def library_summary() -> Dict[str, Any]:
    assets = list_library_assets()
    by_role: Dict[str, int] = {}
    for asset in assets:
        role = str(asset.get("role", "misc"))
        by_role[role] = by_role.get(role, 0) + 1
    return {
        "root": str(LIBRARY_ROOT),
        "count": len(assets),
        "by_role": dict(sorted(by_role.items())),
        "drop_folders": [str(LIBRARY_ROOT / name) for name in ("sfx", "jingles", "ads", "music", "voice", "images", "documents", "misc")],
    }
