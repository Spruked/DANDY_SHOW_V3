"""Three-segment authoring routes. Writer calls share the existing generation lock,
cancel flag and job record, so the Context Generator's cancel button works unchanged."""
from datetime import datetime
from typing import Dict

from fastapi import APIRouter, Body, HTTPException, Query

from . import production as prod
from ..services.authoring import segment_drafts, segment_plan
from ..services.storage.episode_store import episode_dir, load_job, save_json

router = APIRouter(tags=["segments"])


def _job_progress(episode_id):
    """Progress of a segment writer job currently running for this episode, if any."""
    if not prod._ACTIVE_GENERATION:
        return None
    job = load_job(prod._ACTIVE_GENERATION) or {}
    return job.get('progress') if job.get('episode_id') == episode_id else None


def _run_writer(job_id, work):
    """Run one owner-triggered writer request under the shared lock and job record."""
    job = load_job(job_id)
    if not job:
        raise HTTPException(404, 'Generation job not found')
    episode_id = job['episode_id']
    if not prod._GENERATION_LOCK.acquire(blocking=False):
        raise HTTPException(409, 'A writer request is already running; wait for its result')
    prior, started = dict(job), datetime.now().isoformat()

    def record(status, **extra):
        save_json(episode_dir(episode_id).parent / '.drafts' / 'jobs' / f'{job_id}.json',
                  {**prior, 'status': status, 'started_at': started, 'updated_at': datetime.now().isoformat(), **extra})

    def progress(state):
        if not prod._GENERATION_CANCEL.is_set():  # never overwrite a cancellation request
            record('generating', progress=state)
    try:
        from .library import _assert_episode_idle
        _assert_episode_idle(episode_id)
        prod._GENERATION_CANCEL.clear()
        prod._ACTIVE_GENERATION = job_id
        record('generating', progress={'stage': 'starting'})
        result = work(episode_id, progress)
        if prod._GENERATION_CANCEL.is_set():
            raise RuntimeError('Generation cancelled; nothing was saved')
        record('draft_ready', progress=None)
        return result
    except HTTPException:
        raise
    except ValueError as exc:
        record('failed', error=str(exc), progress=None)
        raise HTTPException(422, str(exc)) from exc
    except Exception as exc:
        record('cancelled' if prod._GENERATION_CANCEL.is_set() else 'failed', error=str(exc), progress=None)
        raise HTTPException(502, f'Nemotron request failed: {exc}') from exc
    finally:
        prod._ACTIVE_GENERATION = None
        prod._GENERATION_LOCK.release()


def _owner_action(fn):
    try:
        return fn()
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get('/episodes/{episode_id}/segments')
def segments_state(episode_id: str):
    return segment_drafts.state(episode_id, active=_job_progress(episode_id))


@router.post('/episodes/{episode_id}/segment-plan/new')
def new_segment_plan(episode_id: str, payload: Dict = Body(default={})):
    return _owner_action(lambda: segment_plan.new_plan(episode_id, payload.get('expected_revision')))


@router.put('/episodes/{episode_id}/segment-plan')
def save_segment_plan(episode_id: str, payload: Dict = Body(...)):
    return _owner_action(lambda: segment_plan.save_plan(episode_id, payload.get('plan') or {}, payload.get('expected_revision')))


@router.post('/episodes/{episode_id}/segment-plan/lock')
def lock_segment_plan(episode_id: str, payload: Dict = Body(default={})):
    return _owner_action(lambda: segment_plan.lock_plan(episode_id, payload.get('expected_revision')))


@router.post('/episodes/{episode_id}/segment-plan/unlock')
def unlock_segment_plan(episode_id: str, payload: Dict = Body(default={})):
    return _owner_action(lambda: segment_plan.unlock_plan(episode_id, payload.get('expected_revision')))


@router.post('/episodes/segment-plan/propose')
def propose_segment_plan(job_id: str = Query(...), payload: Dict = Body(default={})):
    """Optional and owner-triggered: one short Nemotron request."""
    return _run_writer(job_id, lambda episode_id, progress: segment_plan.propose_plan(
        episode_id, payload.get('expected_revision'), cancel_event=prod._GENERATION_CANCEL))


@router.post('/episodes/segments/{index}/generate')
def generate_segment(index: int, job_id: str = Query(...)):
    if index not in (1, 2, 3):
        raise HTTPException(404, 'Segments are numbered 1 to 3')
    return _run_writer(job_id, lambda episode_id, progress: segment_drafts.generate(
        episode_id, index, cancel_event=prod._GENERATION_CANCEL, progress=progress))


@router.get('/episodes/{episode_id}/segments/{index}/drafts')
def segment_draft_history(episode_id: str, index: int):
    return {'drafts': segment_drafts.list_drafts(episode_id, index)}


@router.post('/episodes/{episode_id}/segments/{index}/drafts/{draft_id}/approve')
def approve_segment_draft(episode_id: str, index: int, draft_id: str):
    if not prod._GENERATION_LOCK.acquire(blocking=False):
        raise HTTPException(409, 'A writer request is running')
    try:
        return _owner_action(lambda: segment_drafts.approve(episode_id, index, draft_id))
    finally:
        prod._GENERATION_LOCK.release()


@router.get('/episodes/{episode_id}/segments/assembly-preview')
def assembly_preview(episode_id: str):
    return _owner_action(lambda: segment_drafts.assembly_preview(episode_id))


@router.post('/episodes/{episode_id}/segments/assemble')
def assemble_episode(episode_id: str, payload: Dict = Body(...)):
    """Explicit owner action only; requires the preview hash the owner reviewed."""
    from .library import _assert_episode_idle
    if not prod._GENERATION_LOCK.acquire(blocking=False):
        raise HTTPException(409, 'A writer request is running')
    try:
        _assert_episode_idle(episode_id)
        return _owner_action(lambda: segment_drafts.assemble(episode_id, str(payload.get('preview_sha256') or '')))
    finally:
        prod._GENERATION_LOCK.release()
