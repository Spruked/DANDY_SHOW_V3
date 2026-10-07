"""Versioned canonical scripts and the human-approved production handoff."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from ...core.paths import PROJECT_ROOT
from ...core.settings import load_project_config, load_qwen_tts_config, load_voices_config
from ..storage.asset_library import list_library_assets
from ..storage.episode_store import (
    episode_dir, list_assets, list_canonical_scripts, load_canonical_script,
    load_episode_detail, load_media_cues, save_json,
)
from .production_editor import ArbiterMorb, EditorialMorb, PerformanceMorb, _spoken_text


def _digest(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _atomic_json(path: Path, payload: dict[str, Any], *, exclusive: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if exclusive:
        with path.open("x", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)
        return
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(temporary, path)


def _editor_root(episode_id: str) -> Path:
    return episode_dir(episode_id) / "production_editor"


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _settings_snapshot(episode_id: str) -> dict[str, Any]:
    detail = load_episode_detail(episode_id)
    assets = _asset_registry(episode_id)
    cue_assets = []
    for cue in detail.get("media_cues", []):
        asset = assets.get(str(cue.get("asset_id") or ""))
        path = Path(str((asset or {}).get("stored_path") or ""))
        cue_assets.append({"asset_id": cue.get("asset_id"),
                           "hash": _hash_file(path) if path.is_file() else None})
    ad_assets = []
    for ad in detail.get("ads", []):
        path = Path(str(ad.get("audio_file") or ""))
        ad_assets.append({"ad_id": ad.get("ad_id"),
                          "audio_hash": _hash_file(path) if path.is_file() else None})
    return {
        "episode_config": detail.get("config", {}),
        "ads": detail.get("ads", []),
        "ad_settings": detail.get("ad_settings", {}),
        "saved_media_cues": detail.get("media_cues", []),
        "project_config": load_project_config(),
        "voices_config": load_voices_config(),
        "qwen_tts_config": load_qwen_tts_config(),
        "saved_cue_asset_hashes": cue_assets,
        "ad_audio_hashes": ad_assets,
    }


def _asset_registry(episode_id: str) -> dict[str, dict[str, Any]]:
    assets = {item["asset_id"]: item for item in list_library_assets() if item.get("asset_id")}
    assets.update({item["asset_id"]: item for item in list_assets(episode_id) if item.get("asset_id")})
    return assets


def _validate_cues(episode_id: str, cues: Any) -> list[dict[str, Any]]:
    if not isinstance(cues, list):
        raise ValueError("Production cues must be a list")
    registry = _asset_registry(episode_id)
    result = []
    for cue in cues:
        if not isinstance(cue, dict):
            raise ValueError("Each production cue must be an object")
        asset_id = str(cue.get("asset_id") or "")
        asset = registry.get(asset_id)
        if not asset:
            raise ValueError(f"Production cue references an unknown asset: {asset_id}")
        if asset.get("asset_type") != "audio":
            raise ValueError(f"Production cue asset is not audio: {asset_id}")
        path = Path(str(asset.get("stored_path") or ""))
        if not path.is_file():
            raise ValueError(f"Production cue asset file is missing: {asset_id}")
        normalized = copy.deepcopy(cue)
        normalized["asset_id"] = asset_id
        normalized["asset_hash"] = _hash_file(path)
        result.append(normalized)
    return result


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _production_hash(script: list[dict[str, Any]], cues: list[dict[str, Any]]) -> str:
    return _digest({"script": script, "media_cues": cues})


def _state_path(episode_id: str) -> Path:
    return _editor_root(episode_id) / "state.json"


def _preview_root(episode_id: str) -> Path:
    return episode_dir(episode_id) / "preview"


def _preview_pointer_path(episode_id: str, canonical_version_id: str) -> Path:
    if not re.fullmatch(r"canonical_v\d{4,}", canonical_version_id):
        raise ValueError("Invalid Preview canonical version ID")
    return _preview_root(episode_id) / "reviews" / canonical_version_id / "active.json"


def _preview_file(episode_id: str, canonical_version_id: str, review_id: str) -> Path:
    if not re.fullmatch(r"canonical_v\d{4,}", canonical_version_id) or not re.fullmatch(r"preview_v\d{4,}", review_id):
        raise ValueError("Invalid Preview review address")
    return _preview_root(episode_id) / "reviews" / canonical_version_id / f"{review_id}.json"


def _load_state(episode_id: str) -> dict[str, Any]:
    return _read_json(_state_path(episode_id)) or {"episode_id": episode_id}


def canonical_versions(episode_id: str) -> dict[str, Any]:
    active = load_canonical_script(episode_id)
    versions = list_canonical_scripts(episode_id)
    return {"episode_id": episode_id, "active_version_id": active["version_id"],
            "versions": versions}


_PREVIEW_MARKS = {"none", "needs_attention", "possible_cut", "strong", "weak"}


def _preview_hash(review: dict[str, Any]) -> str:
    return _digest({"canonical_version_id": review.get("canonical_version_id"),
                    "canonical_source_hash": review.get("canonical_source_hash"),
                    "overall_notes": review.get("overall_notes", ""),
                    "line_reviews": review.get("line_reviews", {}),
                    "section_notes": review.get("section_notes", {})})


def get_preview_review(episode_id: str, canonical_version_id: str) -> dict[str, Any]:
    canonical = load_canonical_script(episode_id, canonical_version_id)
    pointer = _read_json(_preview_pointer_path(episode_id, canonical_version_id)) or {}
    if pointer.get("canonical_version_id") == canonical_version_id:
        review = _read_json(_preview_file(episode_id, canonical_version_id, str(pointer.get("review_id") or "")))
        if review:
            if review.get("canonical_source_hash") != canonical.get("canonical_hash"):
                raise ValueError("Preview review source hash does not match its canonical snapshot")
            return {**review, "saved": True}
    return {
        "episode_id": episode_id, "canonical_version_id": canonical_version_id,
        "canonical_source_hash": canonical["canonical_hash"], "review_id": None,
        "preview_hash": None, "overall_notes": "", "section_notes": {},
        "line_reviews": {str(line.get("canonical_line_id")): {"mark": "none", "note": ""}
                         for line in canonical.get("script", []) if line.get("canonical_line_id")},
        "saved": False,
    }


def selected_preview_review(episode_id: str) -> dict[str, Any] | None:
    pointer = _read_json(_preview_root(episode_id) / "current.json") or {}
    version_id = str(pointer.get("canonical_version_id") or "")
    if not version_id:
        return None
    return get_preview_review(episode_id, version_id)


def save_preview_review(episode_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    version_id = str(payload.get("canonical_version_id") or "")
    canonical = load_canonical_script(episode_id, version_id)
    if payload.get("canonical_source_hash") != canonical.get("canonical_hash"):
        raise ValueError("Canonical snapshot changed; reload Preview before saving notes")
    lines = canonical.get("script", [])
    valid_line_ids = {str(line.get("canonical_line_id")) for line in lines if line.get("canonical_line_id")}
    raw_reviews = payload.get("line_reviews", {})
    raw_sections = payload.get("section_notes", {})
    if not isinstance(raw_reviews, dict) or set(raw_reviews) - valid_line_ids:
        raise ValueError("Preview review references an unknown canonical line")
    if not isinstance(raw_sections, dict):
        raise ValueError("Section notes must be an object keyed by section")
    overall_notes = str(payload.get("overall_notes") or "").strip()
    if len(overall_notes) > 20000:
        raise ValueError("Overall Preview notes exceed 20,000 characters")
    line_reviews = {}
    for line_id in valid_line_ids:
        raw = raw_reviews.get(line_id, {})
        if not isinstance(raw, dict):
            raise ValueError(f"Preview mark for {line_id} must be an object")
        mark = str(raw.get("mark") or "none")
        note = str(raw.get("note") or "").strip()
        if mark not in _PREVIEW_MARKS:
            raise ValueError(f"Unsupported Preview mark: {mark}")
        if len(note) > 4000:
            raise ValueError(f"Preview note for {line_id} exceeds 4,000 characters")
        line_reviews[line_id] = {"mark": mark, "note": note}
    section_notes = {}
    for section_id, value in raw_sections.items():
        section_id = str(section_id).strip()
        note = str(value or "").strip()
        if not section_id or len(section_id) > 100 or len(note) > 8000:
            raise ValueError("Section note has an invalid key or exceeds 8,000 characters")
        section_notes[section_id] = note
    existing = list((_preview_root(episode_id) / "reviews" / version_id).glob("preview_v*.json"))
    numbers = [int(match.group(1)) for path in existing
               if (match := re.fullmatch(r"preview_v(\d+)\.json", path.name))]
    review_id = f"preview_v{max(numbers, default=0) + 1:04d}"
    review = {
        "episode_id": episode_id, "review_id": review_id,
        "canonical_version_id": version_id,
        "canonical_source_hash": canonical["canonical_hash"],
        "overall_notes": overall_notes, "line_reviews": line_reviews,
        "section_notes": section_notes, "updated_at": datetime.now().isoformat(),
    }
    review["preview_hash"] = _preview_hash(review)
    _atomic_json(_preview_file(episode_id, version_id, review_id), review, exclusive=True)
    _atomic_json(_preview_pointer_path(episode_id, version_id), {
        "canonical_version_id": version_id, "review_id": review_id,
        "preview_hash": review["preview_hash"], "updated_at": review["updated_at"],
    })
    _atomic_json(_preview_root(episode_id) / "current.json", {
        "canonical_version_id": version_id, "review_id": review_id,
        "preview_hash": review["preview_hash"], "updated_at": review["updated_at"],
    })
    return {**review, "saved": True}


def _current_preview_review(episode_id: str, canonical_version_id: str) -> dict[str, Any]:
    pointer = _read_json(_preview_pointer_path(episode_id, canonical_version_id)) or {}
    if pointer.get("canonical_version_id") != canonical_version_id or not pointer.get("review_id"):
        raise ValueError("Preview is required for this canonical version before opening Production Editor")
    review = _read_json(_preview_file(episode_id, canonical_version_id, str(pointer["review_id"])))
    canonical = load_canonical_script(episode_id, canonical_version_id)
    if not review or review.get("canonical_source_hash") != canonical.get("canonical_hash"):
        raise ValueError("Saved Preview review no longer matches its canonical snapshot")
    if _preview_hash(review) != review.get("preview_hash"):
        raise ValueError("Saved Preview review failed its integrity check")
    return review


def _remap_cues_to_lines(cues: list[dict[str, Any]], canonical_lines: list[dict[str, Any]],
                         production_lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    source_ids = [line.get("canonical_line_id") for line in canonical_lines]
    production_by_source = {line.get("source_canonical_line_id"): line for line in production_lines
                           if line.get("source_canonical_line_id")}
    mapped = []
    for raw in cues:
        cue = copy.deepcopy(raw)
        if cue.get("line_number") is not None:
            try:
                zero_index = int(cue["line_number"])
                source_id = source_ids[zero_index] if 0 <= zero_index < len(source_ids) else None
            except (TypeError, ValueError):
                source_id = None
            if source_id:
                target = production_by_source.get(source_id)
                if target:
                    cue["anchor_line_id"] = target["production_line_id"]
        mapped.append(cue)
    return mapped


def _apply_morbs(episode_id: str, lines: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    assets = _asset_registry(episode_id)
    proposals = EditorialMorb().propose(lines) + PerformanceMorb().propose(lines)
    result = copy.deepcopy(lines)
    ledger = []
    for proposal in proposals:
        index = int(str(proposal["segment_id"]).split("_")[1]) - 1
        decision, authority = ArbiterMorb.decide(proposal, assets, allow_embellish=False)
        line_id = result[index]["production_line_id"]
        entry = {**proposal, "proposal_id": f"{line_id}_{proposal.get('action', 'review').lower()}",
                 "production_line_id": line_id, "decision": decision, "authority": authority,
                 "reviewed": False, "operator_decision": None}
        ledger.append(entry)
        if decision != "accepted":
            continue
        field = proposal.get("field")
        if proposal.get("action") == "NORMALIZE" and field == "text":
            result[index]["spoken_text"] = str(proposal["after"])
        elif proposal.get("action") == "PERFORM" and field == "pause_after":
            result[index]["pause_after"] = float(proposal["after"])
    return result, ledger


def create_draft(episode_id: str, canonical_version_id: str) -> dict[str, Any]:
    canonical = load_canonical_script(episode_id, canonical_version_id)
    preview_review = _current_preview_review(episode_id, canonical_version_id)
    detail = load_episode_detail(episode_id)
    from ...api.production import _enforce_ads_and_structure
    source_lines = canonical.get("script", [])
    structured = _enforce_ads_and_structure(source_lines, detail.get("ads", []), detail.get("ad_settings"))
    lines = []
    for line in structured:
        item = copy.deepcopy(line)
        item["source_canonical_line_id"] = item.get("canonical_line_id")
        item["canonical_line_id"] = item.get("canonical_line_id")
        item["production_line_id"] = f"pl_{uuid.uuid4().hex}"
        item["original_text"] = str(item.get("text", ""))
        item["spoken_text"] = str(item.get("spoken_text") or item.get("text", ""))
        item.setdefault("delivery_notes", "")
        item.setdefault("production_cues", [])
        item["production_cues"] = _validate_cues(episode_id, item["production_cues"])
        item.setdefault("pause_after", 0.4)
        lines.append(item)
    lines, proposals = _apply_morbs(episode_id, lines)
    cues = _remap_cues_to_lines(detail.get("media_cues", []), source_lines, lines)
    cues = _validate_cues(episode_id, cues)
    root = _editor_root(episode_id)
    existing = list(root.joinpath("drafts").glob("draft_*.json")) if root.joinpath("drafts").exists() else []
    revision = len(existing) + 1
    draft_id = f"draft_v{revision:04d}"
    environment = _settings_snapshot(episode_id)
    draft = {
        "episode_id": episode_id, "draft_id": draft_id, "revision": revision,
        "canonical_version_id": canonical["version_id"], "canonical_source_hash": canonical["canonical_hash"],
        "production_copy_hash": _production_hash(lines, cues),
        "environment_hash": _digest(environment), "environment_snapshot": environment,
        "script": lines, "media_cues": cues, "morb_proposals": proposals, "change_ledger": [],
        "preview_review_id": preview_review["review_id"],
        "preview_hash": preview_review["preview_hash"],
        "preview_review": copy.deepcopy(preview_review),
        "created_at": datetime.now().isoformat(), "updated_at": datetime.now().isoformat(),
    }
    _atomic_json(root / "drafts" / f"{draft_id}.json", draft, exclusive=True)
    state = _load_state(episode_id)
    state.update({"episode_id": episode_id, "current_draft_id": draft_id,
                  "current_canonical_version_id": canonical["version_id"],
                  "approval_state": "draft", "updated_at": datetime.now().isoformat()})
    _atomic_json(_state_path(episode_id), state)
    return editor_state(episode_id)


def _diff_draft(before: dict[str, Any], after: dict[str, Any]) -> list[dict[str, Any]]:
    old = {line.get("production_line_id"): line for line in before.get("script", [])}
    new = {line.get("production_line_id"): line for line in after.get("script", [])}
    changes = []
    for line_id in old.keys() - new.keys():
        changes.append({"action": "DELETE", "production_line_id": line_id,
                        "before": old[line_id], "after": None})
    for line_id in new.keys() - old.keys():
        changes.append({"action": "ADD", "production_line_id": line_id,
                        "before": None, "after": new[line_id]})
    fields = ("text", "spoken_text", "speaker", "emotion", "delivery_notes", "pause_after", "production_cues")
    for line_id in old.keys() & new.keys():
        for field in fields:
            if old[line_id].get(field) != new[line_id].get(field):
                changes.append({"action": "EDIT", "production_line_id": line_id,
                                "field": field, "before": old[line_id].get(field),
                                "after": new[line_id].get(field)})
    old_order = [line.get("production_line_id") for line in before.get("script", [])]
    new_order = [line.get("production_line_id") for line in after.get("script", [])]
    if old_order != new_order and set(old_order) == set(new_order):
        changes.append({"action": "REORDER", "before": old_order, "after": new_order})
    if before.get("media_cues", []) != after.get("media_cues", []):
        changes.append({"action": "CUES", "before": before.get("media_cues", []),
                        "after": after.get("media_cues", [])})
    return changes


def save_draft(episode_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    state = _load_state(episode_id)
    draft_id = str(payload.get("draft_id") or state.get("current_draft_id") or "")
    if not re.fullmatch(r"draft_v\d{4,}", draft_id):
        raise ValueError("No active production editor draft")
    path = _editor_root(episode_id) / "drafts" / f"{draft_id}.json"
    current = _read_json(path)
    if not current:
        raise FileNotFoundError("Production editor draft not found")
    if payload.get("canonical_version_id") != current.get("canonical_version_id"):
        raise ValueError("Draft canonical source cannot be changed; create a new editor draft")
    lines = payload.get("script")
    if not isinstance(lines, list) or not lines:
        raise ValueError("Production copy must contain at least one line")
    seen = set()
    allowed_speakers = {"phil", "jim", "bryan", "host", "guest", "announcer_male", "announcer_female", "intro_male", "intro_female"}
    cleaned = []
    for line in lines:
        if not isinstance(line, dict):
            raise ValueError("Each production line must be an object")
        item = copy.deepcopy(line)
        line_id = str(item.get("production_line_id") or "")
        if not line_id or line_id in seen:
            raise ValueError("Production line IDs must be present and unique")
        seen.add(line_id)
        if str(item.get("speaker", "")).lower() not in allowed_speakers:
            raise ValueError(f"Unsupported production speaker: {item.get('speaker')}")
        if not str(item.get("text", "")).strip() or not str(item.get("spoken_text", item.get("text", ""))).strip():
            raise ValueError(f"Production line {line_id} cannot be blank")
        item["text"] = str(item["text"]).strip()
        item["spoken_text"] = str(item.get("spoken_text") or item["text"]).strip()
        item["production_cues"] = _validate_cues(episode_id, item.get("production_cues", []))
        try:
            item["pause_after"] = max(0.0, min(3.0, float(item.get("pause_after", 0.4))))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid pause for line {line_id}") from exc
        cleaned.append(item)
    cues = _validate_cues(episode_id, payload.get("media_cues", []))
    positions = {line["production_line_id"]: index for index, line in enumerate(cleaned)}
    for cue in cues:
        anchor = cue.get("anchor_line_id")
        if anchor:
            if anchor not in positions:
                raise ValueError(f"Production cue anchor line no longer exists: {anchor}")
            cue["line_number"] = positions[anchor]
    proposal_values = payload.get("morb_proposals", current.get("morb_proposals", []))
    known_proposals = {item.get("proposal_id"): item for item in current.get("morb_proposals", [])}
    if not isinstance(proposal_values, list) or {item.get("proposal_id") for item in proposal_values} - set(known_proposals):
        raise ValueError("MORB review contains an unknown proposal")
    proposals = []
    for item in proposal_values:
        known = known_proposals[item["proposal_id"]]
        decision = item.get("operator_decision")
        if decision not in (None, "accept", "reject"):
            raise ValueError("MORB review decision must be accept or reject")
        reviewed = bool(item.get("reviewed"))
        proposal = {**known, "reviewed": reviewed, "operator_decision": decision}
        if reviewed and decision == "reject":
            line = next((entry for entry in cleaned if entry["production_line_id"] == known["production_line_id"]), None)
            if line:
                if known.get("action") == "NORMALIZE":
                    if line.get("spoken_text") == known.get("after"):
                        line["spoken_text"] = str(known.get("before", line.get("text", "")))
                elif known.get("action") == "PERFORM" and known.get("field") == "pause_after":
                    if line.get("pause_after") == known.get("after"):
                        line["pause_after"] = known.get("before")
        proposals.append(proposal)
    updated = copy.deepcopy(current)
    updated["script"] = cleaned
    updated["media_cues"] = cues
    updated["morb_proposals"] = proposals
    updated["production_copy_hash"] = _production_hash(cleaned, cues)
    updated["change_ledger"] = current.get("change_ledger", []) + _diff_draft(current, {"script": cleaned, "media_cues": cues})
    updated["updated_at"] = datetime.now().isoformat()
    _atomic_json(path, updated)
    state.update({"approval_state": "stale" if state.get("current_approved_version_id") else "draft",
                  "updated_at": datetime.now().isoformat()})
    _atomic_json(_state_path(episode_id), state)
    return editor_state(episode_id)


def _approved_path(episode_id: str, version_id: str) -> Path:
    if not re.fullmatch(r"approved_v\d{4,}", version_id):
        raise ValueError("Invalid approved production version ID")
    return _editor_root(episode_id) / "approved" / f"{version_id}.json"


def approve_draft(episode_id: str, draft_id: str) -> dict[str, Any]:
    root = _editor_root(episode_id)
    draft = _read_json(root / "drafts" / f"{draft_id}.json")
    if not draft or draft_id != _load_state(episode_id).get("current_draft_id"):
        raise ValueError("Only the current production editor draft can be approved")
    pending = [item for item in draft.get("morb_proposals", []) if not item.get("reviewed")]
    if pending:
        raise ValueError(f"Review all MORB proposals before approval ({len(pending)} pending)")
    canonical = load_canonical_script(episode_id, draft["canonical_version_id"])
    if canonical.get("canonical_hash") != draft.get("canonical_source_hash"):
        raise ValueError("Canonical source hash changed; reopen the editor from a current canonical snapshot")
    environment = _settings_snapshot(episode_id)
    environment_hash = _digest(environment)
    if environment_hash != draft.get("environment_hash"):
        raise ValueError("Episode, voice, ad, or production settings changed; reopen the editor draft before approval")
    production_hash = _production_hash(draft["script"], draft.get("media_cues", []))
    if production_hash != draft.get("production_copy_hash"):
        raise ValueError("Production copy hash mismatch")
    root.mkdir(parents=True, exist_ok=True)
    approved_dir = root / "approved"
    approved_dir.mkdir(parents=True, exist_ok=True)
    versions = [int(match.group(1)) for path in approved_dir.glob("approved_v*.json")
                if (match := re.fullmatch(r"approved_v(\d+)\.json", path.name))]
    version = max(versions, default=0) + 1
    version_id = f"approved_v{version:04d}"
    approved = {
        "episode_id": episode_id, "approved_version_id": version_id, "version": version,
        "draft_id": draft_id, "canonical_version_id": canonical["version_id"],
        "canonical_source_hash": canonical["canonical_hash"],
        "production_copy_hash": production_hash, "environment_hash": environment_hash,
        "environment_snapshot": environment, "script": copy.deepcopy(draft["script"]),
        "preview_review_id": draft.get("preview_review_id"),
        "preview_hash": draft.get("preview_hash"),
        "preview_review": copy.deepcopy(draft.get("preview_review", {})),
        "media_cues": copy.deepcopy(draft.get("media_cues", [])),
        "change_ledger": copy.deepcopy(draft.get("change_ledger", [])),
        "morb_proposals": copy.deepcopy(draft.get("morb_proposals", [])),
        "approved_at": datetime.now().isoformat(), "approved_by": "local_operator",
    }
    _atomic_json(_approved_path(episode_id, version_id), approved, exclusive=True)
    state = _load_state(episode_id)
    state.update({"current_approved_version_id": version_id, "approved_draft_id": draft_id,
                  "approval_state": "approved", "updated_at": datetime.now().isoformat()})
    _atomic_json(_state_path(episode_id), state)
    return editor_state(episode_id)


def current_approval(episode_id: str) -> tuple[dict[str, Any], str]:
    state = _load_state(episode_id)
    version_id = str(state.get("current_approved_version_id") or "")
    if not version_id:
        raise ValueError("Produce is blocked: approve a production version in Production Editor first")
    approved = _read_json(_approved_path(episode_id, version_id))
    if not approved:
        raise ValueError("Approved production version is missing")
    draft = _read_json(_editor_root(episode_id) / "drafts" / f"{state.get('current_draft_id')}.json")
    if not draft or draft.get("draft_id") != approved.get("draft_id"):
        raise ValueError("Approval is stale: the current editor draft differs from the approved version")
    canonical = load_canonical_script(episode_id, str(approved.get("canonical_version_id") or ""))
    if canonical.get("canonical_hash") != approved.get("canonical_source_hash"):
        raise ValueError("Approval is stale: its canonical source snapshot changed")
    current_preview = _current_preview_review(episode_id, str(approved.get("canonical_version_id") or ""))
    if (current_preview.get("review_id") != approved.get("preview_review_id")
            or current_preview.get("preview_hash") != approved.get("preview_hash")):
        raise ValueError("Approval is stale: Preview notes or flags changed after handoff")
    if _production_hash(draft.get("script", []), draft.get("media_cues", [])) != approved.get("production_copy_hash"):
        raise ValueError("Approval is stale: the production copy changed after approval")
    if _digest(_settings_snapshot(episode_id)) != approved.get("environment_hash"):
        raise ValueError("Approval is stale: episode, voice, ad, or production settings changed")
    if _validate_cues(episode_id, approved.get("media_cues", [])) != approved.get("media_cues", []):
        raise ValueError("Approval is stale: a production cue asset changed")
    for line in approved.get("script", []):
        if _validate_cues(episode_id, line.get("production_cues", [])) != line.get("production_cues", []):
            raise ValueError("Approval is stale: a line production cue asset changed")
    return approved, version_id


def editor_state(episode_id: str) -> dict[str, Any]:
    state = _load_state(episode_id)
    result = {**state, "episode_id": episode_id}
    draft_id = state.get("current_draft_id")
    if draft_id:
        result["draft"] = _read_json(_editor_root(episode_id) / "drafts" / f"{draft_id}.json")
    approved_id = state.get("current_approved_version_id")
    if approved_id:
        result["approved"] = _read_json(_approved_path(episode_id, str(approved_id)))
        try:
            current_approval(episode_id)
            result["approval_state"] = "approved"
        except (ValueError, FileNotFoundError):
            result["approval_state"] = "stale"
    return result
