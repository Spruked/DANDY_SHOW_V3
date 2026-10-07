import json
import hashlib
import re
import shutil
import uuid
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import IO
from typing import Any, Dict, List, Optional

from ...core.paths import EPISODES_ROOT


DRAFTS_ROOT = EPISODES_ROOT / ".drafts"
JOBS_ROOT = DRAFTS_ROOT / "jobs"

FALLBACK_LINE_SOURCES = {
    "api_expander",
    "emergency_seed",
    "expander",
    "legacy_template_fallback",
    "script_expander",
    "script_seed",
    "skg_template",
}
LLM_LINE_SOURCES = {"governance_bridge", "llamacpp", "llm_writer"}
STRUCTURAL_LINE_SOURCES = {"ad_engine", "production_structure", "script_feed", "manual_edit"}
LEGACY_TEMPLATE_TEXTS = {
    "happy toes begins as a father trying to reach his daughter through words.",
    "that is the part to keep centered: not whether every sentence is polished, but whether the reaching is honest.",
    "and the reach itself becomes the evidence.",
    "right, because the story is not just 'a poem exists.' it is that someone tried to turn absence into presence.",
    "that is where the father-daughter thread matters. the poem is not decoration. it is a bridge.",
    "a bridge, sure. but bridges have to land somewhere.",
    "and this one lands in the question of what a parent can still give when the normal channels are broken.",
    "that is the useful part. not sentiment for its own sake. a real attempt to leave something that can survive distance.",
}


def _normal_text(text: str) -> str:
    return " ".join(str(text or "").lower().split()).strip()


def ensure_storage_roots() -> None:
    for path in (EPISODES_ROOT, DRAFTS_ROOT, JOBS_ROOT):
        path.mkdir(parents=True, exist_ok=True)


def episode_dir(episode_id: str) -> Path:
    ensure_storage_roots()
    path = EPISODES_ROOT / episode_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def script_versions_dir(episode_id: str) -> Path:
    path = episode_dir(episode_id) / "script_versions"
    path.mkdir(parents=True, exist_ok=True)
    return path


