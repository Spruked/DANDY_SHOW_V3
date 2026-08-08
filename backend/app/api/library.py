from typing import Dict, Any

from fastapi import APIRouter, Body, HTTPException

from ..services.storage.episode_store import (
    list_episode_summaries,
    load_episode_detail,
    load_script,
    save_episode_config,
)


router = APIRouter(tags=["library"])


@router.get("/library")
async def library() -> Dict:
    return {"episodes": list_episode_summaries()}


@router.get("/episodes")
async def episodes() -> Dict:
    return {"episodes": list_episode_summaries()}


@router.get("/episodes/{episode_id}/script")
async def episode_script(episode_id: str) -> Dict:
    script_data = load_script(episode_id)
    return {
        "episode_id": episode_id,
        "script": script_data.get("script", []),
        "updated_at": script_data.get("updated_at"),
        "line_count": len(script_data.get("script", [])),
    }


@router.get("/episodes/{episode_id}")
async def episode_detail(episode_id: str) -> Dict:
    return load_episode_detail(episode_id)


@router.patch("/episodes/{episode_id}/config")
async def update_episode_config(
    episode_id: str,
    payload: Dict[str, Any] = Body(...),
) -> Dict:
    detail = load_episode_detail(episode_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Episode not found")
    updated = save_episode_config(episode_id, payload)
    return {"episode_id": episode_id, "config": updated}
