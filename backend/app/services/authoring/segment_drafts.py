"""Per-segment drafts, approvals and explicit episode assembly.

Each segment keeps its own drafts and approval history. Nothing here replaces
the active canonical script except assemble(), which the owner triggers after
reviewing the assembly preview.
"""
import hashlib
import json
from datetime import datetime, timezone
from uuid import uuid4

from ...core.safety import atomic_json, contained_path, file_lock, validate_id
from ..production.duration import episode_runtime, segment_settings
from ..storage import episode_store as store
from . import segment_plan
from .generated_drafts import saved_context, script_fingerprint
from .review import review_dialogue

COUNT = segment_plan.SEGMENT_COUNT


def _now():
    return datetime.now(timezone.utc).isoformat()


def _sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def _folder(episode_id):
    return store.episode_dir(episode_id) / 'segments'


def _approvals(episode_id):
    path = _folder(episode_id) / 'approvals.json'
    return json.loads(path.read_text(encoding='utf-8')) if path.is_file() else {'segments': {}, 'history': []}


def list_drafts(episode_id, index):
    folder = _folder(episode_id) / f'seg{index}'
    drafts = [json.loads(p.read_text(encoding='utf-8')) for p in folder.glob('segdraft_*.json')]
    return sorted(drafts, key=lambda d: d['created_at'])


def load_draft(episode_id, index, draft_id):
    path = contained_path(_folder(episode_id) / f'seg{index}', validate_id(draft_id) + '.json')
    if not path.is_file():
        raise ValueError('Segment draft was not found')
    draft = json.loads(path.read_text(encoding='utf-8'))
    if draft.get('episode_id') != episode_id or draft.get('segment_index') != index or _sha(draft['script']) != draft.get('script_sha256'):
        raise ValueError('Segment draft integrity check failed')
    return draft


def _stale_reasons(episode_id, plan, approvals, index, context_version):
    record = approvals['segments'].get(str(index))
    if not record:
        return []
    reasons = []
    if plan['context_version_id'] != context_version:
        reasons.append('The saved context changed after this segment was approved')
    if record['fingerprint'] != segment_plan.segment_fingerprint(plan, index):
        reasons.append('The segment plan changed after this segment was approved')
    if index > 1:
        upstream = approvals['segments'].get(str(index - 1))
        if not upstream or upstream['draft_id'] != record.get('upstream_draft_id'):
            reasons.append(f'Segment {index - 1} approval changed after this segment was written')
        elif _stale_reasons(episode_id, plan, approvals, index - 1, context_version):
            reasons.append(f'Segment {index - 1} is stale')
    return reasons


def state(episode_id, active=None):
    """Everything the Segments view shows. `active` is the running job's progress, if any."""
    plan = segment_plan.current_plan(episode_id)
    try:
        context_version = segment_plan.latest_context(episode_id)['version_id']
    except ValueError:
        context_version = None
    approvals = _approvals(episode_id)
    slots = _slots(episode_id)
    result = {'plan': plan, 'context_version_id': context_version, 'segments': [],
              'settings': segment_settings(), 'ad_layout': _layout(slots)}
    if not plan:
        result.update(plan_issues=['Create a segment plan'], plan_stale=False, runtime=None, can_assemble=False)
        return result
    result['plan_issues'] = segment_plan.validate_plan(plan)
    result['plan_notes'] = segment_plan.plan_notes(plan)
    result['plan_stale'] = plan['context_version_id'] != context_version
    words = []
    for index in range(1, COUNT + 1):
        drafts = list_drafts(episode_id, index)
        latest = drafts[-1] if drafts else None
        record = approvals['segments'].get(str(index))
        stale = _stale_reasons(episode_id, plan, approvals, index, context_version)
        blocked = _generation_blocker(plan, approvals, index, context_version, episode_id)
        if active and active.get('segment') == index:
            status = 'generating'
        elif record and latest and latest['draft_id'] == record['draft_id']:
            status = 'stale' if stale else 'approved'
        elif latest:
            status = 'draft_ready'
        else:
            status = 'planned'
        approved = next((d for d in drafts if record and d['draft_id'] == record['draft_id']), None)
        words.append((approved or latest or {}).get('word_count'))
        result['segments'].append({
            'index': index, 'plan': segment_plan.segment_view(plan, index), 'status': status,
            'latest_draft': latest, 'draft_count': len(drafts), 'approved': record, 'stale_reasons': stale,
            'can_generate': blocked is None, 'generate_blocked_reason': blocked,
            'progress': active if active and active.get('segment') == index else None})
    result['runtime'] = episode_runtime([s['talk_minutes'] for s in plan['segments']], slots, actual_words=words)
    result['can_assemble'] = all(s['status'] == 'approved' for s in result['segments'])
    return result


