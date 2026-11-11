"""Three-segment episodes: budgeting, plan, per-segment drafts, assembly. No provider calls."""
import json
import re
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import create_app
from app.api import ads, production
from app.services.authoring import review, segment_drafts, segment_plan
from app.services.production import duration, llm_writer as writer
from app.services.production.ads import AD_SLOT_IDS
from app.services.storage import episode_store as store

MUST_INCLUDE = ("The founder's motivation; denied parenting time and blocked communication; the importance of both "
                "corroborating and contradicting evidence; desktop case organization; Android and iOS field "
                "documentation; fairness to parents and protection of children.\n\n"
                "This episode airs at full launch. Present the desktop, Android and iOS apps as available.\n\n"
                "Founder motivation (owner-approved, use as stated): the record speaks.")
RESERVED = [{'slot_id': s, 'status': 'reserved'} for s in AD_SLOT_IDS]


class FakeNemotron:
    """Returns fresh PHIL:/JIM: lines sized to the request and records every prompt."""

    def __init__(self):
        self.prompts = []

    def __call__(self, prompt, **kwargs):
        self.prompts.append(prompt)
        first = re.search(r'The first turn is (PHIL|JIM)', prompt).group(1)
        words = int(re.search(r'Write about (\d+) spoken words', prompt).group(1))
        other = 'JIM' if first == 'PHIL' else 'PHIL'
        lines = []
        for i in range(max(2, round(words / 16))):
            n = len(self.prompts) * 1000 + i
            lines.append(f"{first if i % 2 == 0 else other}: Call {n} brings a fresh thought about records and "
                         f"presence that moves this talk forward a little more today.")
        return "\n".join(lines)


class BudgetTests(unittest.TestCase):
    def test_three_segment_runtime_and_words(self):
        self.assertEqual(duration.segment_word_budget(10), 1500)
        self.assertEqual(duration.episode_runtime([10] * 3, RESERVED)['runtime_seconds'], 2039.4)
        self.assertEqual(duration.episode_runtime([12] * 3, RESERVED)['runtime_seconds'], 2399.4)
        report = duration.episode_runtime([10] * 3, RESERVED, actual_words=[1500, None, 750])
        self.assertEqual(report['segments'][2]['estimated_talk_seconds'], 300.0)
        self.assertEqual(report['target_words'], 4500)

    def test_must_include_split_preserves_wording_and_sources(self):
        points, requirements = segment_plan.must_include_items({'must_include': MUST_INCLUDE, 'revision_id': 'direction_x'})
        self.assertEqual(len(points), 6)
        self.assertEqual(points[0]['text'], "The founder's motivation")
        self.assertEqual(points[-1]['text'], 'fairness to parents and protection of children.')
        self.assertEqual(points[2]['source'], {'direction_revision_id': 'direction_x', 'field': 'must_include',
                                               'paragraph': 1, 'item': 3})
        self.assertEqual([r['text'][:21] for r in requirements], ['This episode airs at ', 'Founder motivation (o'])


class ParserAndReviewTests(unittest.TestCase):
    def test_transcript_lines_and_labels(self):
        parsed = writer.parse_dialogue("PHIL: Phil: Hello there, Jim.\nJIM: Good to be here.")
        self.assertEqual(parsed[0]['text'], 'Hello there, Jim.')
        self.assertEqual(parsed[1]['pause_after'], writer.DEFAULT_TRANSCRIPT_PAUSE)
        with self.assertRaisesRegex(RuntimeError, 'carries the JIM: label'):
            writer.parse_dialogue("PHIL: Jim: That is mine to say.\nJIM: Indeed it is.")

    def test_slogans_and_names_are_not_flagged_but_copied_exchanges_are(self):
        slogan = 'POPS lets the record speak.'
        lines = [{'speaker': 'phil' if i % 2 == 0 else 'jim', 'text': t} for i, t in enumerate([
            slogan, 'Tell me more about POPS.', slogan, 'POPS again, I love it.',
            'The desktop app organizes the whole case into one timeline you can review.',
            'And the phone captures what happens out in the field as it happens.',
            'The desktop app organizes the whole case into one timeline you can review.',
            'And the phone captures what happens out in the field as it happens.'])]
        warnings = review.review_dialogue(lines)
        self.assertEqual([w['kind'] for w in warnings], ['duplicate_exchange'])
        self.assertEqual((warnings[0]['line'], warnings[0]['end_line']), (7, 8))
        self.assertTrue(warnings[0]['informational'])

    def test_repetition_never_blocks_production(self):
        lines = [{'speaker': 'phil', 'text': 'POPS lets the record speak.', 'generated_by': 'nemotron'}] * 3
        meta = production._assert_llm_script_publishable(lines)
        self.assertFalse(meta['repetition_guard_passed'])  # recorded, not enforced


