import asyncio
import threading
from datetime import datetime
import json
from pathlib import Path
import re
from typing import Dict, List, Optional
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Body
from pydantic import BaseModel
from ..schemas.production import EditScriptRequest
from .assets import _resolve_any_asset
import logging
logger = logging.getLogger(__name__)

from ..core.paths import PROJECT_ROOT
from ..core.settings import load_project_config
from ..schemas.episode import EpisodeCreateRequest
from ..services.production import MergedDandyPodcastWorker
from ..services.production.quality_guard import ScriptQualityGuard
from ..services.production.production_manifest import load_manifest, validate_takes
from ..services.production.production_editor import QcMorb, build_assembly_graph
from ..services.production.production_lifecycle import (
    approve_draft, canonical_versions, create_draft, current_approval,
    editor_state, get_preview_review, save_draft, save_preview_review,
    selected_preview_review,
)
from ..services.social.package_builder import export_social_package
from ..services.storage.episode_store import (
    calculate_repetition_report,
    calculate_script_provenance,
    create_episode_draft,
    episode_dir,
    load_job,
    load_script,
    load_canonical_script,
    load_script_version,
    list_script_versions,
    load_episode_detail,
    list_ads,
    load_ad_settings,
    load_media_cues,
    save_json,
    save_feedback,
    save_script,
)
from ..services.authoring.context import build_context  # noqa: F401  (tests patch it to prove generation never rebuilds context)
from ..services.authoring.pack import render_pack


router = APIRouter(tags=["production"])
_WORKER: MergedDandyPodcastWorker | None = None
_PRODUCTION_SLOT = threading.BoundedSemaphore(1)
from ..services.production.duration import line_seconds, spoken_wpm
_SPOKEN_WPM = spoken_wpm()
_QUALITY_GUARD = ScriptQualityGuard(words_per_minute=_SPOKEN_WPM)
_GENERATION_LOCK = threading.Lock()
_ACTIVE_GENERATION = None
_GENERATION_CANCEL = threading.Event()
_PRODUCTION_CANCEL_EVENTS: dict[str, threading.Event] = {}
_REVISION_LOCK = threading.Lock()
_ACTIVE_REVISIONS: set[str] = set()


class GenerationCancelled(Exception):
    """Cooperative cancellation requested by the operator."""


@router.get("/writer-status")
def writer_status():
    from ..services.production import llm_writer

    return {**llm_writer.writer_status(), 'active_generation_job': _ACTIVE_GENERATION}



class RegenerateProductionLineRequest(BaseModel):
    reason: str = "Operator requested a new take"
    text_change: Optional[str] = None


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
    # Repetition is recorded for owner review only. Repeated product names, slogans
    # and messages are normal in this format and never block production.
    return {**provenance, **repetition}


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


def _estimate_minutes(script: List[Dict], wpm: int = _SPOKEN_WPM) -> float:
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
        if not candidate.resolve().is_relative_to(episode_dir(episode_id).resolve()):
            continue
        if candidate.exists() and candidate.is_file():
            return candidate
    return None


