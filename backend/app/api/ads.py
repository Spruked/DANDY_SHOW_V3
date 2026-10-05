from datetime import datetime
import json
import uuid
import re
import tempfile
from pathlib import Path
from typing import Dict, Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from ..schemas.ads import AdCreateRequest, AdInsertRequest, AdComposition
from ..core.paths import PROJECT_ROOT, EPISODES_ROOT
from ..services.production.ads import generate_ad_lines, ad_audio_fingerprint
from ..services.ads.ad_engine import ADS_CATALOG, generate_ad_script, summarize_context
from ..services.storage.episode_store import (
    list_ads,
    load_script,
    load_ad_settings,
    save_ad_settings,
    save_ad,
    save_script,
)


router = APIRouter(tags=["ads"])

_SPEAKERS = {
    "intro_male": "announcer_male", "intro_female": "announcer_female",
    "announcer_male": "announcer_male", "announcer_female": "announcer_female",
    "phil": "phil", "jim": "jim",
}


def _insert_ad(episode_id: str, ad: Dict, line_index: Optional[int]) -> Dict:
    script = load_script(episode_id).get("script", [])
    existing = [index for index, line in enumerate(script) if line.get("ad_id") == ad["ad_id"]]
    if existing:
        return {"status": "already_inserted", "insert_at": existing[0], "script_length": len(script)}
    insert_at = len(script) if line_index is None else line_index
    if not 0 <= insert_at <= len(script):
        raise HTTPException(400, "Insertion position is outside the episode script")
    lines = [
        {**line, "ad_id": ad["ad_id"], "ad_line_index": index, "is_ad": True}
        for index, line in enumerate(ad.get("script", []), start=1)
    ]
    if not lines:
        raise HTTPException(400, "Ad has no script lines")
    script[insert_at:insert_at] = lines
    for index, line in enumerate(script, start=1):
        line["line_number"] = index
    save_script(episode_id, script)
    return {"status": "inserted", "insert_at": insert_at, "script_length": len(script), "ad_id": ad["ad_id"]}


@router.get("/episodes/{episode_id}/ads")
async def episode_ads(episode_id: str) -> Dict:
    script = load_script(episode_id).get("script", [])
    ads = []
    for ad in list_ads(episode_id):
        positions = [index for index, line in enumerate(script) if line.get("ad_id") == ad["ad_id"]]
        ads.append({**ad, "inserted": bool(positions), "inserted_line_index": positions[0] if positions else None})
    return {"episode_id": episode_id, "ads": ads}


@router.get("/ads/catalog")
async def ads_catalog() -> Dict:
    return {"ads": ADS_CATALOG}


