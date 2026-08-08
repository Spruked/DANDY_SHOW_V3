import asyncio
from datetime import datetime
from functools import partial
from pathlib import Path
import re
from typing import Dict, List, Optional
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Body
from pydantic import BaseModel
from pydub import AudioSegment

from ..core.paths import PROJECT_ROOT
from ..schemas.episode import EpisodeCreateRequest
from ..services.production import MergedDandyPodcastWorker
from ..services.production.quality_guard import QualityDecision, ScriptQualityGuard
from ..services.social.package_builder import export_social_package
from ..services.production.script_seed import generate_seed_script
from ..services.ads.ad_engine import ADS_CATALOG, generate_ad_script, summarize_context
from ..services.storage.episode_store import (
    build_source_context,
    calculate_repetition_report,
    calculate_script_provenance,
    create_episode_draft,
    episode_dir,
    load_draft,
    load_job,
    load_script,
    load_script_version,
    list_script_versions,
    load_episode_detail,
    load_asset,
    load_media_cues,
    save_json,
    save_feedback,
    save_script,
)


router = APIRouter(tags=["production"])
_WORKER: MergedDandyPodcastWorker | None = None
_QUALITY_GUARD = ScriptQualityGuard()


@router.get("/writer-status")
def writer_status():
    from ..services.production import llm_writer

    return llm_writer.writer_status()

    from ..services.production.communication_layer import _is_bridge_reachable
    bridge_ok = _is_bridge_reachable()
    return {
        "bridge_reachable": bridge_ok,
        "active_writer": "llm_bridge" if bridge_ok else "skg_fallback",
        "bridge_url": "http://127.0.0.1:5199",
        "warning": None if bridge_ok else "LLM bridge offline — production will use SKG fallback.",
    }


class EditScriptRequest(BaseModel):
    episode_id: str
    edit_type: str
    line_index: Optional[int] = None
    new_content: Optional[Dict] = None
    new_order: Optional[List[int]] = None
    tone_adjustment: Optional[str] = None
    expansion_words: Optional[int] = None


def _reindex(script: List[Dict]) -> List[Dict]:
    for idx, line in enumerate(script, start=1):
        line["line_number"] = idx
    return script


def _sanitize_script_text(text: str) -> str:
    cleaned = str(text or "").strip()
    cleaned = re.sub(r"^(phil|jim|host|guest|narrator|both|speaker)\s*[:\-]\s*", "", cleaned, flags=re.IGNORECASE).strip()
    return cleaned


def _sanitize_script_line(line: Dict) -> Dict:
    payload = dict(line)
    payload["text"] = _sanitize_script_text(payload.get("text", ""))
    return payload


def _sanitize_script(script: List[Dict]) -> List[Dict]:
    return [_sanitize_script_line(line) for line in script]


def _assert_llm_script_publishable(script: List[Dict], require_llm: bool = True) -> Dict:
    provenance = calculate_script_provenance(script)
    repetition = calculate_repetition_report(script)
    if require_llm and provenance.get("fallback_used"):
        raise RuntimeError(f"Fallback-authored lines present: {provenance.get('fallback_sources')}")
    if require_llm and int(provenance.get("llm_line_count", 0)) <= 0:
        raise RuntimeError("No LLM-authored lines found in script")
    if not repetition.get("repetition_guard_passed"):
        raise RuntimeError(
            "Repetition guard failed: "
            f"max repeated line count {repetition.get('max_repeated_line_count')}"
        )
    return {**provenance, **repetition}


def _validate_runtime_or_raise(script: List[Dict], min_minutes: float = 30.0, max_minutes: float = 45.0) -> None:
    est = _estimate_minutes(script)
    if est < min_minutes or est > max_minutes:
        raise HTTPException(status_code=400, detail=f"Episode must be between {min_minutes:.0f} and {max_minutes:.0f} minutes (current ~{est:.1f}m)")


def _script_as_text(script: List[Dict]) -> str:
    lines = []
    for line in script:
        speaker = str(line.get("speaker", "speaker")).upper()
        text = line.get("text", "")
        lines.append(f"{speaker}: {text}")
    return "\n".join(lines)


