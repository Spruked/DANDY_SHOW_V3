"""Owner-controlled three-segment plan, saved with the context version it was built from."""
import hashlib
import json
import re
from copy import deepcopy
from datetime import datetime, timezone

from ...core.safety import atomic_json, file_lock
from ..production.duration import segment_settings, segment_word_budget
from ..storage import episode_store as store

SEGMENT_COUNT = 3
MIN_BEATS, MAX_BEATS = 4, 8
_OPENING = re.compile(r"\b(welcome (to|back)|open(s|ing)? the (show|episode)|introduc(e|es|ing) the show|"
                      r"introduc(e|es|ing) (phil|jim|the hosts))\b", re.I)
_CLOSING = re.compile(r"\b(sign(s|ing)?[- ]off|goodbye|thanks? (you )?for listening|"
                      r"(close|closes|closing|wrap|wraps|wrapping) (up )?the (show|episode))\b", re.I)


def _now():
    return datetime.now(timezone.utc)


def _folder(episode_id):
    return store.episode_dir(episode_id) / 'segments'


def latest_context(episode_id):
    path = store.episode_dir(episode_id) / 'context_packages' / 'latest.json'
    if not path.is_file():
        raise ValueError('Build and save a context package before planning segments')
    return json.loads(path.read_text(encoding='utf-8'))


def must_include_items(direction):
    """Split Must include into assignable points and episode-wide requirements.

    Paragraphs containing semicolons are lists of points; other paragraphs are
    episode-wide requirements. Wording is preserved exactly (only surrounding
    whitespace is trimmed) and every item records where it came from.
    """
    text = str(direction.get('must_include') or '')
    paragraphs = [p.strip() for p in re.split(r'\r?\n', text) if p.strip()]
    revision = direction.get('revision_id') or ''
    points, requirements = [], []
    for p_index, paragraph in enumerate(paragraphs, 1):
        source = {'direction_revision_id': revision, 'field': 'must_include', 'paragraph': p_index}
        if ';' in paragraph:
            for i_index, item in enumerate((part.strip() for part in paragraph.split(';')), 1):
                if item:
                    points.append({'id': f'p{p_index}_{i_index}', 'text': item, 'source': {**source, 'item': i_index}})
        else:
            requirements.append({'id': f'r{p_index}', 'text': paragraph, 'source': source,
                                 'role': 'episode_requirement', 'primary_segment': None})
    return points, requirements


def current_plan(episode_id):
    path = _folder(episode_id) / 'plan.json'
    return json.loads(path.read_text(encoding='utf-8')) if path.is_file() else None


def _write(episode_id, plan, parent):
    stamp = _now()
    plan = {**plan, 'plan_revision': 'plan_' + stamp.strftime('%Y%m%dT%H%M%S%fZ'),
            'parent_revision': parent, 'saved_at': stamp.isoformat()}
    folder = _folder(episode_id)
    version_path = folder / 'plan_versions' / f"{plan['plan_revision']}.json"
    atomic_json(version_path, plan)
    from ..storage.vault_store import preserve_files
    preserve_files([version_path], 'segment plan revision saved')
    atomic_json(folder / 'plan.json', plan)
    return plan


def _check_revision(current, expected_revision):
    if (current or {}).get('plan_revision', '') != (expected_revision or ''):
        raise ValueError('The segment plan changed elsewhere. Reload before saving.')


def new_plan(episode_id, expected_revision=None, proposal=None, proposed_by='owner'):
    """Start a plan from the latest saved context. Earlier revisions stay in history."""
    package = latest_context(episode_id)
    settings = segment_settings()
    with file_lock(_folder(episode_id) / 'plan-update'):
        current = current_plan(episode_id)
        _check_revision(current, expected_revision)
        if current and current.get('locked'):
            raise ValueError('Unlock the current plan before replacing it')
        points, requirements = must_include_items(package.get('owner_direction') or {})
        segments = [{'index': n, 'title': '', 'focus': '', 'beats': [], 'point_ids': [],
                     'talk_minutes': settings['talk_minutes']} for n in range(1, SEGMENT_COUNT + 1)]
        known = {point['id'] for point in points}
        for segment, proposed in zip(segments, (proposal or {}).get('segments', [])):
            segment.update(title=str(proposed.get('title', ''))[:200], focus=str(proposed.get('focus', ''))[:1000],
                           beats=[str(b).strip()[:400] for b in proposed.get('beats', []) if str(b).strip()][:MAX_BEATS],
                           point_ids=[p for p in proposed.get('point_ids', []) if p in known])
        plan = {'schema_version': 1, 'episode_id': episode_id, 'context_version_id': package['version_id'],
                'direction_revision_id': (package.get('owner_direction') or {}).get('revision_id', ''),
                'locked': False, 'locked_at': None, 'proposed_by': proposed_by,
                'points': points, 'episode_requirements': requirements, 'segments': segments}
        return _write(episode_id, plan, current.get('plan_revision') if current else None)


