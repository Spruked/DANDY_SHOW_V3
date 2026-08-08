from typing import Dict, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..services.mixer import (
    VoiceMeeterConnectionError,
    VoiceMeeterError,
    VoiceMeeterRequestError,
    VoiceMeeterService,
)


router = APIRouter(tags=["mixer"])
service = VoiceMeeterService()


class MixerChannelPatchRequest(BaseModel):
    channel_id: Optional[str] = None
    gain: Optional[float] = None
    mute: Optional[bool] = None
    solo: Optional[bool] = None
    eq: Optional[bool] = None
    gate: Optional[float] = None
    comp: Optional[float] = None
    a1: Optional[bool] = None
    a2: Optional[bool] = None
    b1: Optional[bool] = None
    b2: Optional[bool] = None


class MixerMasterPatchRequest(BaseModel):
    gain: Optional[float] = None
    mute: Optional[bool] = None


class MixerBusPatchRequest(BaseModel):
    gain: Optional[float] = None
    mute: Optional[bool] = None
    mono: Optional[bool] = None


class MixerMacroRequest(BaseModel):
    state: Optional[bool] = None


def _raise_http(exc: VoiceMeeterError) -> None:
    if isinstance(exc, VoiceMeeterConnectionError):
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if isinstance(exc, VoiceMeeterRequestError):
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/mixer/status")
async def mixer_status() -> Dict:
    try:
        return service.status()
    except VoiceMeeterError as exc:
        _raise_http(exc)


@router.get("/mixer/state")
async def mixer_state() -> Dict:
    try:
        return service.state()
    except VoiceMeeterError as exc:
        _raise_http(exc)


@router.get("/mixer/levels")
async def mixer_levels() -> Dict:
    try:
        return service.levels()
    except VoiceMeeterError as exc:
        _raise_http(exc)


@router.post("/mixer/channel")
async def mixer_channel(payload: MixerChannelPatchRequest) -> Dict:
    try:
        if not payload.channel_id:
            raise HTTPException(status_code=400, detail="channel_id is required")
        return service.set_channel(payload.channel_id, payload.model_dump(exclude_none=True))
    except VoiceMeeterError as exc:
        _raise_http(exc)


@router.post("/mixer/strip/{strip_index}")
async def mixer_strip(strip_index: int, payload: MixerChannelPatchRequest) -> Dict:
    try:
        patch = payload.model_dump(exclude_none=True)
        patch.pop("channel_id", None)
        return service.set_strip(strip_index, patch)
    except VoiceMeeterError as exc:
        _raise_http(exc)


@router.post("/mixer/master")
async def mixer_master(payload: MixerMasterPatchRequest) -> Dict:
    try:
        return service.set_master(payload.model_dump(exclude_none=True))
    except VoiceMeeterError as exc:
        _raise_http(exc)


@router.post("/mixer/bus/{bus_index}")
async def mixer_bus(bus_index: int, payload: MixerBusPatchRequest) -> Dict:
    try:
        return service.set_bus(bus_index, payload.model_dump(exclude_none=True))
    except VoiceMeeterError as exc:
        _raise_http(exc)


@router.post("/mixer/macro/{button_index}")
async def mixer_macro(button_index: int, payload: MixerMacroRequest) -> Dict:
    try:
        return service.trigger_macro(button_index, payload.state)
    except VoiceMeeterError as exc:
        _raise_http(exc)
