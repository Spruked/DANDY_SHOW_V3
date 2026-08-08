from datetime import datetime
import json
import uuid
from pathlib import Path
from typing import Dict, Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from ..schemas.ads import AdCreateRequest
from ..core.paths import PROJECT_ROOT, EPISODES_ROOT
from ..services.production.ads import generate_ad_lines
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


@router.get("/episodes/{episode_id}/ads")
async def episode_ads(episode_id: str) -> Dict:
    return {"episode_id": episode_id, "ads": list_ads(episode_id)}


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
    context_summary = summarize_context(script_context)

    announcer_override = payload.announcer_key or ("announcer_female" if duration == 15 else "announcer_male")

    if payload.label and payload.label.lower() in ADS_CATALOG:
        lines = generate_ad_script(
            product_key=payload.label.lower(),
            announcer=announcer_override,
            episode_context=context_summary,
            duration_seconds=duration,
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
        },
    )

    updated_script = None
    if payload.insert_into_script:
        script_data = load_script(episode_id)
        script = script_data.get("script", [])
        insert_at = payload.line_index if payload.line_index is not None else len(script)
        if insert_at < 0 or insert_at > len(script):
            insert_at = len(script)
        # Insert ad lines
        script[insert_at:insert_at] = lines
        # Reindex
        for idx, line in enumerate(script, start=1):
            line["line_number"] = idx
        save_script(episode_id, script)
        updated_script = script

    response = {"status": "created", "ad": ad_record}
    if updated_script is not None:
        response["updated_script"] = updated_script
    return response


@router.post("/episodes/{episode_id}/ads/{ad_id}/produce")
async def produce_ad_audio(episode_id: str, ad_id: str) -> Dict:
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
    raw_mix = staging_dir / "raw_mix.mp3"

    try:
        segments = worker._synthesize_segments(script_lines, staging_dir, episode_id)
        worker._concatenate_segments(segments, raw_mix)
    except Exception as e:
        raise HTTPException(500, f"TTS synthesis failed: {e}")

    ads_dir = EPISODES_ROOT / episode_id / "ads"
    ads_dir.mkdir(exist_ok=True)
    final_audio = ads_dir / f"{ad_id}.mp3"
    if final_audio.exists():
        final_audio.unlink()
    raw_mix.replace(final_audio)

    updated = {**ad, "audio_file": str(final_audio), "produced_at": datetime.now().isoformat(), "status": "produced"}
    save_ad(episode_id, updated)
    return {"status": "produced", "ad": updated}


@router.post("/episodes/{episode_id}/ads/{ad_id}/insert")
async def insert_ad_into_script(episode_id: str, ad_id: str, payload: Dict) -> Dict:
    """Splice ad script lines into the episode script at a given position."""
    ad = next((a for a in list_ads(episode_id) if a.get("ad_id") == ad_id), None)
    if not ad:
        raise HTTPException(404, "Ad not found")

    lines = ad.get("script", [])
    if not lines:
        raise HTTPException(400, "Ad has no script lines")

    script_data = load_script(episode_id)
    script = script_data.get("script", [])
    line_index = payload.get("line_index")
    insert_at = int(line_index) if line_index is not None else len(script)
    insert_at = max(0, min(insert_at, len(script)))

    script[insert_at:insert_at] = lines
    for idx, line in enumerate(script, start=1):
        line["line_number"] = idx
    save_script(episode_id, script)

    return {"status": "inserted", "insert_at": insert_at, "script_length": len(script)}


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
