from datetime import datetime
import base64
import json
import math
import mimetypes
import os
import shutil
import subprocess
from uuid import uuid4
from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from ..core.paths import PROJECT_ROOT
from ..core.settings import load_project_config
from ..services.social.package_builder import export_social_package
from ..services.storage.episode_store import load_episode_detail, load_media_cues, load_asset
from ..services.storage.asset_library import load_library_asset, load_episode_ad_asset
from ..schemas.social_visual import SocialExportRequest
from ..services.social.thumbnail_generator import generate_thumbnail
from ..services.social.audiogram_generator import generate_audiogram


router = APIRouter(tags=["social"])
BRAND_SLOTS = ("thumbnail_base", "waveform_base", "alternate_cover", "character_logo", "segment_tech_talk", "logo")
ASPECT_SIZES = {"16:9": (1280, 720), "1:1": (1080, 1080), "9:16": (1080, 1920), "4:5": (1080, 1350)}


def _brand_path(filename):
    if filename not in {f"{slot}.png" for slot in BRAND_SLOTS}:
        raise HTTPException(400, "Unknown brand asset filename")
    for base in (PROJECT_ROOT / "social" / "templates", PROJECT_ROOT / "social" / "assets"):
        target = base / filename
        if target.is_file():
            return target
    return None


@router.get("/social/assets")
def brand_assets_status():
    return {"assets": [{"id": slot, "key": slot, "filename": f"{slot}.png", "name": slot.replace("_", " ").title(),
                        "available": _brand_path(f"{slot}.png") is not None,
                        "preview_url": f"/api/social/assets/{slot}.png"} for slot in BRAND_SLOTS]}


@router.get("/social/assets/{filename}")
def brand_asset_file(filename: str):
    path = _brand_path(filename)
    if not path:
        raise HTTPException(404, "Brand image is missing from social/templates or social/assets")
    return FileResponse(path)


def _social_root(config: Dict[str, Any]) -> Path:
    social_root = Path(config.get("social", {}).get("generated_root", "./social/generated"))
    if not social_root.is_absolute():
        social_root = (PROJECT_ROOT / social_root).resolve()
    social_root.mkdir(parents=True, exist_ok=True)
    return social_root


def _resolve_visual_asset(episode_id: str, asset_id: str) -> Dict[str, Any] | None:
    value = str(asset_id or "")
    if value.startswith("lib_"):
        return load_library_asset(value)
    if value.startswith("adlib_"):
        return load_episode_ad_asset(episode_id, value)
    return load_asset(episode_id, value)


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
    if not candidate.is_relative_to(root.resolve()):
        raise HTTPException(status_code=400, detail="Invalid export id")
    return candidate


def _shape_social_exports(episode_id: str, root: Path) -> list[Dict[str, Any]]:
    episode_dir = root / episode_id
    export_path = episode_dir / "social_export.json"
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

        if not file_path.resolve().is_relative_to(root.resolve()):
            continue
        export_id = _encode_export_id(file_path, root)
        suffix = file_path.suffix.lower()
        is_image = suffix in {".png", ".jpg", ".jpeg", ".webp", ".gif"}
        media_type = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"
        is_previewable = is_image or media_type.startswith(("video/", "audio/"))
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
                "media_type": media_type,
                "created_at": created_at,
                "file_path": str(file_path),
                "preview_url": f"/api/social/{export_id}/preview" if is_previewable else None,
                "download_url": f"/api/social/{export_id}/download",
                "sort_order": idx,
            }
        )
    for manifest in episode_dir.glob("*/export.json"):
        try:
            item = json.loads(manifest.read_text(encoding="utf-8"))
            path = Path(item["file_path"]).resolve()
            if path.is_file() and path.is_relative_to(root.resolve()):
                media_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
                export_id = item.get("export_id") or _encode_export_id(path, root)
                previewable = media_type.startswith(("image/", "video/", "audio/"))
                exports.append({**item, "export_id": export_id, "media_type": media_type,
                                "preview_url": f"/api/social/{export_id}/preview" if previewable else None})
        except (OSError, ValueError, KeyError):
            continue
    return sorted(exports, key=lambda item: item.get("created_at", ""), reverse=True)