def save_plan(episode_id, value, expected_revision):
    """Owner edits: segment fields and requirement roles. Point wording is fixed by the direction."""
    settings = segment_settings()
    with file_lock(_folder(episode_id) / 'plan-update'):
        current = current_plan(episode_id)
        if not current:
            raise ValueError('Create a segment plan first')
        _check_revision(current, expected_revision)
        if current.get('locked'):
            raise ValueError('Unlock the plan before editing it')
        plan = deepcopy(current)
        incoming = {s.get('index'): s for s in (value.get('segments') or []) if isinstance(s, dict)}
        for segment in plan['segments']:
            edit = incoming.get(segment['index'])
            if not edit:
                continue
            beats = edit.get('beats', segment['beats'])
            ids = edit.get('point_ids', segment['point_ids'])
            if not isinstance(beats, list) or not isinstance(ids, list):
                raise ValueError('Beats and assigned points must be lists')
            minutes = float(edit.get('talk_minutes', segment['talk_minutes']))
            if not settings['min_talk_minutes'] <= minutes <= settings['max_talk_minutes']:
                raise ValueError(f"Talk length must be {settings['min_talk_minutes']}-{settings['max_talk_minutes']} minutes")
            segment.update(title=str(edit.get('title', segment['title']))[:200],
                           focus=str(edit.get('focus', segment['focus']))[:1000],
                           beats=[str(b)[:400] for b in beats], point_ids=[str(i) for i in ids],
                           talk_minutes=minutes)
        roles = {r.get('id'): r for r in (value.get('episode_requirements') or []) if isinstance(r, dict)}
        for requirement in plan['episode_requirements']:
            edit = roles.get(requirement['id'])
            if edit:
                if edit.get('primary_segment') not in (None, 1, 2, 3):
                    raise ValueError('Primary segment must be 1, 2, 3 or none')
                if edit.get('role') not in ('episode_requirement', 'episode_metadata', 'editorial_requirement'):
                    raise ValueError('Unknown requirement role')
                requirement.update(primary_segment=edit.get('primary_segment'), role=edit['role'])
        return _write(episode_id, plan, current['plan_revision'])


def validate_plan(plan):
    """Rules a plan must pass before it can be locked. Returns readable issues."""
    issues = []
    segments = plan.get('segments') or []
    if [s.get('index') for s in segments] != list(range(1, SEGMENT_COUNT + 1)):
        return ['A plan has exactly three segments, numbered 1 to 3']
    assigned = {}
    known = {p['id']: p for p in plan.get('points', [])}
    for segment in segments:
        n = segment['index']
        if not str(segment.get('title', '')).strip():
            issues.append(f'Segment {n} needs a title')
        if not str(segment.get('focus', '')).strip():
            issues.append(f'Segment {n} needs a topic focus')
        beats = [str(b).strip() for b in segment.get('beats', [])]
        if any(not b for b in beats):
            issues.append(f'Segment {n} has an empty beat')
        if not MIN_BEATS <= len(beats) <= MAX_BEATS:
            issues.append(f'Segment {n} has {len(beats)} beats; use {MIN_BEATS}-{MAX_BEATS}')
        for b_index, beat in enumerate(beats, 1):
            if n > 1 and _OPENING.search(beat):
                issues.append(f'Segment {n} beat {b_index} opens the show; only segment 1 opens')
            if n < SEGMENT_COUNT and _CLOSING.search(beat):
                issues.append(f'Segment {n} beat {b_index} closes or signs off; only segment 3 closes')
        for point_id in segment.get('point_ids', []):
            if point_id not in known:
                issues.append(f'Segment {n} refers to an unknown must-include point')
            elif point_id in assigned:
                issues.append(f'"{known[point_id]["text"][:60]}" is assigned to segments {assigned[point_id]} and {n}')
            else:
                assigned[point_id] = n
    for point_id, point in known.items():
        if point_id not in assigned:
            issues.append(f'Must-include point not assigned: "{point["text"][:80]}"')
    return issues


def plan_notes(plan):
    """Informational only. Topics and messages may recur; the owner decides."""
    notes, seen = [], {}
    for segment in plan.get('segments') or []:
        for beat in segment.get('beats', []):
            key = re.sub(r'[^\w\s]', '', str(beat).lower()).strip()
            if key and key in seen and seen[key] != segment['index']:
                notes.append(f'Beat "{str(beat)[:60]}" appears in segments {seen[key]} and {segment["index"]}; '
                             'fine if the topic is meant to return')
            seen.setdefault(key, segment['index'])
    return notes


