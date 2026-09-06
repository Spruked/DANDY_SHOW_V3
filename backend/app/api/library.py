import re
from typing import Dict, Any, List

from fastapi import APIRouter, Body, HTTPException

from ..services.storage.episode_store import (
    list_episode_summaries,
    load_episode_detail,
    load_script,
    save_episode_config,
    save_script,
    save_script_version,
)


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
    from .production import _CANCEL_EVENTS, _CANCEL_LOCK

    detail = load_episode_detail(episode_id)
    with _CANCEL_LOCK:
        detail["job_active"] = detail.get("job_id") in _CANCEL_EVENTS
    if not detail["job_active"] and detail.get("status") in {"producing", "generating_script", "cancel_requested"}:
        detail["previous_status"] = detail["status"]
        detail["status"] = "interrupted"
        detail["error"] = "No active job exists in this backend process. The saved job was interrupted; retry when ready."
    return detail


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
