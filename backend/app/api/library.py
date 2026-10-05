import json
import re
import shutil
from pathlib import Path
from typing import Dict, Any, List

from fastapi import APIRouter, Body, HTTPException

from ..services.storage.episode_store import (
    DRAFTS_ROOT,
    JOBS_ROOT,
    list_episode_summaries,
    load_episode_detail,
    load_script,
    save_episode_config,
    save_script,
    save_script_version,
)
from ..core.paths import EPISODES_ROOT


router = APIRouter(tags=["library"])

_SCRIPT_LINE_RE = re.compile(
    r"^\s*(?:#\s*\d+\s*)?(?:\*\*)?"
    r"(PHIL|JIM|HOST|GUEST|INTRO_MALE|INTRO_FEMALE)"
    r"(?:\*\*)?\s*[:\-]?\s*(.+?)\s*$",
    re.IGNORECASE,
)


def _parse_script_text(text: str) -> List[Dict[str, Any]]:
    parsed: List[Dict[str, Any]] = []
    for raw in str(text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        match = _SCRIPT_LINE_RE.match(line)
        if not match:
            continue
        speaker = match.group(1).lower()
        dialogue = match.group(2).strip().strip('"').strip()
        if not dialogue:
            continue
        parsed.append({
            "speaker": speaker,
            "text": dialogue,
            "emotion": "neutral",
            "pause_after": 0.5,
            "generated_by": "script_feed",
        })
    for idx, line in enumerate(parsed, start=1):
        line["line_number"] = idx
    return parsed


def _safe_episode_path(episode_id: str) -> Path:
    episode_id = str(episode_id or "").strip()
    if not episode_id or episode_id in {".", ".."} or Path(episode_id).name != episode_id:
        raise HTTPException(status_code=400, detail="Invalid episode id")
    root = EPISODES_ROOT.resolve()
    candidate = (EPISODES_ROOT / episode_id).resolve()
    if candidate.parent != root:
        raise HTTPException(status_code=400, detail="Invalid episode id")
    return candidate


@router.get("/library")
async def library() -> Dict:
    return {"episodes": list_episode_summaries()}


@router.get("/episodes")
async def episodes() -> Dict:
    return {"episodes": list_episode_summaries()}


@router.delete("/episodes/{episode_id}")
async def delete_episode(episode_id: str) -> Dict[str, Any]:
    """Delete one episode and only the draft/job records owned by that episode."""
    episode_path = _safe_episode_path(episode_id)
    draft_path = DRAFTS_ROOT / f"{episode_id}.json"

    if not episode_path.exists() and not draft_path.exists():
        raise HTTPException(status_code=404, detail="Episode not found")

    removed_jobs: List[str] = []
    if JOBS_ROOT.exists():
        for job_path in JOBS_ROOT.glob("*.json"):
            try:
                payload = json.loads(job_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if str(payload.get("episode_id", "")) != episode_id:
                continue
            job_path.unlink(missing_ok=True)
            removed_jobs.append(job_path.name)

    if episode_path.exists():
        if not episode_path.is_dir():
            raise HTTPException(status_code=409, detail="Episode path is not a directory")
        shutil.rmtree(episode_path)

    draft_path.unlink(missing_ok=True)

    return {
        "status": "deleted",
        "episode_id": episode_id,
        "removed_job_records": len(removed_jobs),
    }


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
    from ..schemas.episode import EpisodeCreateRequest
    from pydantic import ValidationError
    try:
        EpisodeCreateRequest(**{**detail.get("config", {}), **payload, "episode_id": episode_id})
    except ValidationError as exc:
        raise HTTPException(422, str(exc)) from exc
    updated = save_episode_config(episode_id, payload)
    return {"episode_id": episode_id, "config": updated}


@router.post("/episodes/{episode_id}/replace-script")
async def replace_entire_script(
    episode_id: str,
    payload: Dict[str, Any] = Body(...),
) -> Dict[str, Any]:
    """Replace the current script without invoking an LLM.

    Accepts either a structured ``script`` list or plain ``text`` containing
    PHIL:/JIM: lines. The currently active script is snapshotted before the
    replacement is written, and the replacement itself is versioned by
    ``save_script``.
    """
    detail = load_episode_detail(episode_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Episode not found")

    incoming = payload.get("script")
    if isinstance(incoming, list):
        script: List[Dict[str, Any]] = []
        for raw in incoming:
            if not isinstance(raw, dict):
                continue
            text = str(raw.get("text", raw.get("line", ""))).strip()
            if not text:
                continue
            speaker = str(raw.get("speaker", "phil")).lower().strip()
            script.append({
                **raw,
                "speaker": speaker,
                "text": text,
                "emotion": raw.get("emotion", "neutral"),
                "pause_after": float(raw.get("pause_after", 0.5) or 0.5),
                "generated_by": "script_feed",
            })
        for idx, line in enumerate(script, start=1):
            line["line_number"] = idx
    else:
        script = _parse_script_text(str(payload.get("text", "")))

    if not script:
        raise HTTPException(
            status_code=400,
            detail="No script lines found. Use PHIL: ... and JIM: ... on separate lines.",
        )

    current_script = load_script(episode_id).get("script", [])
    if current_script:
        save_script_version(episode_id, current_script)

    save_script(episode_id, script)
    return {
        "status": "script_ready",
        "episode_id": episode_id,
        "script": script,
        "line_count": len(script),
        "word_count": sum(len(str(line.get("text", "")).split()) for line in script),
        "generation_mode": "script_feed",
    }
