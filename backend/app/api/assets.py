from typing import Any, Dict, List, Optional

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from ..services.storage.asset_library import (
    library_summary,
    list_library_assets,
    load_library_asset,
)
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


def _resolve_any_asset(episode_id: str, asset_id: str) -> Optional[Dict[str, Any]]:
    if str(asset_id or "").startswith("lib_"):
        return load_library_asset(asset_id)
    return load_asset(episode_id, asset_id)


@router.get("/asset-library")
async def asset_library(query: str = Query(""), role: str = Query("")) -> Dict[str, Any]:
    assets = list_library_assets(query=query, role=role)
    return {
        "assets": assets,
        "count": len(assets),
        "summary": library_summary(),
    }


@router.get("/asset-library/{asset_id}/file")
async def asset_library_file(asset_id: str):
    asset = load_library_asset(asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Library asset not found")
    return FileResponse(
        asset["stored_path"],
        media_type=asset.get("content_type", "application/octet-stream"),
        filename=asset.get("original_name", asset_id),
    )


@router.get("/episodes/{episode_id}/assets")
async def episode_assets(episode_id: str) -> Dict[str, Any]:
    episode_assets_list = []
    for asset in list_assets(episode_id):
        episode_assets_list.append({
            **asset,
            "source": asset.get("source", "episode"),
            "scope": asset.get("scope", "episode"),
        })

    # Reusable repo assets are intentionally returned through the same endpoint
    # so the existing Episodes -> ASSETS button and Media Cue selector can call
    # them without a second UI subsystem.
    reusable = list_library_assets()
    combined = episode_assets_list + reusable
    return {
        "episode_id": episode_id,
        "assets": combined,
        "count": len(combined),
        "episode_count": len(episode_assets_list),
        "library_count": len(reusable),
        "library": library_summary(),
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
    asset = _resolve_any_asset(episode_id, asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    return asset


@router.get("/episodes/{episode_id}/assets/{asset_id}/file")
async def episode_asset_file(episode_id: str, asset_id: str):
    asset = _resolve_any_asset(episode_id, asset_id)
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
    asset = _resolve_any_asset(episode_id, payload.asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Referenced asset not found")
    record = payload.model_dump()
    # Keep the selected reusable asset self-describing in the cue label so old
    # cue storage remains backward-compatible while production can resolve the
    # actual asset by stable asset_id.
    if not record.get("display_label"):
        record["display_label"] = str(asset.get("role") or asset.get("label") or "media")
    return append_media_cue(episode_id, record)


@router.put("/episodes/{episode_id}/media-cues")
async def replace_episode_media_cues(episode_id: str, payload: MediaCueBatchRequest) -> Dict[str, Any]:
    for cue in payload.cues:
        if not _resolve_any_asset(episode_id, cue.asset_id):
            raise HTTPException(status_code=404, detail=f"Referenced asset not found: {cue.asset_id}")
    return save_media_cues(episode_id, [cue.model_dump() for cue in payload.cues])
