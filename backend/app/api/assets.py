from typing import Any, Dict, List, Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from ..services.storage.episode_store import (
    append_media_cue,
    load_asset,
    list_assets,
    load_media_cues,
    save_asset_upload,
    save_media_cues,
)


router = APIRouter(tags=["assets"])


class MediaCueRequest(BaseModel):
    asset_id: str
    line_number: Optional[int] = None
    start_seconds: Optional[float] = None
    end_seconds: Optional[float] = None
    display_label: str = ""
    notes: str = ""


class MediaCueBatchRequest(BaseModel):
    cues: List[MediaCueRequest]


@router.get("/episodes/{episode_id}/assets")
async def episode_assets(episode_id: str) -> Dict[str, Any]:
    assets = list_assets(episode_id)
    return {
        "episode_id": episode_id,
        "assets": assets,
        "count": len(assets),
    }


@router.post("/episodes/{episode_id}/assets")
async def upload_episode_asset(
    episode_id: str,
    file: UploadFile = File(...),
    label: str = Form(""),
    description: str = Form(""),
    role: str = Form("source"),
) -> Dict[str, Any]:
    if not file.filename:
        raise HTTPException(status_code=400, detail="file is required")

    metadata = save_asset_upload(
        episode_id,
        filename=file.filename,
        content_type=file.content_type or "application/octet-stream",
        file_stream=file.file,
        label=label,
        description=description,
        role=role,
    )
    return {"status": "uploaded", "asset": metadata}


@router.get("/episodes/{episode_id}/assets/{asset_id}")
async def episode_asset_detail(episode_id: str, asset_id: str) -> Dict[str, Any]:
    asset = load_asset(episode_id, asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    return asset


@router.get("/episodes/{episode_id}/assets/{asset_id}/file")
async def episode_asset_file(episode_id: str, asset_id: str):
    asset = load_asset(episode_id, asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    return FileResponse(
        asset["stored_path"],
        media_type=asset.get("content_type", "application/octet-stream"),
        filename=asset.get("original_name", asset_id),
    )


@router.get("/episodes/{episode_id}/media-cues")
async def episode_media_cues(episode_id: str) -> Dict[str, Any]:
    return load_media_cues(episode_id)


@router.post("/episodes/{episode_id}/media-cues")
async def add_episode_media_cue(episode_id: str, payload: MediaCueRequest) -> Dict[str, Any]:
    asset = load_asset(episode_id, payload.asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Referenced asset not found")
    return append_media_cue(episode_id, payload.model_dump())


@router.put("/episodes/{episode_id}/media-cues")
async def replace_episode_media_cues(episode_id: str, payload: MediaCueBatchRequest) -> Dict[str, Any]:
    for cue in payload.cues:
        asset = load_asset(episode_id, cue.asset_id)
        if not asset:
            raise HTTPException(status_code=404, detail=f"Referenced asset not found: {cue.asset_id}")
    return save_media_cues(episode_id, [cue.model_dump() for cue in payload.cues])