@router.get("/ads/presets")
async def ads_presets() -> Dict:
    presets: list[Dict] = []
    presets_root = PROJECT_ROOT / "config" / "promo_presets"
    if presets_root.exists():
        for path in sorted(presets_root.glob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                presets.append(payload)
            except Exception:
                continue
    return {"presets": presets}


@router.get("/episodes/{episode_id}/ad-settings")
async def get_ad_settings(episode_id: str) -> Dict:
    return load_ad_settings(episode_id)


@router.post("/episodes/{episode_id}/ad-settings")
async def update_ad_settings(episode_id: str, payload: Dict):
    saved = save_ad_settings(episode_id, payload)
    return saved


@router.post("/episodes/{episode_id}/ads")
async def create_ad(episode_id: str, payload: AdCreateRequest):
    duration = payload.duration_seconds
    if duration < 5 or duration > 120:
        raise HTTPException(status_code=400, detail="duration_seconds must be between 5 and 120")

    script_context = load_script(episode_id).get("script", [])
    if payload.insert_into_script and payload.line_index is not None and payload.line_index > len(script_context):
        raise HTTPException(400, "Insertion position is outside the episode script")
    context_summary = summarize_context(script_context)

    raw_speaker = str(payload.announcer_key or "announcer_male").lower()
    from ..core.settings import load_voices_config
    configured_voices = load_voices_config()
    announcer_override = _SPEAKERS.get(raw_speaker, raw_speaker)
    if announcer_override not in configured_voices:
        raise HTTPException(422, "Requested voice identity is not registered in config/voices.json; no announcer fallback was substituted")

    if payload.custom_script.strip():
        lines = []
        for text in payload.custom_script.splitlines():
            text = text.strip()
            if not text:
                continue
            speaker = announcer_override
            labels = set(configured_voices) | set(_SPEAKERS)
            pattern = "|".join(re.escape(key) for key in sorted(labels, key=len, reverse=True))
            match = re.match(rf"^({pattern})\s*:\s*(.+)$", text, re.IGNORECASE)
            if match:
                key = match[1].lower()
                speaker, text = _SPEAKERS.get(key, key), match[2]
            if speaker not in configured_voices:
                raise HTTPException(422, f"Speaker '{speaker}' is not registered; no voice was substituted")
            lines.append({"speaker": speaker, "text": text, "emotion": payload.tone,
                          "pause_after": 0.4, "line_number": len(lines) + 1, "generated_by": "manual_edit"})
    elif payload.label and payload.label.lower() in ADS_CATALOG:
        lines = generate_ad_script(
            product_key=payload.label.lower(),
            announcer=announcer_override,
            episode_context=context_summary,
            duration_seconds=duration,
            sponsor=payload.sponsor, product_name=payload.product,
            offer=payload.offer, cta=payload.cta,
        )
    else:
        lines = generate_ad_lines(
            sponsor=payload.sponsor,
            product=payload.product,
            offer=payload.offer,
            cta=payload.cta,
            duration_seconds=duration,
            tone=payload.tone,
        )
        for line in lines:
            line["speaker"] = announcer_override
    for line in lines:
        line.setdefault("generated_by", "ad_engine")
    if not lines:
        raise HTTPException(400, "Ad script must contain spoken text")
    ad_record = save_ad(
        episode_id,
        {
            "label": payload.label or f"{duration}s - {payload.sponsor}",
            "sponsor": payload.sponsor,
            "product": payload.product,
            "offer": payload.offer,
            "cta": payload.cta,
            "tone": payload.tone,
            "duration_seconds": duration,
            "script": lines,
            "created_at": datetime.now().isoformat(),
            "announcer_key": announcer_override,
            "requested_voice": raw_speaker,
            "resolved_voice": announcer_override,
            "fallback_used": False,
            "custom_script": payload.custom_script,
            "ad_type": payload.ad_type,
            "status": "draft",
            "estimated_duration_seconds": round(sum(len(line["text"].split()) / 2.5 + line.get("pause_after", 0) for line in lines), 1),
        },
    )

    updated_script = None
    if payload.insert_into_script:
        _insert_ad(episode_id, ad_record, payload.line_index)
        updated_script = load_script(episode_id).get("script", [])

    response = {"status": "created", "ad": ad_record}
    if updated_script is not None:
        response["updated_script"] = updated_script
    return response


@router.post("/episodes/{episode_id}/ads/{ad_id}/produce")
def produce_ad_audio(episode_id: str, ad_id: str) -> Dict:
    """Run TTS on the ad script lines and save the resulting MP3."""
    ad = next((a for a in list_ads(episode_id) if a.get("ad_id") == ad_id), None)
    if not ad:
        raise HTTPException(404, "Ad not found")

    script_lines = ad.get("script", [])
    if not script_lines:
        raise HTTPException(400, "Ad has no script lines to produce")

    try:
        from .production import _get_worker
        worker = _get_worker()
    except Exception as e:
        raise HTTPException(503, f"TTS worker unavailable: {e}")

    staging_dir = PROJECT_ROOT / "staging" / "ads" / episode_id / ad_id
    staging_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="produce_", dir=staging_dir) as scratch:
        scratch = Path(scratch)
        raw_mix = scratch / "raw_mix.mp3"
        try:
            segments = worker._synthesize_segments([{**line, "is_ad": True} for line in script_lines], scratch, episode_id)
            # Ad voice assembly must not apply unrelated episode media cues.
            from ..services.production.worker import HardenedPodcastWorker
            HardenedPodcastWorker._concatenate_segments(worker, segments, raw_mix)
        except Exception as exc:
            raise HTTPException(500, f"TTS synthesis failed: {exc}") from exc

        from pydub import AudioSegment
        sound = AudioSegment.from_file(raw_mix)
        target_ms = round(float(ad["duration_seconds"]) * 1000)
        if len(sound) > target_ms + 150:
            raise HTTPException(422, f"Spoken script is {len(sound) / 1000:.2f}s, longer than the requested {ad['duration_seconds']}s. Increase duration or shorten copy; the script and voice were not trimmed or changed.")
        if len(sound) < target_ms:
            sound += AudioSegment.silent(duration=target_ms - len(sound), frame_rate=sound.frame_rate)
            sound.export(raw_mix, format="mp3", bitrate="192k").close()

        resolution = []
        for segment in segments:
            record = {"requested_voice": segment["speaker"], "resolved_voice": segment["speaker"],
                      "resolved_voice_id": segment["voice_name"], "engine": segment["engine"], "fallback_used": False}
            if record not in resolution:
                resolution.append(record)
        ads_dir = EPISODES_ROOT / episode_id / "ads"
        ads_dir.mkdir(exist_ok=True)
        # A failed re-production must preserve the last accepted audio file.
        final_audio = ads_dir / f"{ad_id}.mp3"
        measured = worker._probe_duration_seconds(raw_mix)
        raw_mix.replace(final_audio)

    updated = {**ad, "audio_file": str(final_audio), "produced_at": datetime.now().isoformat(),
               "status": "produced", "actual_duration_seconds": measured,
               "audio_script_fingerprint": ad_audio_fingerprint(script_lines),
               "voice_resolution": resolution}

    save_ad(episode_id, updated)
    return {"status": "produced", "ad": updated}