def _enforce_ads_and_structure(script: List[Dict], ads: List[Dict], ad_settings: Dict | None = None,
                               target_seconds: int = 2400) -> List[Dict]:
    policy = (load_project_config().get('production', {}).get('ad_policy', {}) or {})
    if policy.get('model') == 'seven_independent_slots' or 'slots' in (ad_settings or {}):
        from ..services.production.ads import advertising_slots
        slots = advertising_slots(ads, ad_settings)
        by_id = {ad['ad_id']: ad for ad in ads}
        already_inserted = {line.get('ad_id') for line in script if line.get('ad_id')}
        def slot_lines(slot_id):
            slot = next(slot for slot in slots if slot['slot_id'] == slot_id)
            ad_id = slot['assigned_ad_id']
            if not ad_id or ad_id in already_inserted:
                return []
            ad = by_id.get(ad_id)
            if not ad:
                raise ValueError(f'Assigned recording missing for {slot_id}')
            return [{**line, 'ad_id': ad_id, 'ad_slot_id': slot_id, 'ad_line_index': index, 'is_ad': True}
                    for index, line in enumerate(ad['script'], 1)]
        if any(line.get('episode_segment') for line in script if not line.get('is_ad')):
            # Three-segment episodes: ads only before, between and after segments, never inside one.
            from ..services.production.duration import segment_settings
            layout = segment_settings()['ad_layout']
            def placed(position):
                return [entry for slot_id in layout.get(position, []) for entry in slot_lines(slot_id)]
            result = placed('before_segment_1')
            previous = None
            for line in script:
                current = line.get('episode_segment')
                if not line.get('is_ad') and current and previous and current != previous:
                    result.extend(placed(f'after_segment_{previous}'))
                if not line.get('is_ad') and current:
                    previous = current
                result.append(dict(line))
            result.extend(placed(f'after_segment_{previous}' if previous else 'after_segment_3'))
            return _reindex(result)
        result = slot_lines('pre_roll_1') + slot_lines('pre_roll_2')
        host_words = sum(len(str(line.get('text', '')).split()) for line in script if not line.get('is_ad'))
        elapsed_words, next_midroll = 0, 1
        for line in script:
            if not line.get('is_ad'):
                while next_midroll <= 4 and elapsed_words >= host_words * next_midroll / 5:
                    result.extend(slot_lines(f'mid_roll_{next_midroll}'))
                    next_midroll += 1
                elapsed_words += len(str(line.get('text', '')).split())
            result.append(dict(line))
        while next_midroll <= 4:
            result.extend(slot_lines(f'mid_roll_{next_midroll}'))
            next_midroll += 1
        result.extend(slot_lines('post_roll_1'))
        return _reindex(result)
    # Only saved, explicitly created ads. Never invent sponsors, change voices,
    # duplicate a manual insertion, or add another spoken intro/outro here.
    existing = {line.get("ad_id") for line in script if line.get("ad_id")}
    available = [ad for ad in ads if ad.get("ad_id") not in existing]
    result = []
    elapsed = 0.0
    policy = (load_project_config().get("production", {}).get("ad_policy", {}) or {})
    midroll_count = max(0, int(policy.get("midroll_count", 4)))
    ad_duration = max(5, int(policy.get("midroll_duration_seconds", 30)))
    # Space four single ads through the content portion while reserving their
    # time in the final episode target. Never create or duplicate ad records.
    planned_count = min(midroll_count, len(available))
    content_target = max(60.0, float(target_seconds) - planned_count * ad_duration)
    next_break = content_target / (planned_count + 1) if planned_count else float("inf")
    break_spacing = next_break
    break_index = 0
    previous_segment = None
    for line in script:
        segment = line.get("segment_index")
        boundary = previous_segment is not None and segment is not None and segment != previous_segment and not line.get("is_ad")
        has_sections = any(item.get("segment_index") is not None for item in script)
        if (boundary or (not has_sections and elapsed >= next_break)) and available:
            ad = available.pop(0)
            result.extend({**ad_line, "ad_id": ad["ad_id"], "ad_line_index": index, "is_ad": True, "ad_break_index": break_index + 1}
                          for index, ad_line in enumerate(ad.get("script", []), start=1))
            break_index += 1; next_break += break_spacing
        result.append(dict(line))
        if not line.get("is_ad"):
            elapsed += line_seconds(line, _SPOKEN_WPM)
            if segment is not None:
                previous_segment = segment
    return _reindex(result)


def _get_worker() -> MergedDandyPodcastWorker:
    global _WORKER
    from ..core.settings import load_project_config, load_voices_config, load_qwen_tts_config
    if (_WORKER is None or _WORKER.project_config != load_project_config()
            or _WORKER.voices_config != load_voices_config() or _WORKER.qwen_tts_config != load_qwen_tts_config()):
        _WORKER = MergedDandyPodcastWorker(PROJECT_ROOT)
    return _WORKER


@router.post("/episodes/create")
async def create_episode(payload: EpisodeCreateRequest):
    if (episode_dir(payload.episode_id) / "config.json").is_file():
        raise HTTPException(409, "Episode ID already exists; create a new episode or edit its planning record")
    job_id = f"job_{payload.episode_id}_{uuid4().hex[:8]}"
    draft = create_episode_draft(payload.model_dump(), job_id)
    return {
        "message": "Episode draft created",
        "job_id": job_id,
        "episode_id": payload.episode_id,
        "status": draft["status"],
        "config": draft["config"],
    }