def lock_plan(episode_id, expected_revision):
    with file_lock(_folder(episode_id) / 'plan-update'):
        current = current_plan(episode_id)
        if not current:
            raise ValueError('Create a segment plan first')
        _check_revision(current, expected_revision)
        if current.get('locked'):
            return current
        if current['context_version_id'] != latest_context(episode_id)['version_id']:
            raise ValueError('The plan was made from an older context version; start a new plan from the current context')
        issues = validate_plan(current)
        if issues:
            raise ValueError('Plan cannot be locked: ' + '; '.join(issues))
        return _write(episode_id, {**current, 'locked': True, 'locked_at': _now().isoformat()}, current['plan_revision'])


def unlock_plan(episode_id, expected_revision):
    with file_lock(_folder(episode_id) / 'plan-update'):
        current = current_plan(episode_id)
        if not current:
            raise ValueError('Create a segment plan first')
        _check_revision(current, expected_revision)
        if not current.get('locked'):
            return current
        return _write(episode_id, {**current, 'locked': False, 'locked_at': None}, current['plan_revision'])


def segment_view(plan, index):
    """The plan entry a writer and its drafts depend on, with assigned point wording."""
    segment = next(s for s in plan['segments'] if s['index'] == index)
    texts = {p['id']: p['text'] for p in plan['points']}
    return {**segment, 'point_texts': [texts[i] for i in segment['point_ids'] if i in texts],
            'target_words': segment_word_budget(segment['talk_minutes'])}


def segment_fingerprint(plan, index):
    """Changes when anything this segment was written from changes."""
    payload = {'context_version_id': plan['context_version_id'], 'segment': segment_view(plan, index),
               'requirements': plan['episode_requirements']}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def proposal_prompt(package, plan):
    direction = package.get('owner_direction') or {}
    points = "\n".join(f"- {p['id']}: {p['text']}" for p in plan['points']) or '- (none)'
    requirements = "\n".join(f"- {r['text']}" for r in plan['episode_requirements']) or '- (none)'
    return f"""Plan a Dandy Show episode as exactly three spoken segments of about {plan['segments'][0]['talk_minutes']:g} minutes each.
Phil and Jim talk; advertising breaks fall between segments.

Topic: {package.get('topic', '')}
Episode description: {package.get('description', '')}
Brief: {package.get('brief', '') or '(none)'}
Owner direction: {direction.get('episode_direction', '')}
Angle and tone: {direction.get('angle_and_tone', '')}
Segment notes: {direction.get('segment_notes', '')}
Must avoid: {direction.get('must_avoid', '')}
Episode-wide requirements:
{requirements}
Must-include points (assign each id to exactly one segment):
{points}

Rules: segment 1 opens the show; only segment 3 closes and signs off; {MIN_BEATS}-{MAX_BEATS} short beats per segment;
every must-include id is used exactly once. Each segment should move the conversation forward; product names,
benefits and key messages may recur across segments.
Return ONLY a JSON object: {{"segments": [{{"title": "...", "focus": "...", "beats": ["..."], "point_ids": ["p1_1"]}}, ...three items]}}"""


def parse_proposal(raw):
    candidate = (raw or '').strip()
    if candidate.startswith('```'):
        candidate = re.sub(r'^```(?:json)?\s*|\s*```$', '', candidate, flags=re.I | re.S).strip()
    try:
        value = json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise ValueError('The plan proposal was not valid JSON; nothing was changed') from exc
    segments = value.get('segments') if isinstance(value, dict) else None
    if not isinstance(segments, list) or len(segments) != SEGMENT_COUNT or not all(isinstance(s, dict) for s in segments):
        raise ValueError('The plan proposal must contain exactly three segments; nothing was changed')
    return {'segments': segments}


def propose_plan(episode_id, expected_revision=None, cancel_event=None):
    """Owner-triggered: one short Nemotron request, saved as an unlocked, editable revision."""
    from ..production import llm_writer
    package = latest_context(episode_id)
    current = current_plan(episode_id)
    if current and current.get('locked'):
        raise ValueError('Unlock the current plan before requesting a proposal')
    skeleton = {'points': must_include_items(package.get('owner_direction') or {})[0],
                'episode_requirements': must_include_items(package.get('owner_direction') or {})[1],
                'segments': [{'talk_minutes': segment_settings()['talk_minutes']}]}
    raw = llm_writer._call_nvidia(proposal_prompt(package, skeleton), kind='segment-plan', cancel_event=cancel_event)
    return new_plan(episode_id, expected_revision, parse_proposal(raw), proposed_by='nemotron')