class SegmentWorkflow(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        for name, value in [('EPISODES_ROOT', self.root / 'episodes'),
                            ('DRAFTS_ROOT', self.root / 'episodes/.drafts'),
                            ('JOBS_ROOT', self.root / 'episodes/.drafts/jobs')]:
            self.stack.enter_context(patch.object(store, name, value))
        self.stack.enter_context(patch.object(ads, 'EPISODES_ROOT', store.EPISODES_ROOT))
        self.client = self.stack.enter_context(TestClient(create_app(runtime_root=self.root, recover_jobs=False)))
        created = self.client.post('/api/episodes/create', json={'episode_id': 'seg', 'title': 'Seg', 'topic': 'POPS',
                                                               'target_duration': 1500})
        self.job = created.json()['job_id']
        self.client.post('/api/episodes/seg/context/sources/text', json={'title': 'Facts', 'text': 'Approved facts.'})
        built = self.client.post('/api/episodes/seg/context', json={'brief': 'Brief.', 'owner_direction': {'must_include': MUST_INCLUDE}})
        self.assertEqual(built.status_code, 200, built.text)
        store.save_script('seg', [{'speaker': 'phil', 'text': 'Existing script.'}])
        self.script_before = (store.episode_dir('seg') / 'script.json').read_bytes()
        self.fake = FakeNemotron()
        self.stack.enter_context(patch.object(writer, '_call_nvidia', side_effect=self.fake))

    # helpers -----------------------------------------------------------
    def plan(self):
        return self.client.get('/api/episodes/seg/segments').json()['plan']

    def valid_plan_body(self):
        ids = [p['id'] for p in self.plan()['points']]
        beats = lambda n: [f'Segment {n} beat {b}' for b in range(1, 5)]  # noqa: E731
        return {'segments': [
            {'index': 1, 'title': 'Opening', 'focus': 'Fatherhood', 'beats': beats(1), 'point_ids': ids[:2]},
            {'index': 2, 'title': 'Desktop', 'focus': 'Case work', 'beats': beats(2), 'point_ids': ids[2:4]},
            {'index': 3, 'title': 'Mobile', 'focus': 'Field', 'beats': beats(3), 'point_ids': ids[4:]}]}

    def locked_plan(self):
        current = self.plan()
        rev = self.client.post('/api/episodes/seg/segment-plan/new', json={'expected_revision': (current or {}).get('plan_revision')}).json()['plan_revision']
        saved = self.client.put('/api/episodes/seg/segment-plan', json={'plan': self.valid_plan_body(), 'expected_revision': rev})
        self.assertEqual(saved.status_code, 200, saved.text)
        locked = self.client.post('/api/episodes/seg/segment-plan/lock', json={'expected_revision': saved.json()['plan_revision']})
        self.assertEqual(locked.status_code, 200, locked.text)
        return locked.json()

    def generate(self, index, status=200):
        response = self.client.post(f'/api/episodes/segments/{index}/generate?job_id={self.job}')
        self.assertEqual(response.status_code, status, response.text)
        return response.json()

    def approve(self, index, draft_id, status=200):
        response = self.client.post(f'/api/episodes/seg/segments/{index}/drafts/{draft_id}/approve')
        self.assertEqual(response.status_code, status, response.text)
        return response.json()

    # tests -------------------------------------------------------------
    def test_plan_validation_and_locking(self):
        rev = self.client.post('/api/episodes/seg/segment-plan/new', json={}).json()['plan_revision']
        self.assertEqual(self.client.post('/api/episodes/seg/segment-plan/lock', json={'expected_revision': rev}).status_code, 409)
        body = self.valid_plan_body()
        body['segments'][0]['beats'][3] = 'Sign off and thank listeners'
        body['segments'][2]['beats'][0] = 'Welcome to the show'
        body['segments'][1]['point_ids'] = body['segments'][0]['point_ids']   # duplicates 2, leaves 2 unassigned
        body['segments'][1]['beats'][1] = body['segments'][2]['beats'][1]     # recurring topic: note only
        rev = self.client.put('/api/episodes/seg/segment-plan', json={'plan': body, 'expected_revision': rev}).json()['plan_revision']
        state = self.client.get('/api/episodes/seg/segments').json()
        issues = ' | '.join(state['plan_issues'])
        self.assertIn('only segment 3 closes', issues)
        self.assertIn('only segment 1 opens', issues)
        self.assertIn('is assigned to segments 1 and 2', issues)
        self.assertIn('not assigned', issues)
        self.assertNotIn('beat 2', issues)
        self.assertEqual(len(state['plan_notes']), 1)
        self.assertEqual(self.client.post('/api/episodes/seg/segment-plan/lock', json={'expected_revision': rev}).status_code, 409)
        rev = self.client.put('/api/episodes/seg/segment-plan', json={'plan': self.valid_plan_body(), 'expected_revision': rev}).json()['plan_revision']
        locked = self.client.post('/api/episodes/seg/segment-plan/lock', json={'expected_revision': rev}).json()
        self.assertTrue(locked['locked'])
        edit = self.client.put('/api/episodes/seg/segment-plan', json={'plan': self.valid_plan_body(), 'expected_revision': locked['plan_revision']})
        self.assertEqual(edit.status_code, 409)
        history = list((store.episode_dir('seg') / 'segments/plan_versions').glob('plan_*.json'))
        self.assertEqual(len(history), 4)  # new, two edits, lock

    def test_generation_order_and_plan_lock_required(self):
        self.client.post('/api/episodes/seg/segment-plan/new', json={})
        self.generate(1, status=422)                      # plan not locked
        self.locked_plan()
        self.generate(2, status=422)                      # segment 1 not approved
        draft = self.generate(1)
        self.generate(2, status=422)                      # draft alone is not enough
        self.approve(1, draft['draft_id'])
        self.assertEqual(self.generate(2)['segment_index'], 2)
        self.assertEqual(self.fake.prompts and len(self.fake.prompts), 6)  # 3 passes per 1,500-word segment

    def test_pass_prompts_carry_continuity_not_full_dialogue_and_only_segment_3_closes(self):
        self.locked_plan()
        drafts = {}
        for index in (1, 2, 3):
            drafts[index] = self.generate(index)
            self.approve(index, drafts[index]['draft_id'])
        seg1 = drafts[1]['script']
        segment2_prompts = self.fake.prompts[3:6]
        for line in seg1[:-5]:
            self.assertNotIn(line['text'], segment2_prompts[0])
        for line in seg1[-5:]:
            self.assertIn(line['text'], segment2_prompts[0])
        self.assertIn('Segment 1 beat 4', segment2_prompts[0])               # plan-derived covered list
        opening = [i for i, p in enumerate(self.fake.prompts) if 'This pass OPENS THE SHOW' in p]
        closing = [i for i, p in enumerate(self.fake.prompts) if 'This pass CLOSES THE SHOW' in p]
        self.assertEqual((opening, closing), ([0], [8]))
        self.assertTrue(all('An advertising break follows' in self.fake.prompts[i] for i in (2, 5)))

    def test_regenerating_one_segment_leaves_the_others_unchanged(self):
        self.locked_plan()
        first = self.generate(1)
        self.approve(1, first['draft_id'])
        second = self.generate(2)
        self.approve(2, second['draft_id'])
        folder = store.episode_dir('seg') / 'segments'
        before = {p: p.read_bytes() for p in folder.glob('seg[12]/*.json')}
        approvals = (folder / 'approvals.json').read_bytes()
        again = self.generate(2)
        self.assertNotEqual(again['draft_id'], second['draft_id'])
        self.assertEqual({p: p.read_bytes() for p in before}, before)
        self.assertEqual((folder / 'approvals.json').read_bytes(), approvals)
        states = {s['index']: s['status'] for s in self.client.get('/api/episodes/seg/segments').json()['segments']}
        self.assertEqual(states, {1: 'approved', 2: 'draft_ready', 3: 'planned'})

    def test_changing_an_approved_upstream_segment_marks_downstream_stale(self):
        self.locked_plan()
        first = self.generate(1)
        self.approve(1, first['draft_id'])
        self.approve(2, self.generate(2)['draft_id'])
        self.approve(1, self.generate(1)['draft_id'])
        segments = self.client.get('/api/episodes/seg/segments').json()['segments']
        self.assertEqual(segments[1]['status'], 'stale')
        self.assertIn('Segment 1 approval changed', segments[1]['stale_reasons'][0])
        self.assertFalse(segments[2]['can_generate'])

    def test_assembly_only_after_all_three_approved_and_explicit(self):
        self.locked_plan()
        for index in (1, 2):
            self.approve(index, self.generate(index)['draft_id'])
        self.assertEqual(self.client.get('/api/episodes/seg/segments/assembly-preview').status_code, 409)
        self.approve(3, self.generate(3)['draft_id'])
        self.assertEqual((store.episode_dir('seg') / 'script.json').read_bytes(), self.script_before)
        preview = self.client.get('/api/episodes/seg/segments/assembly-preview').json()
        self.assertEqual(preview['runtime']['advertising_seconds'], 210)
        self.assertEqual([p['position'] for p in preview['ad_layout']][1:3], ['after_segment_1', 'after_segment_2'])
        self.assertEqual((store.episode_dir('seg') / 'script.json').read_bytes(), self.script_before)
        wrong = self.client.post('/api/episodes/seg/segments/assemble', json={'preview_sha256': 'stale'})
        self.assertEqual(wrong.status_code, 409)
        done = self.client.post('/api/episodes/seg/segments/assemble', json={'preview_sha256': preview['preview_sha256']})
        self.assertEqual(done.status_code, 200, done.text)
        script = store.load_script('seg')['script']
        self.assertEqual(sorted({line['episode_segment'] for line in script}), [1, 2, 3])

    def test_ads_fall_between_segments_never_inside(self):
        lines = [{'speaker': 'phil' if i % 2 == 0 else 'jim', 'text': f'Line {i}.', 'episode_segment': 1 + i // 4}
                 for i in range(12)]
        assigned = {}
        for slot in ('pre_roll_1', 'mid_roll_1', 'mid_roll_2', 'mid_roll_3', 'mid_roll_4', 'post_roll_1'):
            assigned[slot] = store.save_ad('seg', {'script': [{'speaker': 'announcer_male', 'text': f'{slot} message.'}]})
        settings = store.load_ad_settings('seg')
        settings['slots'] = [{'slot_id': s, 'assigned_ad_id': assigned[s]['ad_id'] if s in assigned else None} for s in AD_SLOT_IDS]
        result = production._enforce_ads_and_structure(lines, list(assigned.values()), settings)
        order = [line.get('ad_slot_id') or f"s{line['episode_segment']}" for line in result]
        self.assertEqual(order, ['pre_roll_1'] + ['s1'] * 4 + ['mid_roll_1', 'mid_roll_2'] + ['s2'] * 4
                         + ['mid_roll_3', 'mid_roll_4'] + ['s3'] * 4 + ['post_roll_1'])


if __name__ == '__main__':
    unittest.main()