@router.get("/episodes/jobs/{job_id}")
def generation_job_status(job_id: str):
    """Return live script-generation or production status for the UI."""
    job = load_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    detail = load_episode_detail(job["episode_id"]) or {}
    status = detail.get("status") or {}
    return {**job, "episode_status": status}


@router.post("/episodes/jobs/{job_id}/cancel")
def cancel_job(job_id: str):
    """Request cooperative cancellation of script generation or production."""
    global _ACTIVE_GENERATION
    job = load_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if _ACTIVE_GENERATION == job_id:
        _GENERATION_CANCEL.set()
        save_json(episode_dir(job['episode_id']).parent / '.drafts' / 'jobs' / f'{job_id}.json',
                  {**job, 'status': 'cancellation_requested', 'updated_at': datetime.now().isoformat()})
        return {"status": "cancellation_requested", "job_id": job_id}
    production_event = _PRODUCTION_CANCEL_EVENTS.get(job_id)
    if production_event is not None:
        production_event.set()
        save_json(episode_dir(job["episode_id"]) / "status.json", {
            "status": "cancellation_requested",
            "updated_at": datetime.now().isoformat(),
            "job_id": job_id,
        })
        return {"status": "cancellation_requested", "job_id": job_id}
    if job.get("status") in {"generating", "producing"}:
        raise HTTPException(status_code=409, detail="The job is no longer active in this backend process")
    return {"status": job.get("status", "idle"), "job_id": job_id}


@router.post("/episodes/generate-script")
def generate_script(
    job_id: str = Query(...),
    payload: Dict | None = Body(default=None),
):
    global _ACTIVE_GENERATION
    job = load_job(job_id)
    if not job:
        raise HTTPException(404, "Generation job not found")
    episode_id = job.get("episode_id")
    detail = load_episode_detail(episode_id)
    if not detail.get("config"):
        raise HTTPException(404, "Episode not found")
    if not _GENERATION_LOCK.acquire(blocking=False):
        raise HTTPException(409, 'A writer request is already running; wait for its result')
    prior_job = dict(job)
    started = datetime.now().isoformat()
    def record(status, **extra):
        save_json(episode_dir(episode_id).parent / '.drafts' / 'jobs' / f'{job_id}.json',
                  {**prior_job, 'status': status, 'started_at': started,
                   'updated_at': datetime.now().isoformat(), **extra})
    try:
        from .library import _assert_episode_idle
        _assert_episode_idle(episode_id)
        from ..services.authoring import generated_drafts
        from ..services.production import llm_writer
        body = payload or {}
        package = generated_drafts.saved_context(episode_id, body.get('context_version_id'))
        if 'brief' in body and body['brief'] != package.get('brief', ''):
            raise ValueError('Brief differs from saved context; build a new package first')
        source_hash = generated_drafts.script_fingerprint(episode_id)
        target = int(package.get('target_seconds') or 1500)
        from ..services.production.ads import advertising_slots
        from ..services.production.duration import dialogue_budget
        slots = (package.get('ad_slots') or {}).get('slots') or advertising_slots(
            list_ads(episode_id), load_ad_settings(episode_id))
        budget = dialogue_budget(target, slots)
        target_words = budget['target_words']
        sample = body.get('sample', False)
        if not isinstance(sample, bool):
            raise ValueError('sample must be true or false')
        _GENERATION_CANCEL.clear()
        _ACTIVE_GENERATION = job_id
        record('generating', context_version_id=package['version_id'], sample=sample, duration_budget=budget)
        def progress(state):
            if not _GENERATION_CANCEL.is_set():  # never overwrite a cancellation request
                record('generating', context_version_id=package['version_id'], sample=sample,
                       duration_budget=budget, progress=state)
        script = llm_writer.generate_episode_script(render_pack(package), target_words=target_words,
                                                    sample=sample, cancel_event=_GENERATION_CANCEL,
                                                    progress=progress)
        if _GENERATION_CANCEL.is_set():
            raise GenerationCancelled('Generation cancelled; the active script was preserved')
        draft = generated_drafts.save_draft(episode_id, package, script, source_hash, sample,
                                         duration_budget=budget)
        record('draft_ready', draft_id=draft['draft_id'], context_version_id=package['version_id'], sample=sample)
        return {**draft, 'job_id': job_id}
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except Exception as exc:
        record('cancelled' if _GENERATION_CANCEL.is_set() else 'failed', error=str(exc))
        raise HTTPException(502, f"Nemotron script generation failed: {exc}") from exc
    finally:
        _ACTIVE_GENERATION = None
        _GENERATION_LOCK.release()


