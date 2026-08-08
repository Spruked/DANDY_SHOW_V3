from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query

from ..schemas.social_visual import AdCard, AdCardCollection, SaveAdCardsRequest, RenderAdCardRequest
from ..services.social.slideshow_renderer import render_adcard_job
from ..core.paths import EPISODES_ROOT, PROJECT_ROOT

router = APIRouter(prefix="/api/social/adcards", tags=["social-adcards"])

GLOBAL_CARDS_PATH = PROJECT_ROOT / "social" / "ad_cards.json"


def _cards_path(episode_id: str | None) -> Path:
    if episode_id:
        p = EPISODES_ROOT / episode_id / "ad_cards.json"
    else:
        p = GLOBAL_CARDS_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


@router.get("/load")
def load_cards(episode_id: str | None = Query(default=None)):
    path = _cards_path(episode_id)
    if not path.exists():
        return {"episode_id": episode_id, "cards": []}
    return json.loads(path.read_text(encoding="utf-8"))


@router.post("/save")
def save_cards(req: SaveAdCardsRequest):
    payload = AdCardCollection(episode_id=req.episode_id, cards=req.cards).model_dump()
    _cards_path(req.episode_id).write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return {"ok": True, "count": len(req.cards)}


def _find_card(card_id: str) -> AdCard:
    search_paths = list(EPISODES_ROOT.rglob("ad_cards.json"))
    if GLOBAL_CARDS_PATH.exists():
        search_paths.append(GLOBAL_CARDS_PATH)
    for path in search_paths:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            for c in data.get("cards", []):
                if c["id"] == card_id:
                    return AdCard(**c)
        except Exception:
            continue
    raise HTTPException(404, f"card {card_id} not found")


@router.post("/render")
def render(req: RenderAdCardRequest):
    card = _find_card(req.card_id)
    out = render_adcard_job(card=card, aspect=req.aspect, fmt=req.format)
    return {"ok": True, "download_url": out["url"], "path": out["path"]}