def _slots(episode_id):
    from ..production.ads import advertising_slots
    return advertising_slots(store.list_ads(episode_id), store.load_ad_settings(episode_id))


def _layout(slots):
    by_id = {slot['slot_id']: slot for slot in slots}
    layout = segment_settings()['ad_layout']
    return [{'position': position, 'slots': [by_id[s] for s in layout.get(position, []) if s in by_id]}
            for position in ('before_segment_1', 'after_segment_1', 'after_segment_2', 'after_segment_3')]


def _generation_blocker(plan, approvals, index, context_version, episode_id):
    if not plan.get('locked'):
        return 'Lock the segment plan first'
    if plan['context_version_id'] != context_version:
        return 'The saved context changed; start and lock a new plan'
    if index > 1:
        if str(index - 1) not in approvals['segments']:
            return f'Approve segment {index - 1} first'
        if _stale_reasons(episode_id, plan, approvals, index - 1, context_version):
            return f'Segment {index - 1} is stale; regenerate and approve it first'
    return None


def _approved_script(episode_id, approvals, index):
    record = approvals['segments'].get(str(index))
    return load_draft(episode_id, index, record['draft_id'])['script'] if record else []


def generate(episode_id, index, cancel_event=None, progress=None):
    """Write one segment as a new draft. Other segments' drafts and approvals are untouched."""
    from ..production import llm_writer
    from .pack import render_pack
    plan = segment_plan.current_plan(episode_id)
    if not plan:
        raise ValueError('Create and lock a segment plan first')
    context_version = segment_plan.latest_context(episode_id)['version_id']
    approvals = _approvals(episode_id)
    blocked = _generation_blocker(plan, approvals, index, context_version, episode_id)
    if blocked:
        raise ValueError(blocked)
    package = saved_context(episode_id, plan['context_version_id'])
    settings = segment_settings()
    covered = []
    for earlier in range(1, index):
        view = segment_plan.segment_view(plan, earlier)
        covered += view['beats'] + view['point_texts']
    upstream = approvals['segments'].get(str(index - 1)) if index > 1 else None
    previous_lines = (upstream or {}).get('continuity', {}).get('last_lines', [])
    segment = segment_plan.segment_view(plan, index)
    written = llm_writer.write_segment(
        render_pack(package), segment=segment, segment_count=COUNT, target_words=segment['target_words'],
        max_pass_words=settings['max_pass_words'], covered_before=covered, previous_lines=previous_lines,
        requirements=plan['episode_requirements'], continuity_lines=settings['continuity_lines'],
        cancel_event=cancel_event, progress=progress)
    if cancel_event is not None and cancel_event.is_set():
        raise RuntimeError('Generation cancelled; no segment draft was saved')
    earlier_lines = [line for k in range(1, index) for line in _approved_script(episode_id, approvals, k)]
    script = written['script']
    draft = {'draft_id': 'segdraft_' + uuid4().hex, 'episode_id': episode_id, 'segment_index': index,
             'created_at': _now(), 'context_version_id': plan['context_version_id'],
             'plan_revision': plan['plan_revision'], 'fingerprint': segment_plan.segment_fingerprint(plan, index),
             'upstream_draft_id': (upstream or {}).get('draft_id'), 'target_words': segment['target_words'],
             'word_count': written['word_count'], 'passes': written['passes'], 'script': script,
             'script_sha256': _sha(script), 'review_warnings': review_dialogue(script, earlier_lines),
             'writer_engine': 'nemotron'}
    path = _folder(episode_id) / f'seg{index}' / f"{draft['draft_id']}.json"
    atomic_json(path, draft)
    from ..storage.vault_store import preserve_files
    preserve_files([path], f'segment {index} draft saved; active script unchanged')
    return draft