@router.get('/episodes/{episode_id}/writer-draft')
def writer_draft(episode_id: str):
    from ..services.authoring.generated_drafts import latest_draft
    return latest_draft(episode_id)


@router.post('/episodes/{episode_id}/writer-drafts/{draft_id}/accept')
def accept_writer_draft(episode_id: str, draft_id: str):
    from .library import _assert_episode_idle
    from ..services.authoring.generated_drafts import accept_draft
    if not _GENERATION_LOCK.acquire(blocking=False):
        raise HTTPException(409, 'A writer request is running')
    try:
        _assert_episode_idle(episode_id)
        return accept_draft(episode_id, draft_id)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    finally:
        _GENERATION_LOCK.release()


def _run_produce_background(
    episode_id: str, job_id: str, script: list, title: str, topic: str,
    script_text: str, personality_settings, voice_settings: dict,
    writer_engine: str = "unknown", bridge_reachable_at_start: bool = False,
    event_loop=None, approved_production=None,
) -> None:
    """Persist job progress in the worker thread; deliver events on the ASGI loop."""
    from ..websockets.manager import manager

    state = {"episode_id": episode_id, "job_id": job_id, "status": "producing",
             "stage": "starting", "progress": 0.0, "writer_engine": writer_engine}

    def publish(update):
        state.update(update)
        state["updated_at"] = datetime.now().isoformat()
        save_json(episode_dir(episode_id) / "status.json", state)
        save_json(episode_dir(episode_id).parent / ".drafts" / "jobs" / f"{job_id}.json", state)
        if event_loop is not None and not event_loop.is_closed():
            event_type = {"produced": "production_complete", "failed": "production_error"}.get(
                state["status"], "production_progress")
            asyncio.run_coroutine_threadsafe(
                manager.broadcast(episode_id, {**state, "type": event_type}), event_loop
            )

    try:
        publish({})
        # Each job owns its worker so personality settings cannot leak across episodes.
        worker = MergedDandyPodcastWorker()
        worker.cancel_event = _PRODUCTION_CANCEL_EVENTS.get(job_id)
        if personality_settings:
            worker._apply_personality_settings(personality_settings)
        if approved_production is not None:
            current, version_id = current_approval(episode_id)
            if version_id != approved_production.get("approved_version_id"):
                raise RuntimeError("Approved production version changed before synthesis started")
        approval_args = {"approved_production": approved_production} if approved_production is not None else {}
        result = worker.produce_episode(
            episode_id=episode_id, title=title, topic=topic, script_lines=script,
            progress_callback=publish, **approval_args,
        )
        audio_path = Path(result["audio_file"])
        if not audio_path.is_file() or not audio_path.stat().st_size:
            raise RuntimeError("Production returned no audio file")
        manifest = load_manifest(episode_dir(episode_id))
        if manifest:
            build_assembly_graph(episode_dir(episode_id), manifest)
            result["qc_report"] = QcMorb().inspect(episode_dir(episode_id), audio_path)
        metadata = {**calculate_script_provenance(script), **calculate_repetition_report(script),
                    "bridge_reachable_at_start": bridge_reachable_at_start}
        result.setdefault("metadata", {}).update(metadata)
        save_json(episode_dir(episode_id) / "production_result.json", result)
        publish({"stage": "exporting", "progress": 0.95})
        resolved_cues = [
            {**cue, "asset": _resolve_any_asset(episode_id, cue.get("asset_id", "")) or {}}
            for cue in load_media_cues(episode_id).get("cues", [])
        ]
        export_social_package(
            episode_id=episode_id, title=title, topic=topic, script_text=script_text,
            script_lines=script, audio_path=audio_path,
            destination=(PROJECT_ROOT / "social" / "generated" / episode_id).resolve(),
            sponsor_text="Sponsored", media_cues=resolved_cues,
        )
        from ..services.storage.vault_store import preserve_files
        preserved = [p for p in episode_dir(episode_id).rglob('*') if p.is_file() and p.suffix not in {'.lock', '.tmp'}]
        social_folder = PROJECT_ROOT / 'social' / 'generated' / episode_id
        preserved.extend(p for p in social_folder.rglob('*') if p.is_file() and p.suffix not in {'.lock', '.tmp'})
        preserve_files(preserved, 'completed audio and production exports')
        publish({**metadata, "status": "produced", "stage": "completed", "progress": 1.0,
                 "production_mode": "worker", "audio_file": str(audio_path),
                 "engine_stats": result["metadata"].get("engine_stats", {}),
                 "engine_line_stats": result["metadata"].get("engine_line_stats", {}),
                 "synthesized_line_count": result["metadata"].get("synthesized_line_count", 0),
                 "personality_settings": personality_settings, "voice_settings": voice_settings})
    except Exception as exc:
        cancelled = _PRODUCTION_CANCEL_EVENTS.get(job_id)
        publish({"status": "cancelled" if cancelled and cancelled.is_set() else "failed", "failed_stage": state["stage"], "stage": "failed", "error": str(exc)})


