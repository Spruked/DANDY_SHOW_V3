from typing import Dict

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..services.obs import OBSClient, OBSError, OBSConnectionError


router = APIRouter(tags=["obs"])


class SceneSwitchRequest(BaseModel):
    scene_name: str


def _client() -> OBSClient:
    return OBSClient.from_runtime_config()


def _raise_obs_http(exc: OBSError) -> None:
    if isinstance(exc, OBSConnectionError):
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/obs/status")
async def obs_status() -> Dict:
    try:
        return await _client().status()
    except OBSError as exc:
        _raise_obs_http(exc)


@router.get("/obs/scenes")
async def obs_scenes() -> Dict:
    try:
        return await _client().scenes()
    except OBSError as exc:
        _raise_obs_http(exc)


@router.post("/obs/scene")
async def obs_scene(payload: SceneSwitchRequest) -> Dict:
    try:
        return await _client().set_scene(payload.scene_name)
    except OBSError as exc:
        _raise_obs_http(exc)


@router.post("/obs/stream/toggle")
async def obs_stream_toggle() -> Dict:
    try:
        return await _client().toggle_stream()
    except OBSError as exc:
        _raise_obs_http(exc)


@router.post("/obs/record/toggle")
async def obs_record_toggle() -> Dict:
    try:
        return await _client().toggle_record()
    except OBSError as exc:
        _raise_obs_http(exc)
