"""Compatibility route for segment production.

All episode durations use the same approved-production gate. Keeping this route
registered first preserves the existing API URL while delegating to the single
production implementation.
"""

from typing import Dict

from fastapi import APIRouter, BackgroundTasks, Body, Query

from .production import produce_episode as approved_produce_episode


router = APIRouter(tags=["segment-production"])


@router.post("/episodes/produce")
async def produce_segment_or_legacy(
    background_tasks: BackgroundTasks,
    job_id: str = Query(...),
    payload: Dict | None = Body(default=None),
):
    return await approved_produce_episode(
        background_tasks=background_tasks,
        job_id=job_id,
        payload=payload,
    )