@router.post("/episodes/{episode_id}/social-package")
def create_social_package_plan(episode_id: str) -> Dict:
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
def generate_social_compat(payload: SocialExportRequest) -> Dict:
    episode_id = payload.episode_id
    if episode_id in {".", ".."}:
        raise HTTPException(400, "Invalid episode id")
    detail = load_episode_detail(episode_id)
    if not detail.get("script") and not detail.get("config"):
        raise HTTPException(404, "Episode not found")
    config = detail.get("config", {})
    title = config.get("title") or detail.get("title") or episode_id
    topic = config.get("topic") or title
    script_text = "\n".join(f"{line.get('speaker', 'speaker')}: {line.get('text', '')}" for line in detail.get("script", []))
    if payload.export_type == "quote_card" and not payload.quote_text.strip():
        raise HTTPException(422, "Quote cards require quote text")
    background = None
    if payload.asset_slot != "none":
        background = _brand_path(f"{payload.asset_slot}.png")
        if not background:
            raise HTTPException(422, f"Selected asset {payload.asset_slot} is missing. Add its image or explicitly select Plain background.")
    root = _social_root(load_project_config())
    destination = root / episode_id / uuid4().hex[:12]
    destination.mkdir(parents=True, exist_ok=True)
    post_text = payload.post_text or f"{title}\n\n{topic}\n\n#PhilAndJimDandy"
    copy_path = destination / "post_copy.txt"
    copy_path.write_text(post_text, encoding="utf-8")
    width, height = ASPECT_SIZES[payload.aspect_ratio]
    if payload.export_type == "show_notes":
        path = destination / "show_notes.txt"
        path.write_text(f"{title}\nPlatform: {payload.platform}\n\n{post_text}\n\nTranscript\n{script_text}", encoding="utf-8")
    elif payload.export_type in {"thumbnail", "quote_card"}:
        output = generate_thumbnail(episode_id, payload.quote_text if payload.export_type == "quote_card" else title,
                                    subtitle=title if payload.export_type == "quote_card" else topic,
                                    background_image_path=str(background) if background else None, output_dir=destination,
                                    config_overrides={"width": width, "height": height, "background_image_path": None, "logo_path": None,
                                                      "output_format": "png", "wrap_text": True})
        if not output:
            raise HTTPException(500, "Image rendering failed; no completed export was recorded")
        path = Path(output)
    else:
        from .production import _resolve_episode_audio_path
        audio = _resolve_episode_audio_path(episode_id)
        status_path = PROJECT_ROOT / "episodes" / episode_id / "status.json"
        status = json.loads(status_path.read_text(encoding="utf-8")) if status_path.is_file() else {}
        if not audio or status.get("production_mode") == "placeholder_fallback" or status.get("status") == "failed":
            raise HTTPException(422, "Produce real episode audio before generating a video export")
        ffprobe = os.getenv("DANDY_FFPROBE") or shutil.which("ffprobe")
        ffmpeg = os.getenv("DANDY_FFMPEG") or shutil.which("ffmpeg")
        if not ffprobe or not ffmpeg:
            raise HTTPException(503, "FFmpeg and ffprobe are required")
        probe = subprocess.run([ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(audio)],
                               capture_output=True, text=True, timeout=10, check=True)
        actual_duration = float(probe.stdout.strip())
        if not math.isfinite(actual_duration) or payload.clip_start + payload.clip_duration > actual_duration + 0.05:
            raise HTTPException(422, f"Requested clip exceeds the audio duration ({actual_duration:.2f}s); choose an in-range start and duration")
        selected_visual_ids = payload.visual_asset_ids if payload.visual_mode == "slideshow" else ([payload.visual_asset_id] if payload.visual_asset_id else [])
        visual_paths: list[Path] = []
        for asset_id in selected_visual_ids:
            asset = _resolve_visual_asset(episode_id, asset_id)
            if not asset:
                raise HTTPException(422, f"Selected visual asset is no longer available: {asset_id}")
            asset_type = str(asset.get("asset_type") or "").lower()
            visual_path = Path(str(asset.get("stored_path") or ""))
            if asset_type not in {"image", "video"} or not visual_path.is_file():
                raise HTTPException(422, f"Selected asset is not a readable image or video: {asset.get('label') or asset_id}")
            visual_paths.append(visual_path.resolve())
        video_extensions = {".mp4", ".mov", ".webm", ".mkv", ".avi"}
        image_extensions = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}
        if payload.visual_mode == "video" and (not visual_paths or visual_paths[0].suffix.lower() not in video_extensions):
            raise HTTPException(422, "Video visual mode requires one selected video asset")
        if payload.visual_mode in {"image", "slideshow"} and not visual_paths:
            raise HTTPException(422, f"{payload.visual_mode.title()} visual mode requires at least one selected image")
        if payload.visual_mode == "image" and visual_paths and visual_paths[0].suffix.lower() in video_extensions:
            raise HTTPException(422, "Single image mode requires an image asset")
        if payload.visual_mode == "image" and visual_paths and visual_paths[0].suffix.lower() not in image_extensions:
            raise HTTPException(422, "Single image mode requires a supported raster image (PNG, JPEG, WebP, GIF, or BMP)")
        if payload.visual_mode == "slideshow" and any(path.suffix.lower() in video_extensions for path in visual_paths):
            raise HTTPException(422, "Slideshow mode accepts images only")
        if payload.visual_mode == "slideshow" and any(path.suffix.lower() not in image_extensions for path in visual_paths):
            raise HTTPException(422, "Slideshow mode requires raster images (PNG, JPEG, WebP, GIF, or BMP)")
        clip = destination / "clip.mp3"
        subprocess.run([ffmpeg, "-y", "-ss", str(payload.clip_start), "-i", str(audio), "-t", str(payload.clip_duration), "-vn", "-c:a", "libmp3lame", str(clip)],
                       capture_output=True, text=True, timeout=60, check=True)
        path = destination / f"{payload.export_type}.mp4"
        output = generate_audiogram(clip, path, title=title, background_image_path=str(background) if background else None,
                                    hook_text=payload.quote_text,
                                    config_overrides={"width": width, "height": height, "show_waveform": payload.show_waveform,
                                                      "background_image_path": None, "logo_path": None,
                                                      "output_duration": payload.clip_duration},
                                    visual_mode=payload.visual_mode,
                                    visual_asset_path=str(visual_paths[0]) if visual_paths and payload.visual_mode != "slideshow" else None,
                                    visual_asset_paths=[str(p) for p in visual_paths],
                                    visual_clip_start=payload.visual_clip_start)
        if not output:
            raise HTTPException(500, "Video renderer failed; no completed export was recorded")
    if not path.is_file() or not path.stat().st_size:
        raise HTTPException(500, "Renderer did not produce a non-empty file")
    export_id = _encode_export_id(path, root)
    item = {**payload.model_dump(), "export_id": export_id, "status": "done", "created_at": datetime.now().isoformat(),
            "file_path": str(path), "download_url": f"/api/social/{export_id}/download",
            "preview_url": f"/api/social/{export_id}/download" if path.suffix == ".png" else None,
            "post_text": post_text, "post_copy_url": f"/api/social/{_encode_export_id(copy_path, root)}/download",
            "width": width, "height": height}
    (destination / "export.json").write_text(json.dumps(item, indent=2), encoding="utf-8")
    return {"status": "exported", "export": item}


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
                    f"{platform_config['width'] // math.gcd(platform_config['width'], platform_config['height'])}:{platform_config['height'] // math.gcd(platform_config['width'], platform_config['height'])}"
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


@router.get("/social/{export_id}/preview")
async def preview_social_export(export_id: str):
    config = load_project_config()
    root = _social_root(config)
    target = _decode_export_id(export_id, root)
    if not target.is_file():
        raise HTTPException(status_code=404, detail="Export preview not found")
    media_type = mimetypes.guess_type(str(target))[0]
    if not media_type or not media_type.startswith(("image/", "video/", "audio/")):
        raise HTTPException(status_code=415, detail="This export type cannot be previewed inline")
    return FileResponse(target, media_type=media_type, content_disposition_type="inline")