def _run_reserved_production(**kwargs):
    try:
        return _run_produce_background(**kwargs)
    finally:
        _PRODUCTION_CANCEL_EVENTS.pop(kwargs.get("job_id"), None)
        _PRODUCTION_SLOT.release()


@router.get("/episodes/{episode_id}/production-status")
async def production_status(episode_id: str):
    from ..services.storage.episode_store import load_json
    return load_json(episode_dir(episode_id) / "status.json") or {"status": "new", "progress": 0}


@router.post("/episodes/produce")
async def produce_episode(
    background_tasks: BackgroundTasks,
    job_id: str = Query(...),
    payload: Dict | None = Body(default=None),
):
    job = load_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job["episode_id"] in _ACTIVE_REVISIONS:
        raise HTTPException(status_code=409, detail="A line revision is running for this episode")

    detail = load_episode_detail(job["episode_id"])
    if detail.get("status") in {"producing", "cancellation_requested"} or job["episode_id"] in _ACTIVE_REVISIONS:
        raise HTTPException(status_code=409, detail="Episode production is already running")
    approved_production = None
    requested_approval = (payload or {}).get("approved_version_id")
    editor_exists = (episode_dir(job["episode_id"]) / "production_editor" / "state.json").is_file()
    if requested_approval or editor_exists:
        try:
            approved_production, approved_version_id = current_approval(job["episode_id"])
        except (ValueError, FileNotFoundError) as exc:
            raise HTTPException(409, str(exc)) from exc
        if requested_approval != approved_version_id:
            raise HTTPException(409, "Produce requires the current approved production version ID")
    script = approved_production["script"] if approved_production else detail.get("script", [])
    if not script:
        raise HTTPException(status_code=400, detail="Approved production version has no script lines")
    require_llm = detail.get("config", {}).get("generation_mode") != "script_feed"
    target_seconds = int(detail.get("config", {}).get("target_duration") or 1800)
    if not 60 <= target_seconds <= 2700:
        raise HTTPException(422, "Episode target must be 1 to 45 minutes. Edit the episode configuration first.")
    target_seconds = int(detail.get("config", {}).get("target_duration") or 2400)
    est_words = sum(len(str(line.get("text", "")).split()) for line in script)
    if est_words == 0:
        raise HTTPException(400, "Script contains no spoken words")
    if not approved_production and target_seconds > 900:
        if est_words < 5000:
            raise HTTPException(400, f"Episode must have at least 5000 words (got {est_words}); use a short target for short scripts")
        script = _enforce_ads_and_structure(
            script, detail.get("ads", []), detail.get("ad_settings"), target_seconds=target_seconds
        )
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

    if not _PRODUCTION_SLOT.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="Studio production is busy; retry after the active job finishes")

    try:
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

        _PRODUCTION_CANCEL_EVENTS[job_id] = threading.Event()
        background_tasks.add_task(
            _run_reserved_production,
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
            event_loop=asyncio.get_running_loop(),
            approved_production=approved_production,
        )
    except BaseException:
        _PRODUCTION_SLOT.release()
        raise

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

    if payload.edit_type == "regenerate_section":
        raise HTTPException(410, "Episode rewriting is external. Export context and import your revised script.")

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
        raise HTTPException(422, "Episode expansion is external. Export context and import a revised script.")
    elif payload.edit_type == "adjust_tone":
        from ..services.production.script_edits import adjust_tone
        if load_episode_detail(payload.episode_id).get("status") == "producing":
            raise HTTPException(409, "Wait for production to finish before adjusting dialogue")
        start = payload.section_start if payload.section_start is not None else 0
        end = payload.section_end if payload.section_end is not None else len(script)
        if not 0 <= start < end <= len(script):
            raise HTTPException(400, "Invalid tone adjustment range")
        if not payload.tone_adjustment or not payload.tone_adjustment.strip():
            raise HTTPException(400, "tone_adjustment is required")
        script = adjust_tone(script, payload.tone_adjustment, start, end)
        save_script(payload.episode_id, script)
        return {"status": "script_ready", "episode_id": payload.episode_id,
                "updated_script": script, "line_count": len(script)}
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


