from typing import Dict, List, Any

from fastapi import APIRouter, Body

from ..services.production.dandy_harmonizer import DandyHarmonizer
from ..services.production.personality_loader import load_personality

router = APIRouter(tags=["conversation"])


def _get_harmonizer() -> DandyHarmonizer:
    # lightweight instantiation; personalities are cached by loader
    phil = load_personality("phil")
    jim = load_personality("jim")
    return DandyHarmonizer(phil, jim)


@router.post("/conversation/segment")
async def conversation_segment(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    topic = payload.get("topic", "general")
    context = payload.get("context") or {}
    personality = payload.get("personality_settings") or {}

    harmonizer = _get_harmonizer()
    if personality:
        for skg in (harmonizer.phil, harmonizer.jim):
            if hasattr(skg, "set_personality_tuning"):
                try:
                    skg.set_personality_tuning(personality)
                except Exception:
                    pass

    transcript: List[Dict[str, Any]] = harmonizer.generate_segment(topic, context)
    return {"topic": topic, "exchanges": transcript}