def _find_ad(episode_id, ad_id):
    ad = next((item for item in list_ads(episode_id) if item.get("ad_id") == ad_id), None)
    if not ad:
        raise HTTPException(404, "Ad not found")
    return ad


@router.put("/episodes/{episode_id}/ads/{ad_id}/composition")
def save_composition(episode_id: str, ad_id: str, payload: AdComposition):
    ad = _find_ad(episode_id, ad_id)
    duration = float(ad.get("duration_seconds") or 30)
    if any(layer.end > duration for layer in payload.text_layers + payload.visuals) or any(track.start >= duration for track in payload.sfx_tracks):
        raise HTTPException(422, "Composition timing must stay within the requested ad duration")
    meta_path = EPISODES_ROOT / episode_id / "ads" / f"{ad_id}_assets.json"
    assets = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.is_file() else []
    asset_map = {asset["asset_id"]: asset for asset in assets}
    visual_types = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".mp4", ".mov", ".webm", ".mkv", ".avi"}
    audio_types = {".wav", ".mp3", ".ogg", ".flac", ".m4a", ".aac"}
    for track in payload.visuals + payload.sfx_tracks:
        asset = asset_map.get(track.asset_id)
        if not asset or not Path(asset["stored_path"]).is_file():
            raise HTTPException(422, f"Asset '{track.asset_id}' is not attached or its file is missing")
        allowed = visual_types if track in payload.visuals else audio_types
        if Path(asset["stored_path"]).suffix.lower() not in allowed:
            raise HTTPException(422, f"Asset '{track.asset_id}' has an unsupported file type for this track")
    updated = save_ad(episode_id, {**ad, "composition": payload.model_dump(), "composition_saved_at": datetime.now().isoformat()})
    return {"status": "saved", "ad": updated}


@router.post("/episodes/{episode_id}/ads/{ad_id}/render")
def render_composition(episode_id: str, ad_id: str):
    ad = _find_ad(episode_id, ad_id)
    if not ad.get("audio_file") or not Path(ad["audio_file"]).is_file():
        raise HTTPException(422, "Produce the ad voice audio before rendering its visual composition")
    if not ad.get("composition"):
        raise HTTPException(422, "Save the visual composition before rendering")
    asset_meta = EPISODES_ROOT / episode_id / "ads" / f"{ad_id}_assets.json"
    assets = json.loads(asset_meta.read_text(encoding="utf-8")) if asset_meta.is_file() else []
    from ..services.social.slideshow_renderer import render_composed_ad
    try:
        output = render_composed_ad(ad, AdComposition(**ad["composition"]), assets)
    except Exception as exc:
        raise HTTPException(422, f"Visual ad render failed: {exc}") from exc
    updated = save_ad(episode_id, {**ad, "visual_export": output, "visual_rendered_at": datetime.now().isoformat()})
    return {"status": "rendered", "ad": updated, **output}