@router.get("/episodes/{episode_id}/production-manifest")
def production_manifest(episode_id: str):
    if not re.fullmatch(r"[A-Za-z0-9_-]+", episode_id):
        raise HTTPException(400, "Invalid episode ID")
    episode_path = episode_dir(episode_id)
    manifest = load_manifest(episode_path)
    if manifest is None:
        raise HTTPException(404, "No addressable production exists for this episode yet")
    try:
        approved, approved_id = current_approval(episode_id)
        manifest["script_current"] = (
            manifest.get("canonical_version_id") == approved.get("canonical_version_id")
            and manifest.get("approved_version_id") == approved_id
            and manifest.get("production_copy_hash") == approved.get("production_copy_hash")
        )
    except (ValueError, FileNotFoundError):
        manifest["script_current"] = False
    return manifest


@router.get("/episodes/{episode_id}/canonical-scripts")
def get_canonical_scripts(episode_id: str):
    if not re.fullmatch(r"[A-Za-z0-9_-]+", episode_id):
        raise HTTPException(400, "Invalid episode ID")
    try:
        return canonical_versions(episode_id)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(404, str(exc)) from exc


@router.get("/episodes/{episode_id}/canonical-scripts/{version_id}")
def get_canonical_script_version(episode_id: str, version_id: str):
    if not re.fullmatch(r"[A-Za-z0-9_-]+", episode_id):
        raise HTTPException(400, "Invalid episode ID")
    try:
        return load_canonical_script(episode_id, version_id)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(404, str(exc)) from exc


@router.get("/episodes/{episode_id}/canonical-scripts/{version_id}/preview")
def get_canonical_preview(episode_id: str, version_id: str):
    if not re.fullmatch(r"[A-Za-z0-9_-]+", episode_id):
        raise HTTPException(400, "Invalid episode ID")
    try:
        return get_preview_review(episode_id, version_id)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(404, str(exc)) from exc


@router.get("/episodes/{episode_id}/preview")
def get_selected_preview(episode_id: str):
    if not re.fullmatch(r"[A-Za-z0-9_-]+", episode_id):
        raise HTTPException(400, "Invalid episode ID")
    try:
        return selected_preview_review(episode_id) or {"episode_id": episode_id, "saved": False}
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(404, str(exc)) from exc