def approve(episode_id, index, draft_id):
    """Owner approval of one segment draft. Review warnings are shown, not enforced."""
    with file_lock(_folder(episode_id) / 'approval-update'):
        plan = segment_plan.current_plan(episode_id)
        if not plan or not plan.get('locked'):
            raise ValueError('Lock the segment plan first')
        context_version = segment_plan.latest_context(episode_id)['version_id']
        approvals = _approvals(episode_id)
        draft = load_draft(episode_id, index, draft_id)
        if draft['fingerprint'] != segment_plan.segment_fingerprint(plan, index) or plan['context_version_id'] != context_version:
            raise ValueError('This draft was written from a different plan or context; regenerate it')
        if index > 1:
            upstream = approvals['segments'].get(str(index - 1))
            if not upstream:
                raise ValueError(f'Approve segment {index - 1} first')
            if _stale_reasons(episode_id, plan, approvals, index - 1, context_version):
                raise ValueError(f'Segment {index - 1} is stale; approve a current version first')
            if draft['upstream_draft_id'] != upstream['draft_id']:
                raise ValueError(f'This draft continues an older segment {index - 1}; regenerate it')
        lines = draft['script']
        view = segment_plan.segment_view(plan, index)
        record = {'draft_id': draft_id, 'approved_at': _now(), 'fingerprint': draft['fingerprint'],
                  'upstream_draft_id': draft['upstream_draft_id'], 'word_count': draft['word_count'],
                  'continuity': {'title': view['title'], 'beats': view['beats'], 'point_texts': view['point_texts'],
                                 'last_lines': [{'speaker': l['speaker'], 'text': l['text']}
                                                for l in lines[-segment_settings()['continuity_lines']:]]}}
        previous = approvals['segments'].get(str(index))
        approvals['segments'][str(index)] = record
        approvals['history'].append({'segment_index': index, 'draft_id': draft_id, 'approved_at': record['approved_at'],
                                     'replaced_draft_id': (previous or {}).get('draft_id')})
        path = _folder(episode_id) / 'approvals.json'
        atomic_json(path, approvals)
        from ..storage.vault_store import preserve_files
        preserve_files([path], f'segment {index} approved')
        return record


def assembly_preview(episode_id):
    """What Assemble Episode would save, with a duration report. Changes nothing."""
    view = state(episode_id)
    if not view['can_assemble']:
        blockers = [f"Segment {s['index']}: {s['status']}" for s in view['segments'] if s['status'] != 'approved']
        raise ValueError('Approve all three current segments first. ' + '; '.join(blockers))
    approvals = _approvals(episode_id)
    script, warnings, segments = [], [], []
    for index in range(1, COUNT + 1):
        draft = load_draft(episode_id, index, approvals['segments'][str(index)]['draft_id'])
        for line in draft['script']:
            script.append({**line, 'episode_segment': index})
        warnings += [{**w, 'segment_index': index} for w in draft.get('review_warnings', [])]
        segments.append({'segment_index': index, 'draft_id': draft['draft_id'], 'turns': len(draft['script']),
                         'word_count': draft['word_count']})
    for number, line in enumerate(script, 1):
        line['line_number'] = number
    active_hash = script_fingerprint(episode_id)
    preview = {'episode_id': episode_id, 'plan_revision': view['plan']['plan_revision'],
               'context_version_id': view['plan']['context_version_id'], 'segments': segments,
               'script': script, 'word_count': sum(s['word_count'] for s in segments),
               'runtime': view['runtime'], 'ad_layout': view['ad_layout'], 'review_warnings': warnings,
               'active_script_hash': active_hash}
    preview['preview_sha256'] = _sha({k: preview[k] for k in ('segments', 'script', 'active_script_hash', 'plan_revision')})
    return preview


def assemble(episode_id, preview_sha256):
    """Explicit owner action: save the reviewed preview as the active canonical script."""
    with file_lock(store.episode_dir(episode_id) / 'episode-update'):
        preview = assembly_preview(episode_id)
        if preview['preview_sha256'] != preview_sha256:
            raise ValueError('The segments or the active script changed since the preview; review the new preview')
        result = store._save_canonical_snapshot(episode_id, preview['script'], project_active=True, save_legacy_version=True)
    record = {**{k: v for k, v in preview.items() if k != 'script'}, 'assembled_at': _now(),
              'canonical_version_id': result['version_id']}
    path = _folder(episode_id) / 'assemblies' / f"assembly_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}.json"
    atomic_json(path, record)
    from ..storage.vault_store import preserve_files
    preserve_files([path], 'episode assembled from approved segments')
    return record
