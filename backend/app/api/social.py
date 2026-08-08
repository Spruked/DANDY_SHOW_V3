from datetime import datetime
import base64
import json
from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from ..core.paths import PROJECT_ROOT
from ..core.settings import load_project_config
from ..services.social.package_builder import export_social_package
from ..services.storage.episode_store import load_episode_detail, load_media_cues, load_asset


router = APIRouter(tags=["social"])


def _social_root(config: Dict[str, Any]) -> Path:
    social_root = Path(config.get("social", {}).get("generated_root", "./social/generated"))
    if not social_root.is_absolute():
        social_root = (PROJECT_ROOT / social_root).resolve()
    social_root.mkdir(parents=True, exist_ok=True)
    return social_root


def _encode_export_id(path: Path, root: Path) -> str:
    rel = path.resolve().relative_to(root.resolve()).as_posix()
    return base64.urlsafe_b64encode(rel.encode("utf-8")).decode("ascii").rstrip("=")


def _decode_export_id(export_id: str, root: Path) -> Path:
    try:
        padding = "=" * ((4 - (len(export_id) % 4)) % 4)
        rel = base64.urlsafe_b64decode(f"{export_id}{padding}".encode("ascii")).decode("utf-8")
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid export id") from exc
    candidate = (root / rel).resolve()
    if not str(candidate).startswith(str(root.resolve())):
        raise HTTPException(status_code=400, detail="Invalid export id")
    return candidate


def _shape_social_exports(episode_id: str, root: Path) -> list[Dict[str, Any]]:
    episode_dir = root / episode_id
    export_path = episode_dir / "social_export.json"
    if not export_path.exists():
        return []

    try:
        payload = json.loads(export_path.read_text(encoding="utf-8"))
    except Exception:
        payload = {}

    files: list[tuple[str, Path]] = []
    for key in ("thumbnail", "video"):
        value = payload.get(key)
        if value:
            files.append((key, Path(value)))
    for clip in payload.get("clips", []):
        clip_id = clip.get("clip_id", "clip")
        for key in ("video", "audio"):
            value = clip.get(key)
            if value:
                files.append((f"{clip_id}_{key}", Path(value)))

    exports: list[Dict[str, Any]] = []
    for idx, (kind, file_path) in enumerate(files, start=1):
        if not file_path.is_absolute():
            file_path = (PROJECT_ROOT / file_path).resolve()
        if not file_path.exists() or not file_path.is_file():
            continue

        export_id = _encode_export_id(file_path, root)
        suffix = file_path.suffix.lower()
        is_image = suffix in {".png", ".jpg", ".jpeg", ".webp", ".gif"}
        created_at = datetime.fromtimestamp(file_path.stat().st_mtime).isoformat()
        exports.append(
            {
                "export_id": export_id,
                "episode_id": episode_id,
                "export_type": kind,
                "platform": "studio",
                "status": "done",
                "aspect_ratio": "",
                "asset_slot": "thumbnail_base",
                "created_at": created_at,
                "file_path": str(file_path),
                "preview_url": f"/api/social/{export_id}/download" if is_image else None,
                "download_url": f"/api/social/{export_id}/download",
                "sort_order": idx,
            }
        )
    return sorted(exports, key=lambda item: item.get("created_at", ""), reverse=True)


@router.post("/episodes/{episode_id}/social-package")
async def create_social_package_plan(episode_id: str) -> Dict:
    detail = load_episode_detail(episode_id)
    if not detail.get("config") and not detail.get("script"):
        raise HTTPException(status_code=404, detail="Episode not found")

    config = load_project_config()
    social_root = _social_root(config)
    destination = social_root / episode_id
    title = detail.get("config", {}).get("title") or episode_id
    topic = detail.get("config", {}).get("topic") or title
    audio_path = PROJECT_ROOT / "episodes" / episode_id / "audio.mp3"
    if not audio_path.exists():
        raise HTTPException(status_code=400, detail="Audio not found. Run production first.")

    script_lines = detail.get("script", [])
    script_text = "\n".join(f"{line.get('speaker', 'speaker')}: {line.get('text', '')}" for line in script_lines)
    media_cues_payload = load_media_cues(episode_id)
    resolved_cues = []
    for cue in media_cues_payload.get("cues", []):
        asset = load_asset(episode_id, cue.get("asset_id", ""))
        resolved_cues.append({**cue, "asset": asset or {}})
    plan = export_social_package(
        episode_id=episode_id,
        title=title,
        topic=topic,
        script_text=script_text,
        script_lines=script_lines,
        audio_path=audio_path,
        destination=destination,
        sponsor_text=config.get("social", {}).get("default_disclosure_text", "Sponsored"),
        media_cues=resolved_cues,
    )
    return {
        "status": "exported",
        "episode_id": episode_id,
        "destination": str(destination),
        "package": plan,
    }


@router.post("/social/generate")
async def generate_social_compat(payload: Dict[str, Any]) -> Dict:
    episode_id = str(payload.get("episode_id") or "").strip()
    if not episode_id:
        raise HTTPException(status_code=400, detail="episode_id is required")
    return await create_social_package_plan(episode_id)


@router.get("/social/presets")
async def social_presets() -> Dict:
    config = load_project_config()
    presets_path = Path(config.get("social", {}).get("presets_config", "./config/social_presets.json"))
    if not presets_path.is_absolute():
        presets_path = (PROJECT_ROOT / presets_path).resolve()

    payload = {}
    if presets_path.exists():
        try:
            payload = json.loads(presets_path.read_text(encoding="utf-8"))
        except Exception:
            payload = {}

    platforms = payload.get("platforms", {})
    presets = []
    for name, platform_config in platforms.items():
        presets.append(
            {
                "preset_id": name,
                "name": name.replace("_", " ").title(),
                "platform": name,
                "export_type": "audiogram" if platform_config.get("type") == "video" else "thumbnail",
                "aspect_ratio": (
                    f"{platform_config.get('width', 1)}:{platform_config.get('height', 1)}"
                    if platform_config.get("width") and platform_config.get("height")
                    else ""
                ),
            }
        )
    return {"presets": presets}


@router.get("/episodes/{episode_id}/social")
async def list_social_exports(episode_id: str) -> Dict:
    config = load_project_config()
    root = _social_root(config)
    exports = _shape_social_exports(episode_id, root)
    return {"episode_id": episode_id, "exports": exports}


@router.get("/social/{export_id}/download")
async def download_social_export(export_id: str):
    config = load_project_config()
    root = _social_root(config)
    target = _decode_export_id(export_id, root)
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="Export file not found")
    return FileResponse(target, filename=target.name)