@router.put("/episodes/{episode_id}/preview")
def save_episode_preview(episode_id: str, payload: Dict = Body(...)):
    if not re.fullmatch(r"[A-Za-z0-9_-]+", episode_id):
        raise HTTPException(400, "Invalid episode ID")
    try:
        return save_preview_review(episode_id, payload)
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/episodes/{episode_id}/production-editor/drafts")
def create_production_editor_draft(episode_id: str, payload: Dict = Body(...)):
    if not re.fullmatch(r"[A-Za-z0-9_-]+", episode_id):
        raise HTTPException(400, "Invalid episode ID")
    version_id = str(payload.get("canonical_version_id") or "")
    try:
        return create_draft(episode_id, version_id)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(409, str(exc)) from exc


@router.put("/episodes/{episode_id}/production-editor/draft")
def update_production_editor_draft(episode_id: str, payload: Dict = Body(...)):
    if not re.fullmatch(r"[A-Za-z0-9_-]+", episode_id):
        raise HTTPException(400, "Invalid episode ID")
    try:
        return save_draft(episode_id, payload)
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/episodes/{episode_id}/production-editor/approve")
def approve_production_editor_draft(episode_id: str, payload: Dict = Body(...)):
    if not re.fullmatch(r"[A-Za-z0-9_-]+", episode_id):
        raise HTTPException(400, "Invalid episode ID")
    try:
        return approve_draft(episode_id, str(payload.get("draft_id") or ""))
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get("/episodes/{episode_id}/production-editor")
def production_editor_report(episode_id: str):
    if not re.fullmatch(r"[A-Za-z0-9_-]+", episode_id):
        raise HTTPException(400, "Invalid episode ID")
    state = editor_state(episode_id)
    episode_path = episode_dir(episode_id)
    for key, filename in (("assembly_graph", "assembly_graph.v1.json"), ("qc_report", "qc_report.v1.json")):
        path = episode_path / filename
        state[key] = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None
    return state


@router.get("/episodes/{episode_id}/production-revision")
def production_revision_status(episode_id: str):
    if not re.fullmatch(r"[A-Za-z0-9_-]+", episode_id):
        raise HTTPException(400, "Invalid episode ID")
    path = episode_dir(episode_id) / "revision_status.json"
    if not path.is_file():
        return {"status": "idle", "episode_id": episode_id}
    state = json.loads(path.read_text(encoding="utf-8"))
    if state.get("status") == "running" and episode_id not in _ACTIVE_REVISIONS:
        state.update({"status": "interrupted", "error": "Backend restarted before revision completed",
                      "updated_at": datetime.now().isoformat()})
        save_json(path, state)
    return state


def _run_line_revision_background(
    episode_id: str, segment_id: str, reason: str, text_change: Optional[str], revision_id: str,
    approved_production: dict,
) -> None:
    episode_path = episode_dir(episode_id)
    committed = False
    result = None
    try:
        manifest = load_manifest(episode_path)
        before = next(item for item in manifest["segments"] if item["segment_id"] == segment_id)
        result = _get_worker().regenerate_production_line(
            episode_id, segment_id, reason, text_change, revision_id=revision_id,
            approved_production=approved_production,
        )
        committed = True
        updated = load_manifest(episode_path)
        build_assembly_graph(episode_path, updated)
        QcMorb().inspect(episode_path, Path(result["audio_file"]))
        after = next(item for item in updated["segments"] if item["segment_id"] == segment_id)
        ledger_path = episode_path / "production_change_ledger.json"
        import json
        ledger = json.loads(ledger_path.read_text(encoding="utf-8")) if ledger_path.is_file() else {"episode_id": episode_id, "changes": []}
        ledger["changes"].append({
            "run_id": revision_id, "segment_id": segment_id, "action": "REGENERATE",
            "reason": reason, "before_text": before["production_text"],
            "after_text": after["production_text"], "before_take": before["audio"]["take"],
            "after_take": after["audio"]["take"], "created_at": datetime.now().isoformat(),
        })
        save_json(ledger_path, ledger)
        metadata_path = episode_path / "production_metadata.json"
        if metadata_path.is_file():
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            metadata["last_revision_id"] = revision_id
            metadata["last_revision_at"] = datetime.now().isoformat()
            metadata["processing"] = result["processing"]
            save_json(metadata_path, metadata)
        save_json(episode_path / "revision_status.json", {
            "status": "completed", "revision_id": revision_id, "episode_id": episode_id,
            "segment_id": segment_id, "take": result["take"],
            "updated_at": datetime.now().isoformat(),
        })
    except Exception as exc:
        save_json(episode_path / "revision_status.json", {
            "status": "completed_with_warnings" if committed else "failed",
            "revision_id": revision_id, "episode_id": episode_id,
            "segment_id": segment_id, "error": str(exc),
            "take": result["take"] if result else None,
            "updated_at": datetime.now().isoformat(),
        })
    finally:
        with _REVISION_LOCK:
            _ACTIVE_REVISIONS.discard(episode_id)
        _PRODUCTION_SLOT.release()


