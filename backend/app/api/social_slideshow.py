from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Dict, Any

from fastapi import APIRouter, HTTPException, Query

from ..schemas.social_visual import Slide, Slideshow, SaveSlideshowRequest, RenderSlideshowRequest
from ..services.social.slideshow_renderer import render_slideshow_job
from ..core.paths import EPISODES_ROOT

router = APIRouter(prefix="/api/social/slideshow", tags=["social-slideshow"])


def _slideshow_path(episode_id: str) -> Path:
    p = EPISODES_ROOT / episode_id / "slideshow.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _load_script(episode_id: str) -> Dict[str, Any]:
    script = EPISODES_ROOT / episode_id / "script.json"
    if not script.exists():
        return {}
    return json.loads(script.read_text(encoding="utf-8"))


@router.get("/load")
def load_slideshow(episode_id: str = Query(...)):
    path = _slideshow_path(episode_id)
    if not path.exists():
        return {"episode_id": episode_id, "slides": []}
    return json.loads(path.read_text(encoding="utf-8"))


@router.post("/save")
def save_slideshow(req: SaveSlideshowRequest):
    payload = Slideshow(episode_id=req.episode_id, slides=req.slides).model_dump()
    _slideshow_path(req.episode_id).write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return {"ok": True, "count": len(req.slides)}


@router.post("/auto-generate")
def auto_generate(episode_id: str = Query(...)):
    """Build slides from the episode script. Uses segments if present; falls back to script lines."""
    script = _load_script(episode_id)
    slides: list[Slide] = []

    segments = script.get("segments") or []
    if segments:
        for i, seg in enumerate(segments):
            slides.append(Slide(
                id=f"slide_{uuid.uuid4().hex[:8]}",
                title=seg.get("title", f"Segment {i + 1}"),
                subtitle=seg.get("subtitle", ""),
                body=seg.get("summary", ""),
                start=float(seg.get("start", 0.0)),
                end=float(seg.get("end", seg.get("start", 0.0) + 15.0)),
            ))
    else:
        # Build topic cards from script lines by grouping on speaker changes
        lines = script.get("script", [])
        title = script.get("title", episode_id)
        slides.append(Slide(
            id=f"slide_{uuid.uuid4().hex[:8]}",
            title=title,
            subtitle="The Phil and Jim Dandy Show",
            start=0.0,
            end=15.0,
        ))
        # One card per ~10 lines as topic beats
        chunk = 10
        for i in range(0, len(lines), chunk):
            group = lines[i:i + chunk]
            first_line = group[0].get("text", "") if group else ""
            snippet = first_line[:60] + ("…" if len(first_line) > 60 else "")
            slides.append(Slide(
                id=f"slide_{uuid.uuid4().hex[:8]}",
                title=f"Part {i // chunk + 1}",
                subtitle=snippet,
                start=float(i * 3),
                end=float((i + chunk) * 3),
            ))

    payload = Slideshow(episode_id=episode_id, slides=slides).model_dump()
    _slideshow_path(episode_id).write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


@router.post("/snap")
def snap_to_script(episode_id: str = Query(...), slide_id: str = Query(...)):
    """Suggest start/end by matching nearest script segment."""
    path = _slideshow_path(episode_id)
    if not path.exists():
        raise HTTPException(404, "slideshow not found")

    data = json.loads(path.read_text(encoding="utf-8"))
    target = next((s for s in data["slides"] if s["id"] == slide_id), None)
    if not target:
        raise HTTPException(404, "slide not found")

    script = _load_script(episode_id)
    segments = script.get("segments") or []
    if not segments:
        return {"start": target["start"], "end": target["end"]}

    nearest = min(segments, key=lambda s: abs(float(s.get("start", 0)) - target["start"]))
    return {"start": float(nearest["start"]), "end": float(nearest.get("end", nearest["start"] + 15))}


@router.post("/render")
def render(req: RenderSlideshowRequest):
    path = _slideshow_path(req.episode_id)
    if not path.exists():
        raise HTTPException(404, "save slideshow before rendering")

    out = render_slideshow_job(
        episode_id=req.episode_id,
        slideshow_path=path,
        aspect=req.aspect,
        fmt=req.format,
    )
    return {"ok": True, "download_url": out["url"], "path": out["path"]}