def canonical_scripts_dir(episode_id: str) -> Path:
    path = episode_dir(episode_id) / "canonical_scripts"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _canonical_script_hash(script: List[Dict[str, Any]]) -> str:
    serialized = json.dumps(script, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def list_canonical_scripts(episode_id: str) -> List[Dict[str, Any]]:
    directory = canonical_scripts_dir(episode_id)
    snapshots = []
    for path in sorted(directory.glob("canonical_v*.json")):
        payload = load_json(path)
        if payload:
            snapshots.append({key: payload.get(key) for key in
                              ("version_id", "version", "created_at", "canonical_hash", "word_count", "line_count")})
    return snapshots


def _save_canonical_snapshot(episode_id: str, script: List[Dict[str, Any]], *,
                             project_active: bool, save_legacy_version: bool) -> Dict[str, Any]:
    directory = canonical_scripts_dir(episode_id)
    existing = [int(match.group(1)) for path in directory.glob("canonical_v*.json")
                if (match := re.fullmatch(r"canonical_v(\d+)\.json", path.name))]
    version = max(existing, default=0) + 1
    version_id = f"canonical_v{version:04d}"
    timestamp = datetime.now().isoformat()
    canonical_lines = []
    for index, raw_line in enumerate(script, start=1):
        line = dict(raw_line)
        line.pop("canonical_line_id", None)
        line["canonical_line_id"] = f"{version_id}_line_{index:04d}_{uuid.uuid4().hex[:8]}"
        canonical_lines.append(line)
    canonical_hash = _canonical_script_hash(canonical_lines)
    metadata = _recalculate_script_metadata(canonical_lines)
    payload = {"episode_id": episode_id, "version_id": version_id, "version": version,
               "created_at": timestamp, "canonical_hash": canonical_hash,
               "script": canonical_lines, "metadata": metadata,
               "word_count": metadata.get("word_count", 0), "line_count": len(canonical_lines)}
    snapshot_path = directory / f"{version_id}.json"
    with snapshot_path.open("x", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
    if project_active:
        save_json(directory / "active.json", {"version_id": version_id, "canonical_hash": canonical_hash,
                                               "updated_at": timestamp})
        save_json(episode_dir(episode_id) / "script.json", {
            "episode_id": episode_id, "updated_at": timestamp, "canonical_version_id": version_id,
            "canonical_hash": canonical_hash, "script": canonical_lines, "metadata": metadata,
        })
        existing_metadata = load_json(episode_metadata_path(episode_id)) or {}
        existing_metadata.update(metadata)
        save_json(episode_metadata_path(episode_id), existing_metadata)
        save_json(episode_dir(episode_id) / "status.json", {"status": "script_ready", "updated_at": timestamp,
                                                             "canonical_version_id": version_id, **metadata})
    if save_legacy_version:
        save_script_version(episode_id, canonical_lines)
    return payload


def load_canonical_script(episode_id: str, version_id: Optional[str] = None) -> Dict[str, Any]:
    directory = canonical_scripts_dir(episode_id)
    active = load_json(directory / "active.json")
    if not active:
        legacy = load_json(episode_dir(episode_id) / "script.json") or {"script": []}
        if not legacy.get("script"):
            raise FileNotFoundError(f"No canonical script exists for episode {episode_id}")
        snapshot = _save_canonical_snapshot(episode_id, legacy["script"],
                                           project_active=True, save_legacy_version=False)
        active = {"version_id": snapshot["version_id"]}
    selected = version_id or active.get("version_id")
    if not isinstance(selected, str) or not re.fullmatch(r"canonical_v\d{4,}", selected):
        raise ValueError("Invalid canonical script version ID")
    path = directory / f"{selected}.json"
    payload = load_json(path)
    if not payload:
        raise FileNotFoundError(f"Canonical script version not found: {selected}")
    if _canonical_script_hash(payload.get("script", [])) != payload.get("canonical_hash"):
        raise ValueError(f"Canonical script snapshot integrity check failed: {selected}")
    return payload


def assets_dir(episode_id: str) -> Path:
    path = episode_dir(episode_id) / "assets"
    path.mkdir(parents=True, exist_ok=True)
    return path


def asset_metadata_dir(episode_id: str) -> Path:
    path = assets_dir(episode_id) / "_meta"
    path.mkdir(parents=True, exist_ok=True)
    return path


def ads_dir(episode_id: str) -> Path:
    path = episode_dir(episode_id) / "ads"
    path.mkdir(parents=True, exist_ok=True)
    return path


def media_cues_path(episode_id: str) -> Path:
    return episode_dir(episode_id) / "media_cues.json"


def episode_metadata_path(episode_id: str) -> Path:
    return episode_dir(episode_id) / "metadata.json"


def ad_settings_path(episode_id: str) -> Path:
    return episode_dir(episode_id) / "ad_settings.json"


def save_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def load_json(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _sanitize_name(name: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in (".", "-", "_") else "_" for char in name.strip())
    return cleaned or "uploaded_file"


def _infer_asset_type(filename: str, content_type: str = "") -> str:
    suffix = Path(filename).suffix.lower()
    if content_type.startswith("image/") or suffix in {".png", ".jpg", ".jpeg", ".webp", ".gif"}:
        return "image"
    if suffix in {".txt", ".md", ".json", ".csv", ".html", ".htm"}:
        return "document"
    if suffix in {".pdf", ".doc", ".docx", ".rtf"}:
        return "document"
    if suffix in {".mp3", ".wav", ".m4a"}:
        return "audio"
    if suffix in {".mp4", ".mov", ".webm", ".mkv", ".avi"}:
        return "video"
    return "file"


def _extract_text_preview(stored_path: Path, asset_type: str) -> str:
    if asset_type != "document":
        return ""
    suffix = stored_path.suffix.lower()
    if suffix not in {".txt", ".md", ".json", ".csv", ".html", ".htm"}:
        return ""
    try:
        text = stored_path.read_text(encoding="utf-8", errors="ignore")
        return " ".join(text.split())[:4000]
    except Exception:
        return ""


def save_asset_upload(
    episode_id: str,
    *,
    filename: str,
    content_type: str,
    file_stream: IO[bytes],
    label: str = "",
    description: str = "",
    role: str = "source",
) -> Dict[str, Any]:
    episode_assets_dir = assets_dir(episode_id)
    asset_id = f"asset_{uuid.uuid4().hex[:12]}"
    safe_name = _sanitize_name(filename)
    stored_name = f"{asset_id}_{safe_name}"
    stored_path = episode_assets_dir / stored_name

    with stored_path.open("wb") as destination:
        shutil.copyfileobj(file_stream, destination)

    asset_type = _infer_asset_type(filename, content_type)
    extracted_text = _extract_text_preview(stored_path, asset_type)
    metadata = {
        "asset_id": asset_id,
        "episode_id": episode_id,
        "original_name": filename,
        "stored_name": stored_name,
        "stored_path": str(stored_path),
        "content_type": content_type or "application/octet-stream",
        "asset_type": asset_type,
        "label": label,
        "description": description,
        "role": role,
        "uploaded_at": datetime.now().isoformat(),
        "extracted_text_preview": extracted_text,
    }
    save_json(asset_metadata_dir(episode_id) / f"{asset_id}.json", metadata)
    return metadata


def list_assets(episode_id: str) -> List[Dict[str, Any]]:
    directory = asset_metadata_dir(episode_id)
    assets: List[Dict[str, Any]] = []
    for path in sorted(directory.glob("asset_*.json")):
        payload = load_json(path)
        if payload:
            assets.append(payload)
    return assets


def load_asset(episode_id: str, asset_id: str) -> Optional[Dict[str, Any]]:
    return load_json(asset_metadata_dir(episode_id) / f"{asset_id}.json")


def save_media_cues(episode_id: str, cues: List[Dict[str, Any]]) -> Dict[str, Any]:
    payload = {
        "episode_id": episode_id,
        "updated_at": datetime.now().isoformat(),
        "cues": cues,
    }
    save_json(media_cues_path(episode_id), payload)
    return payload


def load_media_cues(episode_id: str) -> Dict[str, Any]:
    payload = load_json(media_cues_path(episode_id))
    if payload:
        return payload
    return {"episode_id": episode_id, "updated_at": None, "cues": []}


def append_media_cue(episode_id: str, cue: Dict[str, Any]) -> Dict[str, Any]:
    payload = load_media_cues(episode_id)
    cues = payload.get("cues", [])
    cue_record = {
        "cue_id": cue.get("cue_id") or f"cue_{uuid.uuid4().hex[:10]}",
        "asset_id": cue.get("asset_id"),
        "line_number": cue.get("line_number"),
        "start_seconds": cue.get("start_seconds"),
        "end_seconds": cue.get("end_seconds"),
        "display_label": cue.get("display_label", ""),
        "notes": cue.get("notes", ""),
    }
    cues.append(cue_record)
    return save_media_cues(episode_id, cues)


def save_ad_settings(episode_id: str, settings: Dict[str, Any]) -> Dict[str, Any]:
    payload = {"episode_id": episode_id, **settings, "updated_at": datetime.now().isoformat()}
    save_json(ad_settings_path(episode_id), payload)
    return payload


def load_ad_settings(episode_id: str) -> Dict[str, Any]:
    return load_json(ad_settings_path(episode_id)) or {}


def save_ad(episode_id: str, ad_payload: Dict[str, Any]) -> Dict[str, Any]:
    ads_path = ads_dir(episode_id)
    ad_id = ad_payload.get("ad_id") or f"ad_{uuid.uuid4().hex[:8]}"
    payload = {
        "ad_id": ad_id,
        "episode_id": episode_id,
        **ad_payload,
    }
    save_json(ads_path / f"{ad_id}.json", payload)
    return payload


def list_ads(episode_id: str) -> List[Dict[str, Any]]:
    directory = ads_dir(episode_id)
    ads: List[Dict[str, Any]] = []
    for path in sorted(directory.glob("ad_*.json")):
        payload = load_json(path)
        if isinstance(payload, dict) and payload.get("ad_id") and "script" in payload:
            ads.append(payload)
    return ads


def build_source_context(episode_id: str) -> str:
    parts: List[str] = []
    for asset in list_assets(episode_id):
        role = asset.get("role", "source")
        label = asset.get("label") or asset.get("original_name", "")
        description = asset.get("description", "")
        preview = asset.get("extracted_text_preview", "")
        if asset.get("asset_type") == "image":
            image_line = f"Image asset: {label}."
            if description:
                image_line += f" Description: {description}"
            parts.append(image_line.strip())
            continue
        context_bits = [bit for bit in [f"{role}: {label}".strip(), description, preview] if bit]
        if context_bits:
            parts.append(" | ".join(context_bits))
    return "\n".join(parts[:8])


def create_episode_draft(payload: Dict[str, Any], job_id: str) -> Dict[str, Any]:
    ensure_storage_roots()
    created_at = datetime.now().isoformat()
    episode_id = payload["episode_id"]
    ep_dir = episode_dir(episode_id)

    draft = {
        "job_id": job_id,
        "episode_id": episode_id,
        "created_at": created_at,
        "updated_at": created_at,
        "status": "draft_created",
        "config": payload,
    }
    save_json(DRAFTS_ROOT / f"{episode_id}.json", draft)
    save_json(JOBS_ROOT / f"{job_id}.json", {"job_id": job_id, "episode_id": episode_id})
    save_json(ep_dir / "config.json", payload)
    save_json(ep_dir / "status.json", {"status": "draft_created", "updated_at": created_at})
    return draft


def load_job(job_id: str) -> Optional[Dict[str, Any]]:
    return load_json(JOBS_ROOT / f"{job_id}.json")


def load_draft(episode_id: str) -> Optional[Dict[str, Any]]:
    return load_json(DRAFTS_ROOT / f"{episode_id}.json")


def _line_source(line: Dict[str, Any]) -> str:
    source = str(line.get("generated_by") or line.get("line_source") or line.get("source") or "").strip()
    if source:
        return source
    text = _normal_text(str(line.get("text", line.get("line", ""))))
    if text in LEGACY_TEMPLATE_TEXTS:
        return "legacy_template_fallback"
    return "unknown"


def calculate_script_provenance(script_lines: List[Dict[str, Any]]) -> Dict[str, Any]:
    source_counts = Counter(_line_source(line) for line in script_lines)
    fallback_sources = sorted(source for source in source_counts if source in FALLBACK_LINE_SOURCES)
    llm_sources = sorted(source for source in source_counts if source in LLM_LINE_SOURCES)
    structural_sources = sorted(source for source in source_counts if source in STRUCTURAL_LINE_SOURCES)
    fallback_line_count = sum(source_counts[source] for source in fallback_sources)
    llm_line_count = sum(source_counts[source] for source in llm_sources)
    structural_line_count = sum(source_counts[source] for source in structural_sources)
    unknown_line_count = source_counts.get("unknown", 0)

    if fallback_line_count and llm_line_count:
        writer_engine = "mixed"
    elif fallback_line_count:
        writer_engine = "template_fallback"
    elif llm_line_count:
        writer_engine = "llm_bridge"
    elif structural_line_count and not unknown_line_count:
        writer_engine = "structured"
    else:
        writer_engine = "unknown"

    return {
        "writer_engine": writer_engine,
        "writer_engine_actual": writer_engine,
        "fallback_used": fallback_line_count > 0,
        "fallback_sources": fallback_sources,
        "fallback_line_count": fallback_line_count,
        "llm_sources": llm_sources,
        "llm_line_count": llm_line_count,
        "structural_sources": structural_sources,
        "structural_line_count": structural_line_count,
        "unknown_line_count": unknown_line_count,
        "line_source_counts": dict(sorted(source_counts.items())),
        "provenance_reliable": unknown_line_count == 0,
    }


def calculate_repetition_report(script_lines: List[Dict[str, Any]], max_allowed: int = 1) -> Dict[str, Any]:
    texts = [re.sub(r"[^\w\s]", "", _normal_text(str(line.get("text", line.get("line", ""))))) for line in script_lines if not line.get("is_ad") and not line.get("ad_id")]
    counts = Counter(text for text in texts if text)
    repeated = [(text, count) for text, count in counts.items() if count > 1]
    repeated.sort(key=lambda item: item[1], reverse=True)
    max_count = repeated[0][1] if repeated else 1 if counts else 0

    return {
        "repetition_guard_passed": max_count <= max_allowed,
        "repetition_guard_max_allowed": max_allowed,
        "max_repeated_line_count": max_count,
        "repeated_line_count": len(repeated),
        "duplicate_line_instances": sum(count - 1 for _, count in repeated),
        "top_repeated_lines": [
            {"count": count, "text": text[:160]}
            for text, count in repeated[:5]
        ],
    }


def _recalculate_script_metadata(script_lines: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Recalculate line counts, speaker counts, and estimated runtime."""
    def speaker_is(line: Dict[str, Any], name: str) -> bool:
        speaker = str(line.get("speaker", "")).lower()
        return speaker == name or speaker.startswith(f"{name}_")

    metadata = {
        "line_count": len(script_lines),
        "phil_count": sum(1 for line in script_lines if speaker_is(line, "phil")),
        "jim_count": sum(1 for line in script_lines if speaker_is(line, "jim")),
        "host_count": sum(1 for line in script_lines if speaker_is(line, "host")),
        "ads_count": len({line["ad_id"] for line in script_lines if line.get("ad_id")}) + sum(1 for line in script_lines if not line.get("ad_id") and speaker_is(line, "ad")),
    }

    words = sum(len(str(line.get("text", "")).split()) for line in script_lines)
    pauses = sum(float(line.get("pause_after", 0) or 0) for line in script_lines)
    metadata["word_count"] = words
    metadata["estimated_runtime_seconds"] = round(words / 155 * 60 + pauses)
    metadata["runtime_source"] = "word-count plus pauses estimate; final audio requires ffprobe"
    metadata["segment_count"] = len({line["segment_index"] for line in script_lines if line.get("segment_index") is not None and not line.get("is_ad")})
    metadata.update(calculate_script_provenance(script_lines))
    metadata.update(calculate_repetition_report(script_lines))

    return metadata


def save_script(episode_id: str, script: List[Dict[str, Any]]) -> None:
    _save_canonical_snapshot(episode_id, script, project_active=True, save_legacy_version=True)


def save_generated_script(episode_id: str, script_lines: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Save script and update metadata every time a script is generated."""
    save_script(episode_id, script_lines)
    return load_json(episode_metadata_path(episode_id)) or {}


def load_script(episode_id: str) -> Dict[str, Any]:
    ep_dir = episode_dir(episode_id)
    canonical_index = load_json(canonical_scripts_dir(episode_id) / "active.json")
    if canonical_index and canonical_index.get("version_id"):
        return load_canonical_script(episode_id, canonical_index["version_id"])
    script_data = load_json(ep_dir / "script.json")
    if script_data:
        return script_data
    return {"episode_id": episode_id, "script": [], "updated_at": None}


def save_script_version(episode_id: str, script: List[Dict[str, Any]]) -> Dict[str, Any]:
    versions = list_script_versions(episode_id)
    version_number = len(versions) + 1
    payload = {
        "version": version_number,
        "saved_at": datetime.now().isoformat(),
        "script": script,
        "word_count": sum(len(line.get("text", "").split()) for line in script),
    }
    save_json(script_versions_dir(episode_id) / f"version_{version_number:03d}.json", payload)
    return payload


def list_script_versions(episode_id: str) -> List[Dict[str, Any]]:
    directory = script_versions_dir(episode_id)
    versions: List[Dict[str, Any]] = []
    for path in sorted(directory.glob("version_*.json")):
        payload = load_json(path)
        if payload:
            versions.append(payload)
    return versions


def load_script_version(episode_id: str, version: int) -> Optional[Dict[str, Any]]:
    return load_json(script_versions_dir(episode_id) / f"version_{version:03d}.json")


def save_feedback(episode_id: str, feedback: str) -> Dict[str, Any]:
    payload = {
        "episode_id": episode_id,
        "feedback": feedback,
        "saved_at": datetime.now().isoformat(),
    }
    save_json(episode_dir(episode_id) / "customer_feedback.json", payload)
    return payload


def load_feedback(episode_id: str) -> Optional[Dict[str, Any]]:
    return load_json(episode_dir(episode_id) / "customer_feedback.json")


def save_episode_config(episode_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
    ep_dir = episode_dir(episode_id)
    existing = load_json(ep_dir / "config.json") or {}
    protected = {"episode_id"}
    merged = {**existing, **{k: v for k, v in updates.items() if k not in protected}, "episode_id": episode_id}
    merged["updated_at"] = datetime.now().isoformat()
    save_json(ep_dir / "config.json", merged)
    return merged


def load_episode_detail(episode_id: str) -> Dict[str, Any]:
    ep_dir = episode_dir(episode_id)
    config = load_json(ep_dir / "config.json") or {}
    status = load_json(ep_dir / "status.json") or {}
    script = load_json(ep_dir / "script.json") or {"script": []}
    metadata = load_json(episode_metadata_path(episode_id)) or script.get("metadata") or {}
    feedback = load_feedback(episode_id)
    production = load_json(ep_dir / "production_result.json") or {}
    audio_path = production.get("audio_file") or status.get("audio_file")
    assets = list_assets(episode_id)
    media_cues = load_media_cues(episode_id)
    ads = list_ads(episode_id)
    ad_settings = load_ad_settings(episode_id)
    return {
        "episode_id": episode_id,
        "config": config,
        "status": status.get("status", "new"),
        "updated_at": status.get("updated_at"),
        "script": script.get("script", []),
        "metadata": metadata,
        "feedback": feedback.get("feedback") if feedback else None,
        "line_count": metadata.get("line_count", len(script.get("script", []))),
        "phil_count": metadata.get("phil_count", 0),
        "jim_count": metadata.get("jim_count", 0),
        "host_count": metadata.get("host_count", 0),
        "estimated_runtime_seconds": metadata.get("estimated_runtime_seconds", 0),
        "audio": audio_path,
        "has_audio": bool(audio_path and Path(audio_path).exists()),
        "production_mode": status.get("production_mode"),
        "assets": assets,
        "assets_count": len(assets),
        "media_cues": media_cues.get("cues", []),
        "media_cues_count": len(media_cues.get("cues", [])),
        "ads": ads,
        "ads_count": len(ads),
        "ad_settings": ad_settings,
    }


def list_episode_summaries() -> List[Dict[str, Any]]:
    ensure_storage_roots()
    episodes: List[Dict[str, Any]] = []
    for path in sorted(EPISODES_ROOT.iterdir()):
        if not path.is_dir() or path.name.startswith("."):
            continue
        config = load_json(path / "config.json") or {}
        status = load_json(path / "status.json") or {}
        script = load_json(path / "script.json") or {"script": []}
        metadata = load_json(episode_metadata_path(path.name)) or script.get("metadata") or {}
        production = load_json(path / "production_result.json") or {}
        audio_path = production.get("audio_file") or status.get("audio_file")
        assets = list_assets(path.name)
        media_cues = load_media_cues(path.name)
        ads = list_ads(path.name)
        ad_settings = load_ad_settings(path.name)
        episodes.append(
            {
                "episode_id": path.name,
                "title": config.get("title") or path.name,
                "topic": config.get("topic", ""),
                "status": status.get("status", "new"),
                "updated_at": status.get("updated_at"),
                "has_script": bool(script.get("script")),
                "line_count": metadata.get("line_count", len(script.get("script", []))),
                "phil_count": metadata.get("phil_count", 0),
                "jim_count": metadata.get("jim_count", 0),
                "host_count": metadata.get("host_count", 0),
                "estimated_runtime_seconds": metadata.get("estimated_runtime_seconds", 0),
                "has_audio": bool(audio_path and Path(audio_path).exists()),
                "production_mode": status.get("production_mode"),
                "assets_count": len(assets),
                "media_cues_count": len(media_cues.get("cues", [])),
                "ads_count": len(ads),
                "ad_settings": ad_settings,
            }
        )
    return episodes