def _script_as_srt(script: List[Dict]) -> str:
    rows = []
    for idx, line in enumerate(script, start=1):
        start_seconds = (idx - 1) * 4
        end_seconds = start_seconds + 4
        start = f"00:00:{start_seconds:02d},000"
        end = f"00:00:{end_seconds:02d},000"
        speaker = str(line.get("speaker", "speaker")).upper()
        text = line.get("text", "")
        rows.append(f"{idx}\n{start} --> {end}\n{speaker}: {text}\n")
    return "\n".join(rows)


def _create_placeholder_audio(episode_id: str, script: List[Dict]) -> Path:
    target_dir = episode_dir(episode_id)
    output_path = target_dir / "audio.mp3"
    word_count = max(1, sum(len(line.get("text", "").split()) for line in script))
    duration_ms = max(5000, min(60000, word_count * 350))
    AudioSegment.silent(duration=duration_ms).export(output_path, format="mp3")
    return output_path


def _estimate_minutes(script: List[Dict], wpm: int = 160) -> float:
    words = sum(len(line.get("text", "").split()) for line in script)
    return words / float(wpm)


_EXPAND_LINES = [
    ("phil", "And that's really the crux of it — let's unpack that a bit more.", "curious"),
    ("jim",  "Right, and when you look at the bigger picture, it becomes even clearer.", "thoughtful"),
    ("phil", "I think people underestimate how much context matters here.", "excited"),
    ("jim",  "Exactly — context changes everything. Give me an example.", "skeptical"),
    ("phil", "Sure. Think about what happens when you strip away all the noise.", "curious"),
    ("jim",  "That's a fair point. What does that look like in practice?", "thoughtful"),
    ("phil", "In practice it means you have to be intentional about every decision.", "excited"),
    ("jim",  "Which most people aren't, honestly. They just react.", "skeptical"),
    ("phil", "Reactive versus proactive — that's the whole game right there.", "curious"),
    ("jim",  "And the proactive folks win nine times out of ten. That's just the data.", "thoughtful"),
    ("phil", "The data backs it up and so does every case study I've seen.", "excited"),
    ("jim",  "So why don't more people do it? That's the real question.", "skeptical"),
    ("phil", "Fear, mostly. Change is uncomfortable even when it's obviously better.", "curious"),
    ("jim",  "Comfort zones are expensive. People don't realize the cost until too late.", "thoughtful"),
    ("phil", "By which point the gap between them and the leaders is enormous.", "excited"),
    ("jim",  "Compounding works against you just as fast as it works for you.", "skeptical"),
]


def _expand_script(script: List[Dict], target_min: float) -> List[Dict]:
    working = list(script)
    idx = 0
    while _estimate_minutes(working) < target_min:
        entry = _EXPAND_LINES[idx % len(_EXPAND_LINES)]
        working.append({
            "speaker": entry[0],
            "text": entry[1],
            "emotion": entry[2],
            "pause_after": 0.4,
            "generated_by": "api_expander",
        })
        idx += 1
        if idx > 10000:  # absolute safety cap
            break
    return _reindex(working)


def _trim_script(script: List[Dict], target_max: float) -> List[Dict]:
    working = list(script)
    while working and _estimate_minutes(working) > target_max and len(working) > 8:
        working.pop()
    return _reindex(working)


def _resolve_episode_audio_path(episode_id: str) -> Path | None:
    detail = load_episode_detail(episode_id)
    recorded_audio = detail.get("audio")
    candidates: List[Path] = []

    if recorded_audio:
        raw_path = Path(str(recorded_audio))
        candidates.append(raw_path)
        if not raw_path.is_absolute():
            candidates.append((PROJECT_ROOT / raw_path).resolve())
            candidates.append((episode_dir(episode_id) / raw_path).resolve())

    candidates.append(episode_dir(episode_id) / "audio.mp3")

    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        if candidate.exists() and candidate.is_file():
            return candidate
    return None