@router.post("/episodes/{episode_id}/production/segments/{segment_id}/regenerate", status_code=202)
def regenerate_production_segment(
    episode_id: str, segment_id: str, payload: RegenerateProductionLineRequest,
    background_tasks: BackgroundTasks,
):
    if not re.fullmatch(r"[A-Za-z0-9_-]+", episode_id) or not re.fullmatch(r"[A-Za-z0-9_-]+", segment_id):
        raise HTTPException(400, "Invalid episode or segment ID")
    episode_path = episode_dir(episode_id)
    manifest = load_manifest(episode_path)
    if manifest is None:
        raise HTTPException(409, "Produce this episode once with saved line takes before regenerating a line")
    try:
        approved_production, approved_id = current_approval(episode_id)
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(409, str(exc)) from exc
    if (manifest.get("approved_version_id") != approved_id
            or manifest.get("production_copy_hash") != approved_production.get("production_copy_hash")):
        raise HTTPException(409, "Rendered production does not match the current approved version")
    if not any(item.get("segment_id") == segment_id for item in manifest["segments"]):
        raise HTTPException(404, "Production segment not found")
    if payload.text_change is not None:
        raise HTTPException(422, "Dialogue changes require a new production editor draft and approval")
    status_path = episode_path / "status.json"
    if status_path.is_file():
        import json
        if json.loads(status_path.read_text(encoding="utf-8")).get("status") == "producing":
            raise HTTPException(409, "Episode production is already running")
    try:
        validate_takes(episode_path, manifest["segments"])
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    if not _PRODUCTION_SLOT.acquire(blocking=False):
        raise HTTPException(409, "Studio production is busy; retry after the active job finishes")
    with _REVISION_LOCK:
        if episode_id in _ACTIVE_REVISIONS:
            _PRODUCTION_SLOT.release()
            raise HTTPException(409, "A line revision is already running for this episode")
        _ACTIVE_REVISIONS.add(episode_id)
    revision_id = uuid4().hex
    try:
        save_json(episode_path / "revision_status.json", {
            "status": "running", "revision_id": revision_id, "episode_id": episode_id,
            "segment_id": segment_id, "updated_at": datetime.now().isoformat(),
        })
        background_tasks.add_task(
            _run_line_revision_background, episode_id, segment_id,
            payload.reason, payload.text_change, revision_id, approved_production,
        )
    except Exception:
        with _REVISION_LOCK:
            _ACTIVE_REVISIONS.discard(episode_id)
        _PRODUCTION_SLOT.release()
        raise
    return {"status": "queued", "revision_id": revision_id, "segment_id": segment_id}


@router.get("/audio/{episode_id}/final.mp3")
@router.head("/audio/{episode_id}/final.mp3")
async def final_audio(episode_id: str, download: bool = False):
    from fastapi.responses import FileResponse

    audio_path = _resolve_episode_audio_path(episode_id)
    if not audio_path:
        raise HTTPException(status_code=404, detail="Audio not found")
    return FileResponse(
        audio_path, media_type="audio/mpeg",
        filename=audio_path.name if download else None,
        content_disposition_type="attachment" if download else "inline",
    )


@router.post("/produce")
async def legacy_produce(payload: EpisodeCreateRequest):
    created = await create_episode(payload)
    return {
        "message": "Legacy produce compatibility route created a draft only.",
        "job_id": created["job_id"],
        "episode_id": created["episode_id"],
        "status": "draft_created",
    }
