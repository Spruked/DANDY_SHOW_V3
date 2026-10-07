"""Persistent take manifest for addressable Dandy dialogue production."""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any


EDITOR_VERSION = "1.0.0"


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def script_hash(episode_path: Path) -> str:
    path = episode_path / "script.json"
    if not path.is_file():
        raise FileNotFoundError(f"Saved script is missing: {path}")
    return file_hash(path)


def manifest_path(episode_path: Path) -> Path:
    return episode_path / "production_manifest.json"


def load_manifest(episode_path: Path) -> dict[str, Any] | None:
    path = manifest_path(episode_path)
    if not path.is_file():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    validate_manifest(payload)
    return payload


def save_manifest(episode_path: Path, payload: dict[str, Any]) -> None:
    validate_manifest(payload)
    path = manifest_path(episode_path)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(temporary, path)


def validate_manifest(payload: dict[str, Any]) -> None:
    if not isinstance(payload, dict) or not isinstance(payload.get("segments"), list):
        raise ValueError("Production manifest must contain a segment list")
    if not re.fullmatch(r"[0-9a-f]{64}", str(payload.get("script_hash", ""))):
        raise ValueError("Production manifest has no valid saved-script hash")
    if not payload.get("episode_id") or not payload.get("editor_run_id"):
        raise ValueError("Production manifest is missing episode or run identity")
    seen: set[str] = set()
    for segment in payload["segments"]:
        segment_id = str(segment.get("segment_id", ""))
        if not segment_id or segment_id in seen:
            raise ValueError(f"Production manifest has a missing or duplicate segment ID: {segment_id}")
        seen.add(segment_id)
        if not isinstance(segment.get("line_index"), int) or segment["line_index"] < 1:
            raise ValueError(f"Production segment {segment_id} has no valid line index")
        audio = segment.get("audio", {})
        if not isinstance(audio.get("take"), int) or audio["take"] < 1:
            raise ValueError(f"Production segment {segment_id} has no valid take number")
        chunks = audio.get("chunks")
        if not isinstance(chunks, list) or not chunks:
            raise ValueError(f"Production segment {segment_id} has no audio chunks")
        for chunk in chunks:
            if not chunk.get("asset_id") or not chunk.get("path"):
                raise ValueError(f"Production segment {segment_id} has an unaddressed take")
            if not re.fullmatch(r"[0-9a-f]{64}", str(chunk.get("hash", ""))):
                raise ValueError(f"Production segment {segment_id} has an invalid take hash")


def checked_take_path(episode_path: Path, relative_path: str) -> Path:
    root = episode_path.resolve()
    candidate = (root / relative_path).resolve()
    if candidate == root or root not in candidate.parents or not candidate.is_file():
        raise ValueError(f"Production take is missing or outside episode: {relative_path}")
    return candidate


def validate_takes(episode_path: Path, segments: list[dict[str, Any]]) -> None:
    for segment in segments:
        for chunk in segment.get("audio", {}).get("chunks", []):
            path = checked_take_path(episode_path, str(chunk.get("path") or ""))
            if file_hash(path) != chunk.get("hash"):
                raise ValueError(f"Production take hash mismatch: {path}")