@router.post("/episodes/{episode_id}/ads/{ad_id}/insert")
async def insert_ad_into_script(episode_id: str, ad_id: str, payload: AdInsertRequest) -> Dict:
    """Splice ad script lines into the episode script at a given position."""
    ad = next((a for a in list_ads(episode_id) if a.get("ad_id") == ad_id), None)
    if not ad:
        raise HTTPException(404, "Ad not found")

    return _insert_ad(episode_id, ad, payload.line_index)


@router.get("/episodes/{episode_id}/ads/{ad_id}/assets")
async def list_ad_assets(episode_id: str, ad_id: str) -> Dict:
    meta_path = EPISODES_ROOT / episode_id / "ads" / f"{ad_id}_assets.json"
    if not meta_path.exists():
        return {"ad_id": ad_id, "assets": []}
    return {"ad_id": ad_id, "assets": json.loads(meta_path.read_text(encoding="utf-8"))}


@router.post("/episodes/{episode_id}/ads/{ad_id}/assets")
async def upload_ad_asset(
    episode_id: str,
    ad_id: str,
    file: UploadFile = File(...),
    label: str = Form(""),
) -> Dict:
    asset_dir = EPISODES_ROOT / episode_id / "ads" / f"{ad_id}_assets"
    asset_dir.mkdir(parents=True, exist_ok=True)
    meta_path = EPISODES_ROOT / episode_id / "ads" / f"{ad_id}_assets.json"

    asset_id = f"asset_{uuid.uuid4().hex[:8]}"
    suffix = Path(file.filename or "file").suffix
    stored_name = f"{asset_id}{suffix}"
    stored_path = asset_dir / stored_name
    stored_path.write_bytes(await file.read())

    existing = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else []
    record = {
        "asset_id": asset_id,
        "original_name": file.filename,
        "stored_name": stored_name,
        "stored_path": str(stored_path),
        "content_type": file.content_type or "application/octet-stream",
        "label": label,
        "uploaded_at": datetime.now().isoformat(),
    }
    existing.append(record)
    meta_path.write_text(json.dumps(existing, indent=2), encoding="utf-8")
    return {"status": "uploaded", "asset": record}


@router.get("/episodes/{episode_id}/ads/{ad_id}/assets/{asset_id}/file")
async def serve_ad_asset(episode_id: str, ad_id: str, asset_id: str):
    meta_path = EPISODES_ROOT / episode_id / "ads" / f"{ad_id}_assets.json"
    if not meta_path.exists():
        raise HTTPException(404, "No assets for this ad")
    assets = json.loads(meta_path.read_text(encoding="utf-8"))
    rec = next((a for a in assets if a["asset_id"] == asset_id), None)
    if not rec:
        raise HTTPException(404, "Asset not found")
    return FileResponse(rec["stored_path"], media_type=rec["content_type"], filename=rec["original_name"])


@router.get("/episodes/{episode_id}/ads/{ad_id}/audio")
async def ad_audio(episode_id: str, ad_id: str):
    ad = next((item for item in list_ads(episode_id) if item.get("ad_id") == ad_id), None)
    if not ad:
        raise HTTPException(status_code=404, detail="Ad not found")

    audio_path = ad.get("audio_file") or ad.get("audio_path") or ad.get("audio")
    if not audio_path:
        raise HTTPException(status_code=404, detail="Audio not found for this ad")

    path = Path(audio_path)
    if not path.is_absolute():
        path = (PROJECT_ROOT / path).resolve()
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Ad audio file missing")

    return FileResponse(path, media_type="audio/mpeg", filename=path.name)
