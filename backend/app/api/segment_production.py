"""Segment-aware production routing.

For new 1-15 minute targets, production uses the validated script exactly as
written: no 5,000-word floor, no canned expansion, and no automatic ad
insertion. Ads are intended to be assembled between completed segments later.
Legacy targets above 15 minutes delegate to the established production route.
"""

from __future__ import annotations

from datetime import datetime
from typing import Dict

from fastapi import APIRouter, BackgroundTasks, Body, HTTPException, Query

from .production import (
    _assert_llm_script_publishable,
    _run_produce_background,
    _sanitize_script,
    _script_as_text,
    produce_episode as legacy_produce_episode,
)
from ..services.storage.episode_store import (
    episode_dir,
    load_episode_detail,
    load_job,
    save_json,
)


router = APIRouter(tags=["segment-production"])


@router.post("/episodes/produce")
async def produce_segment_or_legacy(
    background_tasks: BackgroundTasks,
    job_id: str = Query(...),
    payload: Dict | None = Body(default=None),
):
    job = load_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    detail = load_episode_detail(job["episode_id"])
    config = detail.get("config", {}) or {}
    target_duration = int(config.get("target_duration") or 600)

    # Preserve existing long-form behavior for saved legacy episodes.
    if target_duration > 15 * 60:
        return await legacy_produce_episode(
            background_tasks=background_tasks,
            job_id=job_id,
            payload=payload,
        )

    script = detail.get("script", [])
    if not script:
        raise HTTPException(status_code=400, detail="No script found. Generate script first.")

    script = _sanitize_script(script)
    require_llm = config.get("generation_mode") != "script_feed"

    # Segment mode deliberately does not length-pad or template-expand. The
    # generation quality gate owns target-length validation; production renders
    # the approved script that is actually present.
    est_words = sum(len(str(line.get("text", "")).split()) for line in script)
    if est_words <= 0:
        raise HTTPException(status_code=400, detail="Segment script contains no spoken words.")

    try:
        script_meta = _assert_llm_script_publishable(script, require_llm=require_llm)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    title = config.get("title") or job["episode_id"]
    topic = config.get("topic") or title
    script_text = _script_as_text(script)
    personality_settings = (payload or {}).get("personality_settings") if payload else None
    voice_settings = (payload or {}) if payload else {}
    writer_engine = str(script_meta.get("writer_engine", "unknown"))
    bridge_was_reachable = writer_engine in {"llm_bridge", "governance_bridge", "llamacpp"}
    target_minutes = max(1, min(15, round(target_duration / 60)))

    save_json(
        episode_dir(job["episode_id"]) / "status.json",
        {
            "status": "producing",
            "updated_at": datetime.now().isoformat(),
            "job_id": job_id,
            "production_mode": "segment",
            "target_minutes": target_minutes,
            "writer_engine": writer_engine,
            "bridge_reachable_at_start": bridge_was_reachable,
            "fallback_used": script_meta.get("fallback_used"),
            "line_source_counts": script_meta.get("line_source_counts", {}),
        },
    )

    background_tasks.add_task(
        _run_produce_background,
        episode_id=job["episode_id"],
        job_id=job_id,
        script=script,
        title=title,
        topic=topic,
        script_text=script_text,
        personality_settings=personality_settings,
        voice_settings=voice_settings,
        writer_engine=writer_engine,
        bridge_reachable_at_start=bridge_was_reachable,
    )

    return {
        "status": "queued",
        "mode": "segment",
        "job_id": job_id,
        "episode_id": job["episode_id"],
        "target_minutes": target_minutes,
        "word_count": est_words,
        "message": "Segment production started in background.",
    }
