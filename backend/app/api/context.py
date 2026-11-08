"""Document context and external script handoff endpoints."""
from io import BytesIO
from typing import Literal
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, model_validator
from ..services.authoring.context import build_context, inspect_sources
from ..services.authoring.direction import OwnerDirection, current_direction, save_direction
from ..services.storage.episode_store import episode_dir, load_episode_detail, save_asset_upload

router = APIRouter(tags=['episode-context'])


@router.get('/authoring/ocr/status')
def local_ocr_status():
    from ..services.authoring.ocr import ocr_status
    return ocr_status()


class ShortCopyRequest(BaseModel):
    kind: Literal['ad', 'post']
    facts: str = Field(min_length=1, max_length=12000)
    instructions: str = Field(default='', max_length=2000)


@router.post('/authoring/short-copy')
def short_copy(payload: ShortCopyRequest):
    from ..services.authoring.short_copy import generate_short_copy
    try:
        return {'kind': payload.kind, 'text': generate_short_copy(payload.kind, payload.facts, payload.instructions)}
    except Exception as exc:
        raise HTTPException(502, str(exc)) from exc


class Curation(BaseModel):
    priority_source_ids: list[str] = Field(default_factory=list, max_length=200)
    model_name: str = Field(default='External LLM', max_length=200)
    context_window_tokens: int = Field(default=32768, ge=1024, le=2000000)
    reserved_output_tokens: int = Field(default=4096, ge=256, le=1000000)

    @model_validator(mode='after')
    def valid_budget(self):
        if self.reserved_output_tokens >= self.context_window_tokens:
            raise ValueError('Output reservation must be smaller than the context window')
        return self


class ContextRequest(BaseModel):
    brief: str = Field(default='', max_length=30000)
    source_ids: list[str] | None = None
    owner_direction: OwnerDirection | None = None
    expected_direction_revision: str | None = None
    curation: Curation = Field(default_factory=Curation)


class InspectRequest(BaseModel):
    source_ids: list[str] | None = None


class DirectionRequest(BaseModel):
    owner_direction: OwnerDirection
    expected_direction_revision: str | None = None


class TextSource(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    text: str = Field(min_length=1, max_length=1000000)
    source_url: str = Field(default='', max_length=2000)


def require_episode(episode_id):
    detail = load_episode_detail(episode_id)
    if not detail.get('config'):
        raise HTTPException(404, 'Episode not found')
    return detail


@router.post('/episodes/{episode_id}/context/sources/text')
def add_text_source(episode_id: str, payload: TextSource):
    require_episode(episode_id)
    return save_asset_upload(episode_id, filename=payload.title + '.txt', content_type='text/plain',
                             file_stream=BytesIO(payload.text.encode('utf-8')), label=payload.title,
                             description=payload.source_url, role='source')


@router.post('/episodes/{episode_id}/context')
def generate_context(episode_id: str, payload: ContextRequest):
    require_episode(episode_id)
    try:
        return build_context(episode_id, payload.brief, payload.source_ids,
                             payload.owner_direction.model_dump() if payload.owner_direction is not None else None,
                             payload.expected_direction_revision, payload.curation.model_dump())
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post('/episodes/{episode_id}/context/inspect')
def inspect_context_sources(episode_id: str, payload: InspectRequest):
    require_episode(episode_id)
    try:
        return inspect_sources(episode_id, payload.source_ids)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get('/episodes/{episode_id}/context')
def latest_context(episode_id: str):
    require_episode(episode_id)
    path = episode_dir(episode_id) / 'context_packages' / 'latest.json'
    if not path.exists():
        return None
    import json
    return json.loads(path.read_text(encoding='utf-8'))


@router.get('/episodes/{episode_id}/context/direction')
def get_owner_direction(episode_id: str):
    require_episode(episode_id)
    return current_direction(episode_id)


@router.get('/episodes/{episode_id}/context/reference')
def context_reference(episode_id: str):
    detail = require_episode(episode_id)
    from ..services.authoring.pack import show_bible, ad_slots, FORMAT_CONTRACT
    return {'show_bible': show_bible(), 'format_contract': FORMAT_CONTRACT, 'ad_slots': ad_slots(episode_id),
            'episode_brief': detail.get('config', {}).get('description', '')}


@router.put('/episodes/{episode_id}/context/direction')
def update_owner_direction(episode_id: str, payload: DirectionRequest):
    require_episode(episode_id)
    try:
        return save_direction(episode_id, payload.owner_direction.model_dump(), payload.expected_direction_revision)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
