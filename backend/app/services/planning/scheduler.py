from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

from ...core.paths import PROJECT_ROOT
from .registry import ROOT, _slug, list_businesses, list_products

ROOT_CAMPAIGNS = PROJECT_ROOT / "campaigns"
PLANS = ROOT_CAMPAIGNS / "plans"


def _read_rules() -> dict:
    path = ROOT_CAMPAIGNS / "rules.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {
        "ad_schedule": ["pre_roll_1", "pre_roll_2", "mid_roll_1", "mid_roll_2", "mid_roll_3", "mid_roll_4", "post_roll_1"],
        "blackout_dates": []
    }


def list_plans() -> list[dict]:
    PLANS.mkdir(parents=True, exist_ok=True)
    rows = []
    for path in sorted(PLANS.glob("episode-*.json")):
        rows.append(json.loads(path.read_text(encoding="utf-8")))
    return rows


def create_plan(episode_number: int, featured_product: str, release_date: str,
                business_slug: str, ad_assignments: list[str] | None = None) -> dict:
    if date.fromisoformat(release_date) < date.today():
        raise ValueError("Release date cannot be in the past")
    PLANS.mkdir(parents=True, exist_ok=True)
    schedule = ["pre_roll_1", "pre_roll_2", "mid_roll_1", "mid_roll_2", "mid_roll_3", "mid_roll_4", "post_roll_1"]
    plan = {"episode_number": episode_number, "business_slug": _slug(business_slug),
            "featured_product": _slug(featured_product), "ad_assignments": ad_assignments or [],
            "ad_slots": [{"slot_id": slot, "placement": slot, "status": "reserved", "assigned_ad_id": None}
                         for slot in schedule], "release_date": release_date}
    (PLANS / f"episode-{episode_number:04d}.json").write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
    return plan


def generate_calendar(start_date: str, weeks: int = 4) -> list[dict]:
    rules = _read_rules()
    businesses = list_businesses()
    products = [(b["slug"], p) for b in businesses for p in list_products(b["slug"])]
    if not products:
        return []
    blackout = set(rules.get("blackout_dates", []))
    cursor = date.fromisoformat(start_date)
    result = []
    episode = max([p["episode_number"] for p in list_plans()] or [0]) + 1
    for offset in range(max(1, weeks) * 1):
        release = cursor + timedelta(days=7 * offset)
        if release.isoformat() in blackout:
            continue
        business, product = products[offset % len(products)]
        result.append(create_plan(episode, product["slug"], release.isoformat(), business))
        episode += 1
    return result