def _enforce_ads_and_structure(script: List[Dict], ads: List[Dict], ad_settings: Dict | None = None) -> List[Dict]:
    if len(script) < 4:
        return script
    ad_settings = ad_settings or {}
    required_ads = 2
    est_minutes = _estimate_minutes(script)
    if est_minutes > 40:
        required_ads = 3

    # Ensure at least two ads exist
    def fallback_ad(idx: int) -> List[Dict]:
        key = list(ADS_CATALOG.keys())[idx % len(ADS_CATALOG)]
        announcer = ad_settings.get(f"ad{idx+1}_announcer") or ("announcer_female" if idx == 0 else "announcer_male")
        return generate_ad_script(key, announcer, summarize_context(script), duration_seconds=20)

    def pick_announcer_for_record(idx: int, default_key: str) -> str:
        return (
            ad_settings.get(f"ad{idx+1}_announcer")
            or (ads[idx].get("announcer_key") if idx < len(ads) else None)
            or default_key
        )

    ad1 = ads[0]["script"] if len(ads) > 0 else fallback_ad(0)
    ad2 = ads[1]["script"] if len(ads) > 1 else fallback_ad(1)
    ad3 = ads[2]["script"] if len(ads) > 2 else fallback_ad(2) if required_ads >= 3 else []

    seg_len = max(1, len(script) // 4)
    segments = [
        script[0:seg_len],
        script[seg_len : seg_len * 2],
        script[seg_len * 2 : seg_len * 3],
        script[seg_len * 3 :],
    ]

    assembled: List[Dict] = []
    intro_voice = ad_settings.get("intro_announcer", "announcer_male")
    outro_voice = ad_settings.get("outro_announcer", "announcer_female")
    assembled.append(
        {"speaker": intro_voice, "text": "Welcome to the Phil and Jim Dandy Show.", "emotion": "confident", "pause_after": 0.6, "generated_by": "production_structure"}
    )
    assembled.extend(segments[0])
    assembled.extend(segments[1])
    ad1_speaker = pick_announcer_for_record(0, "announcer_female")
    assembled.extend([{**l, "speaker": ad1_speaker, "generated_by": l.get("generated_by", "ad_engine")} for l in ad1])
    assembled.extend(segments[2])
    ad2_speaker = pick_announcer_for_record(1, "announcer_male")
    assembled.extend([{**l, "speaker": ad2_speaker, "generated_by": l.get("generated_by", "ad_engine")} for l in ad2])
    assembled.extend(segments[3])
    if required_ads >= 3 and ad3:
        ad3_speaker = pick_announcer_for_record(2, "announcer_male")
        assembled.extend([{**l, "speaker": ad3_speaker, "generated_by": l.get("generated_by", "ad_engine")} for l in ad3])
    assembled.append(
        {"speaker": outro_voice, "text": "Thanks for listening. Catch us next episode.", "emotion": "warm", "pause_after": 0.6, "generated_by": "production_structure"}
    )
    for idx, line in enumerate(assembled, start=1):
        line["line_number"] = idx
    return assembled


def _get_worker() -> MergedDandyPodcastWorker:
    global _WORKER
    if _WORKER is None:
        _WORKER = MergedDandyPodcastWorker(PROJECT_ROOT)
    return _WORKER


@router.post("/episodes/create")
async def create_episode(payload: EpisodeCreateRequest):
    job_id = f"job_{payload.episode_id}_{uuid4().hex[:8]}"
    draft = create_episode_draft(payload.model_dump(), job_id)
    return {
        "message": "Episode draft created",
        "job_id": job_id,
        "episode_id": payload.episode_id,
        "status": draft["status"],
        "config": draft["config"],
    }


@router.post("/episodes/generate-script")
async def generate_script(
    job_id: str = Query(...),
    payload: Dict | None = Body(default=None),
):
    job = load_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    draft = load_draft(job["episode_id"])
    if not draft:
        raise HTTPException(status_code=404, detail="Episode draft not found")

    generation_config = dict(draft["config"])
    if payload and payload.get("personality_settings"):
        generation_config["personality_settings"] = payload["personality_settings"]
    generation_config["source_context"] = build_source_context(job["episode_id"])
    generation_config["require_llm"] = True
    generation_config["generation_nonce"] = f"{job['episode_id']}-{uuid4().hex}"

    # script_feed mode: use provided_script directly, skip AI generation
    if generation_config.get("generation_mode") == "script_feed" and generation_config.get("provided_script"):
        script = _sanitize_script(generation_config["provided_script"])
        for line in script:
            line.setdefault("generated_by", "script_feed")
        save_script(job["episode_id"], script)
        return {
            "status": "script_ready",
            "job_id": job_id,
            "episode_id": job["episode_id"],
            "script": script,
            "word_count": sum(len(line["text"].split()) for line in script),
        }

    # Default to ~150 wpm toward a 40-minute optimal length when not provided
    if not generation_config.get("target_word_count"):
        target_duration = generation_config.get("target_duration") or 2400
        generation_config["target_word_count"] = int((target_duration / 60) * 150)

    try:
        script = _get_worker().generate_script(generation_config)
        # Guard against silent template failures: if >30% of lines contain
        # unresolved [unknown] placeholders the generator returned bad output.
        unknown_lines = sum(1 for line in script if "[unknown]" in line.get("text", ""))
        if not script or (len(script) > 0 and unknown_lines / len(script) > 0.3):
            raise RuntimeError(f"Script quality check failed: {unknown_lines}/{len(script)} lines contain [unknown]")
        target_minutes = int(
            generation_config.get("target_duration_minutes")
            or (generation_config.get("target_duration", 2400) // 60)
            or 40
        )
        report = _QUALITY_GUARD.evaluate(script, target_minutes, generation_config.get("topic", ""))
        if report.decision != QualityDecision.ACCEPT:
            raise RuntimeError(f"Script quality check failed: {report.issues or report.warnings}")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"LLM script generation failed: {exc}") from exc
    script = _sanitize_script(script)
    script_meta = _assert_llm_script_publishable(script, require_llm=True)
    save_script(job["episode_id"], script)
    return {
        "status": "script_ready",
        "job_id": job_id,
        "episode_id": job["episode_id"],
        "script": script,
        "word_count": sum(len(line["text"].split()) for line in script),
        "writer_engine": script_meta.get("writer_engine"),
        "fallback_used": script_meta.get("fallback_used"),
    }


def _run_produce_background(
    episode_id: str,
    job_id: str,
    script: list,
    title: str,
    topic: str,
    script_text: str,
    personality_settings,
    voice_settings: dict,
    writer_engine: str = "skg_fallback",
    bridge_reachable_at_start: bool = False,
) -> None:
    """Heavy TTS work — runs in a thread so the event loop stays alive."""
    worker = _get_worker()
    if personality_settings:
        try:
            worker._apply_personality_settings(personality_settings)  # type: ignore[attr-defined]
        except Exception:
            pass
    try:
        production_result = worker.produce_episode(
            episode_id=episode_id,
            title=title,
            topic=topic,
            script_lines=script,
        )
        audio_path = Path(production_result["audio_file"])
        production_mode = "worker"
    except Exception as exc:
        audio_path = _create_placeholder_audio(episode_id, script)
        production_mode = "placeholder_fallback"
        production_result = {
            "episode_id": episode_id,
            "audio_file": str(audio_path),
            "transcript": script,
            "metadata": {
                "warning": str(exc),
                "processing": {"processing_chain": "placeholder_fallback"},
            },
        }

    script_meta = {
        **calculate_script_provenance(script),
        **calculate_repetition_report(script),
    }
    writer_engine = str(script_meta.get("writer_engine", writer_engine))
    produced_at = datetime.now().isoformat()
    save_json(
        episode_dir(episode_id) / "status.json",
        {
            "status": "produced",
            "updated_at": produced_at,
            "production_mode": production_mode,
            "audio_file": str(audio_path),
            "personality_settings": personality_settings,
            "voice_settings": voice_settings,
            "writer_engine": writer_engine,
            "bridge_reachable_at_start": bridge_reachable_at_start,
            "fallback_used": script_meta.get("fallback_used"),
            "fallback_sources": script_meta.get("fallback_sources", []),
            "llm_line_count": script_meta.get("llm_line_count", 0),
            "fallback_line_count": script_meta.get("fallback_line_count", 0),
            "unknown_line_count": script_meta.get("unknown_line_count", 0),
            "line_source_counts": script_meta.get("line_source_counts", {}),
            "repetition_guard_passed": script_meta.get("repetition_guard_passed"),
            "max_repeated_line_count": script_meta.get("max_repeated_line_count"),
        },
    )
    production_result.setdefault("metadata", {}).update({
        "writer_engine": writer_engine,
        "bridge_reachable_at_start": bridge_reachable_at_start,
        "fallback_used": script_meta.get("fallback_used"),
        "fallback_sources": script_meta.get("fallback_sources", []),
        "llm_line_count": script_meta.get("llm_line_count", 0),
        "fallback_line_count": script_meta.get("fallback_line_count", 0),
        "unknown_line_count": script_meta.get("unknown_line_count", 0),
        "line_source_counts": script_meta.get("line_source_counts", {}),
        "repetition_guard_passed": script_meta.get("repetition_guard_passed"),
        "max_repeated_line_count": script_meta.get("max_repeated_line_count"),
    })
    save_json(episode_dir(episode_id) / "production_result.json", production_result)

    social_destination = (PROJECT_ROOT / "social" / "generated" / episode_id).resolve()
    resolved_cues = []
    for cue in load_media_cues(episode_id).get("cues", []):
        asset = load_asset(episode_id, cue.get("asset_id", ""))
        resolved_cues.append({**cue, "asset": asset or {}})
    export_social_package(
        episode_id=episode_id,
        title=title,
        topic=topic,
        script_text=script_text,
        script_lines=script,
        audio_path=audio_path,
        destination=social_destination,
        sponsor_text="Sponsored",
        media_cues=resolved_cues,
    )


@router.post("/episodes/produce")
async def produce_episode(
    background_tasks: BackgroundTasks,
    job_id: str = Query(...),
    payload: Dict | None = Body(default=None),
):
    job = load_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    detail = load_episode_detail(job["episode_id"])
    script = detail.get("script", [])
    if not script:
        raise HTTPException(status_code=400, detail="No script found. Generate script first.")
    script = _sanitize_script(script)
    require_llm = detail.get("config", {}).get("generation_mode") != "script_feed"
    WORD_MIN = 5000
    WORD_MAX = int(45 * 160)
    est_words = sum(len(l.get("text", "").split()) for l in script)
    if est_words < WORD_MIN:
        if require_llm:
            raise HTTPException(
                status_code=400,
                detail=f"LLM-authored episode is too short for production and will not be template-expanded (got {est_words}, need {WORD_MIN}).",
            )
        script = _expand_script(script, WORD_MIN / 160)
    est_words = sum(len(l.get("text", "").split()) for l in script)
    if est_words > WORD_MAX:
        script = _trim_script(script, 45.0)
    est_words = sum(len(l.get("text", "").split()) for l in script)
    if est_words < WORD_MIN:
        raise HTTPException(status_code=400, detail=f"Episode must have at least {WORD_MIN} words after normalization (got {est_words}).")

    script = _enforce_ads_and_structure(script, detail.get("ads", []), detail.get("ad_settings"))
    try:
        script_meta = _assert_llm_script_publishable(script, require_llm=require_llm)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    title = detail.get("config", {}).get("title") or job["episode_id"]
    topic = detail.get("config", {}).get("topic") or title
    script_text = _script_as_text(script)
    personality_settings = (payload or {}).get("personality_settings") if payload else None
    voice_settings = (payload or {}) if payload else {}

    writer_engine = str(script_meta.get("writer_engine", "unknown"))
    bridge_was_reachable = writer_engine == "llm_bridge"

    # Mark as producing immediately so the UI can show progress
    save_json(
        episode_dir(job["episode_id"]) / "status.json",
        {
            "status": "producing",
            "updated_at": datetime.now().isoformat(),
            "job_id": job_id,
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
        "job_id": job_id,
        "episode_id": job["episode_id"],
        "message": "Production started in background. Poll episode status for completion.",
        "word_count": est_words,
    }


@router.post("/episodes/edit-script")
async def edit_script(payload: EditScriptRequest):
    script_data = load_script(payload.episode_id)
    script = script_data.get("script", [])

    if payload.edit_type == "modify_line":
        if payload.line_index is None or payload.line_index >= len(script):
            raise HTTPException(status_code=400, detail="Invalid line index")
        if not payload.new_content:
            raise HTTPException(status_code=400, detail="new_content is required")
        script[payload.line_index] = _sanitize_script_line(payload.new_content)
        script[payload.line_index]["generated_by"] = "manual_edit"
        script = _reindex(script)
    elif payload.edit_type == "add_line":
        new_line = payload.new_content or {"speaker": "phil", "text": "", "emotion": "neutral", "pause_after": 0.5}
        new_line = _sanitize_script_line(new_line)
        new_line["generated_by"] = "manual_edit"
        insert_at = payload.line_index if payload.line_index is not None else len(script)
        script.insert(insert_at, new_line)
        script = _reindex(script)
    elif payload.edit_type == "remove_line":
        if payload.line_index is None or payload.line_index >= len(script):
            raise HTTPException(status_code=400, detail="Invalid line index")
        script.pop(payload.line_index)
        script = _reindex(script)
    elif payload.edit_type == "reorder_lines":
        if not payload.new_order:
            raise HTTPException(status_code=400, detail="new_order is required")
        script = [script[i] for i in payload.new_order if 0 <= i < len(script)]
        script = _reindex(script)
    elif payload.edit_type == "expand_script":
        addition = {
            "speaker": "phil",
            "text": "This expanded section is a placeholder for the next production import step.",
            "emotion": "warm",
            "pause_after": 0.5,
            "generated_by": "api_expander",
        }
        script.append(addition)
        script = _reindex(script)
    elif payload.edit_type == "adjust_tone":
        tone = payload.tone_adjustment or "adjusted"
        for line in script:
            line["emotion"] = tone
    else:
        raise HTTPException(status_code=400, detail="Unsupported edit_type in shell stage")

    script = _sanitize_script(script)
    save_script(payload.episode_id, script)
    return {
        "status": "script_ready",
        "episode_id": payload.episode_id,
        "updated_script": script,
        "line_count": len(script),
    }


@router.get("/episodes/{episode_id}/script-versions")
async def script_versions(episode_id: str):
    versions = list_script_versions(episode_id)
    return {
        "episode_id": episode_id,
        "versions": [
            {
                "version": item["version"],
                "saved_at": item["saved_at"],
                "word_count": item["word_count"],
                "preview": item["script"][0]["text"][:80] if item["script"] else "",
            }
            for item in versions
        ],
    }


@router.post("/episodes/{episode_id}/rollback")
async def rollback_script(episode_id: str, version: int = Query(...)):
    payload = load_script_version(episode_id, version)
    if not payload:
        raise HTTPException(status_code=404, detail="Version not found")
    save_script(episode_id, payload.get("script", []))
    return {
        "status": "rolled_back",
        "episode_id": episode_id,
        "version": version,
        "script": payload.get("script", []),
    }


@router.post("/episodes/{episode_id}/customer-feedback")
async def customer_feedback(episode_id: str, payload: Dict):
    feedback = str(payload.get("feedback", "")).strip()
    if not feedback:
        raise HTTPException(status_code=400, detail="feedback is required")
    saved = save_feedback(episode_id, feedback)
    return {
        "status": "feedback_recorded",
        "episode_id": episode_id,
        "feedback": saved["feedback"],
        "saved_at": saved["saved_at"],
    }


@router.get("/episodes/{episode_id}/export")
async def export_episode(episode_id: str, format: str = Query("json")):
    detail = load_episode_detail(episode_id)
    script = detail.get("script", [])
    if format == "json":
        return detail
    if format == "txt":
        return {"episode_id": episode_id, "format": "txt", "content": _script_as_text(script)}
    if format == "srt":
        return {"episode_id": episode_id, "format": "srt", "content": _script_as_srt(script)}
    raise HTTPException(status_code=400, detail="Unsupported export format")


@router.get("/audio/{episode_id}/final.mp3")
async def final_audio(episode_id: str):
    from fastapi.responses import FileResponse

    audio_path = _resolve_episode_audio_path(episode_id)
    if not audio_path:
        raise HTTPException(status_code=404, detail="Audio not found")
    return FileResponse(audio_path, media_type="audio/mpeg", filename=audio_path.name)


@router.post("/produce")
async def legacy_produce(payload: EpisodeCreateRequest):
    created = await create_episode(payload)
    return {
        "message": "Legacy produce compatibility route created a draft only.",
        "job_id": created["job_id"],
        "episode_id": created["episode_id"],
        "status": "draft_created",
    }
