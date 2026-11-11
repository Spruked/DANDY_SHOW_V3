"""Exercise the context/import UI with intercepted API calls; no episode writes."""
import json
import os
from pathlib import Path
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright, expect

POINTS = ['Explain the fee', 'Show the timeline', 'Close honestly']
SLOTS = {'before_segment_1': ['pre_roll_1', 'pre_roll_2'], 'after_segment_1': ['mid_roll_1', 'mid_roll_2'],
         'after_segment_2': ['mid_roll_3', 'mid_roll_4'], 'after_segment_3': ['post_roll_1']}


class SegmentFixture:
    """Stateful stand-in for the segment API; mirrors the backend's ordering rules."""

    def __init__(self):
        self.plan, self.drafts, self.approved, self.assembled = None, {1: [], 2: [], 3: []}, {}, None

    def blocker(self, n):
        if not (self.plan and self.plan['locked']):
            return 'Lock the segment plan first'
        if n > 1 and n - 1 not in self.approved:
            return f'Approve segment {n - 1} first'
        return None

    def state(self):
        segments = []
        for n in (1, 2, 3):
            latest = self.drafts[n][-1] if self.drafts[n] else None
            approved = self.approved.get(n)
            status = ('approved' if approved and latest and approved['draft_id'] == latest['draft_id']
                      else 'draft_ready' if latest else 'planned')
            segments.append({'index': n, 'plan': {'target_words': 1500}, 'status': status, 'latest_draft': latest,
                             'draft_count': len(self.drafts[n]), 'approved': approved, 'stale_reasons': [],
                             'can_generate': self.blocker(n) is None, 'generate_blocked_reason': self.blocker(n), 'progress': None})
        layout = [{'position': k, 'slots': [{'slot_id': s, 'status': 'reserved', 'assigned_ad_id': None, 'duration_seconds': 0} for s in v]}
                  for k, v in SLOTS.items()]
        runtime = {'runtime_seconds': 2039.4, 'talk_seconds': 1800, 'advertising_seconds': 210, 'theme_seconds': 29.4,
                   'target_words': 4500, 'segments': [{'talk_minutes': 10}] * 3} if self.plan else None
        return {'plan': self.plan, 'segments': segments, 'settings': {'min_talk_minutes': 10, 'max_talk_minutes': 12},
                'ad_layout': layout, 'runtime': runtime, 'plan_issues': [] if self.plan else ['Create a segment plan'],
                'plan_notes': [], 'plan_stale': False, 'can_assemble': all(s['status'] == 'approved' for s in segments)}

    def handle(self, method, path, body):
        if path.endswith('/segment-plan/new'):
            self.plan = {'plan_revision': 'plan_1', 'locked': False, 'context_version_id': 'context_fixture_v2', 'proposed_by': 'owner',
                         'points': [{'id': f'p1_{i}', 'text': t} for i, t in enumerate(POINTS, 1)],
                         'episode_requirements': [{'id': 'r2', 'text': 'This episode airs at launch.', 'role': 'episode_requirement', 'primary_segment': None}],
                         'segments': [{'index': n, 'title': '', 'focus': '', 'beats': [], 'point_ids': [], 'talk_minutes': 10} for n in (1, 2, 3)]}
            return self.plan
        if path.endswith('/segment-plan') and method == 'PUT':
            assert body['expected_revision'] == self.plan['plan_revision'] and not self.plan['locked']
            number = int(self.plan['plan_revision'].split('_')[1]) + 1
            self.plan = {**self.plan, **body['plan'], 'plan_revision': f'plan_{number}'}
            return self.plan
        if path.endswith('/segment-plan/lock'):
            assert body['expected_revision'] == self.plan['plan_revision']
            assigned = sorted(i for s in self.plan['segments'] for i in s['point_ids'])
            assert assigned == ['p1_1', 'p1_2', 'p1_3'], assigned
            assert all(len(s['beats']) == 4 and s['title'] for s in self.plan['segments'])
            assert self.plan['episode_requirements'][0]['primary_segment'] == 1
            self.plan = {**self.plan, 'locked': True, 'plan_revision': self.plan['plan_revision'] + '_locked'}
            return self.plan
        if path.endswith('/generate'):
            n = int(path.split('/')[-2])
            assert self.blocker(n) is None, self.blocker(n)
            script = [{'speaker': 'phil' if i % 2 == 0 else 'jim', 'text': f'Segment {n} line {i + 1}.'} for i in range(4)]
            warnings = [{'id': 'duplicate_exchange_3', 'line': 3, 'end_line': 4, 'informational': True,
                         'detail': 'Lines 3-4 repeat segment 1 lines 1-2 word for word. Owner decides whether this is intentional.'}] if n == 2 else []
            draft = {'draft_id': f'segdraft_{n}_{len(self.drafts[n]) + 1}', 'segment_index': n, 'word_count': 1500, 'target_words': 1500,
                     'script': script, 'passes': [{}, {}, {}], 'review_warnings': warnings}
            self.drafts[n].append(draft)
            return draft
        if path.endswith('/approve'):
            n, draft_id = int(path.split('/')[-4]), path.split('/')[-2]
            assert n == 1 or n - 1 in self.approved
            self.approved[n] = {'draft_id': draft_id}
            return self.approved[n]
        if path.endswith('/assembly-preview'):
            assert self.state()['can_assemble']
            script = [{**line, 'episode_segment': n} for n in (1, 2, 3) for line in self.drafts[n][-1]['script']]
            for number, line in enumerate(script, 1):
                line['line_number'] = number
            return {'segments': [{'segment_index': n, 'word_count': 1500, 'turns': 4} for n in (1, 2, 3)], 'script': script,
                    'runtime': self.state()['runtime'], 'review_warnings': [], 'preview_sha256': 'preview_fixture'}
        if path.endswith('/assemble'):
            assert body == {'preview_sha256': 'preview_fixture'}
            self.assembled = True
            return {'canonical_version_id': 'canonical_v0002'}
        return self.state()


def main():
    sources, lines, calls, errors = [], [], [], []
    packet = None
    writer_draft = None
    owner = {'authority': 'owner_direction', 'revision_id': '', 'per_source_notes': {}}
    revision = 0
    segments = SegmentFixture()

    def api(route):
        nonlocal packet, lines, owner, revision, writer_draft
        request = route.request
        path = urlsplit(request.url).path
        calls.append((request.method, path))
        if '/segment' in path:
            route.fulfill(json=segments.handle(request.method, path, request.post_data_json if request.method != 'GET' else None))
            return
        if path == '/api/episodes':
            data = {'episodes': [{'episode_id': 'fixture', 'title': 'Context workflow test', 'status': 'draft_created', 'config': {'topic': 'Evidence', 'target_duration': 300}}]}
        elif path.endswith('/context/sources/text'):
            body = request.post_data_json
            sources.append({'asset_id': 'asset_fixture', 'original_name': body['title'] + '.txt', 'label': body['title'], 'role': 'source'})
            data = sources[-1]
        elif path.endswith('/context/reference'):
            data = {'show_bible': [{'speaker': 'phil', 'source_file': 'phil.py', 'location': 'lines 1-2', 'character': {'primary_traits': ['warm']}}],
                    'format_contract': {'spoken_script': 'One PHIL: or JIM: turn per line.'}, 'ad_slots': {'settings': {}, 'ads': []}}
        elif path.endswith('/context/inspect'):
            assert request.post_data_json['source_ids'] == ['asset_fixture']
            data = {'sources': [{'source_id': 'asset_fixture', 'character_count': 25, 'estimated_tokens': 9, 'record_count': 1,
                                'records': [{'record_id': 'record_fixture', 'location': 'lines 1-1', 'text_preview': 'Original source evidence.'}]}], 'warnings': []}
        elif path.endswith('/context/direction'):
            if request.method == 'PUT':
                body = request.post_data_json
                assert body['expected_direction_revision'] == owner['revision_id']
                revision += 1
                owner = {**body['owner_direction'], 'authority': 'owner_direction', 'revision_id': f'direction_{revision}'}
                if packet:
                    packet = {**packet, 'version_id': 'context_fixture_v2', 'owner_direction': owner}
                data = {'owner_direction': owner, 'package': packet, 'pack_regenerated': bool(packet)}
            else:
                data = owner
        elif path.endswith('/context'):
            if request.method == 'POST':
                body = request.post_data_json
                assert body['source_ids'] == ['asset_fixture']
                assert body['owner_direction']['per_source_notes']['asset_fixture'] == 'Use only the pricing section.'
                revision += 1
                owner = {**body['owner_direction'], 'authority': 'owner_direction', 'revision_id': f'direction_{revision}'}
                assert body['curation']['priority_source_ids'] == ['asset_fixture']
                packet = {'version_id': 'context_fixture', 'sources': [{'source_id': s['asset_id'], **s, 'sections': [{'location': 'lines 1-1', 'text': 'Original source evidence.'}]} for s in sources],
                          'curation': body['curation'],
                          'sizing': {'estimated_input_tokens': 1000, 'planning_margin_tokens': 406, 'input_budget_tokens': 57344, 'fits_estimate': True, 'json_estimated_input_tokens': 2100},
                          'warnings': [], 'brief': body['brief'], 'owner_direction': owner,
                          'markdown': '# Owner direction\nOriginal source evidence.'}
            data = packet
        elif path.endswith('/assets') or path == '/api/asset-library':
            data = {'assets': sources}
        elif path.endswith('/replace-script'):
            assert 'PHIL:' in request.post_data_json['text']
            lines = [{'speaker': 'phil', 'text': 'Welcome to the show.', 'canonical_line_id': 'line_1'}, {'speaker': 'jim', 'text': 'Let us examine the evidence.', 'canonical_line_id': 'line_2'}]
            data = {'script': lines, 'line_count': 2}
        elif path.endswith('/script'):
            data = {'script': lines}
        elif path.endswith('/canonical-scripts'):
            data = {'active_version_id': 'canonical_v0001' if lines else '', 'versions': [{'version_id': 'canonical_v0001', 'word_count': 12}] if lines else []}
        elif path.endswith('/ads'):
            data = {'ads': []}
        elif path.endswith('/writer-status'):
            data = {'bridge_reachable': False, 'active_writer': 'offline'}
        elif path.endswith('/writer-draft'):
            data = writer_draft
        elif path.endswith('/episodes/jobs/job_fixture'):
            data = {'status': 'draft_ready' if writer_draft else 'idle'}
        elif path == '/api/episodes/generate-script':
            assert request.post_data_json == {'context_version_id': packet['version_id'], 'sample': True}
            sample = [{'speaker': 'phil' if i % 2 == 0 else 'jim', 'text': f'Approved sample dialogue number {i}.',
                       'emotion': 'neutral', 'pause_after': .4} for i in range(8)]
            writer_draft = {'draft_id': 'draft_ui_fixture', 'sample': True, 'status': 'sample',
                            'context_version_id': packet['version_id'], 'word_count': 40, 'script': sample, 'review_warnings': []}
            data = writer_draft
        elif path.endswith('/episodes/fixture'):
            data = {'episode_id': 'fixture', 'job_id': 'job_fixture', 'title': 'Context workflow test', 'config': {'topic': 'Evidence', 'target_duration': 300}, 'script': lines}
        else:
            data = {}
        route.fulfill(json=data)

    output = Path(__file__).resolve().parents[1] / 'archive/testing/results/context-ui'
    output.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(channel='msedge', headless=True)
        page = browser.new_page(viewport={'width': 1366, 'height': 1000})
        page.on('pageerror', lambda e: errors.append(str(e)))
        page.on('dialog', lambda dialog: dialog.accept())
        page.route('**/api/**', api)
        page.route_web_socket('**/ws/**', lambda ws: None)
        page.goto(os.getenv('DANDY_UI_URL', 'http://localhost:8112/studio'))
        page.get_by_role('button', name='CONTEXT GENERATOR & EDITOR', exact=True).click()
        page.get_by_text('Context workflow test', exact=True).first.click()
        expect(page.get_by_role('heading', name='Context Generator & Editor')).to_be_visible()
        page.get_by_role('textbox', name='Episode direction', exact=True).fill('Explain the costs honestly.')
        page.get_by_role('textbox', name='Angle and tone', exact=True).fill('Teaching with dry humor')
        page.get_by_role('textbox', name='Must include', exact=True).fill('Explain the fee.')
        page.get_by_role('textbox', name='Must avoid', exact=True).fill('Unsupported claims')
        page.get_by_role('textbox', name='Segment notes', exact=True).fill('Closing: ask what remains unknown.')
        page.get_by_role('button', name='SAVE OWNER DIRECTION', exact=True).click()
        expect(page.get_by_text('Owner direction saved.', exact=True)).to_be_visible()
        page.get_by_role('tab', name='Sources', exact=True).click()
        page.get_by_text('Paste a source document', exact=True).click()
        page.get_by_role('textbox', name='Source title', exact=True).fill('Original source')
        page.get_by_role('textbox', name='Source document text', exact=True).fill('Original source evidence.')
        page.get_by_role('button', name='ADD SOURCE', exact=True).click()
        expect(page.get_by_role('checkbox', name='Original source', exact=True)).to_be_checked()
        page.get_by_role('button', name='ANALYZE SELECTED SOURCES', exact=True).click()
        expect(page.get_by_text('1 records · approximately 9 source tokens', exact=True)).to_be_visible()
        page.get_by_role('checkbox', name='Priority source Original source', exact=True).check()
        page.get_by_role('textbox', name='Owner note for Original source', exact=True).fill('Use only the pricing section.')
        page.get_by_role('tab', name='Build & Export', exact=True).click()
        page.get_by_role('textbox', name='External model name', exact=True).fill('My external writer')
        page.get_by_role('spinbutton', name='Context window (tokens)', exact=True).fill('65536')
        page.get_by_role('spinbutton', name='Reserve for script output (tokens)', exact=True).fill('8192')
        page.get_by_role('tab', name='Brief', exact=True).click()
        page.get_by_role('textbox', name='Episode brief:').fill('Explain the evidence without invented claims.')
        page.get_by_role('tab', name='Build & Export', exact=True).click()
        page.get_by_role('button', name='BUILD CONTEXT PACKAGE', exact=True).click()
        expect(page.get_by_text('Saved context_fixture', exact=False)).to_be_visible()
        with page.expect_download() as info:
            page.get_by_role('button', name='DOWNLOAD CONTEXT MD').click()
        assert info.value.suggested_filename == 'fixture-context.md'
        page.get_by_role('spinbutton', name='Context window (tokens)', exact=True).fill('32768')
        expect(page.get_by_role('button', name='DOWNLOAD CONTEXT MD')).to_be_disabled()
        page.get_by_role('spinbutton', name='Context window (tokens)', exact=True).fill('65536')
        expect(page.get_by_role('button', name='DOWNLOAD CONTEXT MD')).to_be_enabled()
        page.get_by_role('tab', name='Direction', exact=True).click()
        page.get_by_role('textbox', name='Must avoid', exact=True).fill('Do not claim this is free.')
        page.get_by_role('tab', name='Build & Export', exact=True).click()
        expect(page.get_by_role('button', name='DOWNLOAD CONTEXT MD')).to_be_disabled()
        page.get_by_role('tab', name='Direction', exact=True).click()
        page.get_by_role('button', name='SAVE OWNER DIRECTION', exact=True).click()
        page.get_by_role('tab', name='Build & Export', exact=True).click()
        expect(page.get_by_text('Saved context_fixture_v2', exact=False)).to_be_visible()
        expect(page.get_by_role('button', name='DOWNLOAD CONTEXT MD')).to_be_enabled()
        page.reload()
        expect(page.get_by_role('textbox', name='Episode direction', exact=True)).to_have_value('Explain the costs honestly.')
        expect(page.get_by_role('textbox', name='Must avoid', exact=True)).to_have_value('Do not claim this is free.')
        page.get_by_role('tab', name='Sources', exact=True).click()
        expect(page.get_by_role('textbox', name='Owner note for Original source', exact=True)).to_have_value('Use only the pricing section.')
        expect(page.get_by_role('checkbox', name='Priority source Original source', exact=True)).to_be_checked()
        page.get_by_role('tab', name='Build & Export', exact=True).click()
        expect(page.get_by_role('spinbutton', name='Context window (tokens)', exact=True)).to_have_value('65536')
        page.set_viewport_size({'width': 958, 'height': 903})
        for label in ['Direction', 'Sources', 'Brief', 'Show Bible', 'Source Facts', 'Format', 'Ad Slots', 'Build & Export', 'Segments', 'Short Copy']:
            page.get_by_role('tab', name=label, exact=True).click()
            expect(page.get_by_role('tabpanel')).to_have_count(1)
        page.get_by_role('tab', name='Direction', exact=True).focus()
        page.keyboard.press('ArrowRight')
        expect(page.get_by_role('tab', name='Sources', exact=True)).to_have_attribute('aria-selected', 'true')
        page.keyboard.press('Home')
        expect(page.get_by_role('tab', name='Direction', exact=True)).to_have_attribute('aria-selected', 'true')
        page.get_by_role('tab', name='Build & Export', exact=True).click()
        page.get_by_role('button', name='TEST WRITER · 8 TURNS', exact=True).click()
        expect(page.get_by_role('heading', name='Diagnostic sample · 40 words')).to_be_visible()
        expect(page.get_by_role('button', name='ACCEPT DRAFT TO PREVIEW', exact=True)).to_have_count(0)
        assert lines == [], 'Sample must not activate an episode script'
        page.reload()
        page.get_by_role('tab', name='Build & Export', exact=True).click()
        expect(page.get_by_role('heading', name='Diagnostic sample · 40 words')).to_be_visible()
        page.screenshot(path=str(output / 'context-958.png'), full_page=True)
        # Segments view: plan, lock, ordered generation, approval, informational review, explicit assembly.
        page.set_viewport_size({'width': 1366, 'height': 1000})
        page.get_by_role('button', name='WRITE EPISODE IN SEGMENTS →', exact=True).click()
        expect(page.get_by_text('No segment plan yet.', exact=True)).to_be_visible()
        page.get_by_role('button', name='NEW EMPTY PLAN', exact=True).click()
        order = page.get_by_label('Running order')
        expect(order).to_have_text('THEMEPRE 1PRE 2SEGMENT 1MID 1MID 2SEGMENT 2MID 3MID 4SEGMENT 3POSTTHEME')
        expect(page.get_by_text('Runtime 33:59.4', exact=False)).to_be_visible()
        for n in (1, 2, 3):
            card = page.get_by_role('article', name=f'Segment {n}', exact=True)
            expect(card.get_by_text('Lock the segment plan first', exact=True)).to_be_visible()
            card.get_by_role('textbox', name='Title', exact=True).fill(f'Part {n}')
            card.get_by_role('textbox', name='Topic focus', exact=True).fill(f'Focus {n}')
            for b in range(1, 5):
                card.get_by_role('button', name='+ BEAT', exact=True).click()
                card.get_by_role('textbox', name=f'Segment {n} beat {b}', exact=True).fill(f'Beat {n}.{b}')
            card.get_by_role('checkbox', name=POINTS[n - 1], exact=False).check()
        page.get_by_role('combobox', name='Primary segment for requirement 1', exact=True).select_option('1')
        page.get_by_role('button', name='LOCK PLAN', exact=True).click()
        expect(page.get_by_text('Plan locked. Segment 1 can be written.', exact=True)).to_be_visible()
        cards = [page.get_by_role('article', name=f'Segment {n}', exact=True) for n in (1, 2, 3)]
        expect(cards[1].get_by_role('button', name='GENERATE', exact=True)).to_be_disabled()
        cards[0].get_by_role('button', name='GENERATE', exact=True).click()
        expect(cards[0].get_by_text('DRAFT READY', exact=True)).to_be_visible()
        expect(cards[1].get_by_text('Approve segment 1 first', exact=True)).to_be_visible()
        cards[0].get_by_role('button', name='APPROVE', exact=True).click()
        expect(cards[0].get_by_role('button', name='APPROVED', exact=True)).to_be_disabled()
        for n in (2, 3):
            cards[n - 1].get_by_role('button', name='GENERATE', exact=True).click()
            expect(cards[n - 1].get_by_text('DRAFT READY', exact=True)).to_be_visible()
            if n == 2:
                expect(cards[1].get_by_text('Review notes (1, informational)', exact=True)).to_be_visible()
                cards[1].get_by_role('button', name='REGENERATE', exact=True).click()
                expect(cards[1].get_by_text('Draft 2 ·', exact=False)).to_be_visible()
                expect(cards[0].get_by_text('Draft 1 ·', exact=False)).to_be_visible()
            cards[n - 1].get_by_role('button', name='APPROVE', exact=True).click()
            expect(cards[n - 1].get_by_role('button', name='APPROVED', exact=True)).to_be_disabled()
        assert segments.assembled is None
        page.get_by_role('button', name='ASSEMBLY PREVIEW', exact=True).click()
        expect(page.get_by_role('heading', name='Assembly preview · nothing saved yet')).to_be_visible()
        assert segments.assembled is None, 'Preview must not assemble'
        page.screenshot(path=str(output / 'segments.png'), full_page=True)
        page.get_by_role('button', name='ASSEMBLE EPISODE', exact=True).click()
        # Like an accepted draft, the assembled script opens in Preview for review.
        expect(page.get_by_role('button', name='SAVE PREVIEW')).to_be_visible()
        assert segments.assembled is True
        page.get_by_role('button', name='CONTEXT GENERATOR & EDITOR', exact=True).click()
        page.get_by_text('Context workflow test', exact=True).first.click()
        expect(page.get_by_role('heading', name='Context Generator & Editor')).to_be_visible()
        page.set_viewport_size({'width': 958, 'height': 903})
        page.get_by_role('tab', name='Build & Export', exact=True).click()
        page.get_by_role('button', name='IMPORT FINISHED SCRIPT', exact=True).first.click()
        page.get_by_placeholder('PHIL: Opening line…\nJIM: Response…\nPHIL: Next point…').fill('PHIL: Welcome to the show.\nJIM: Let us examine the evidence.')
        page.get_by_role('button', name='IMPORT SCRIPT', exact=True).last.click()
        page.get_by_role('button', name='PRODUCTION', exact=True).click()
        page.get_by_role('button', name='EPISODES', exact=True).click()
        expect(page.get_by_text('Welcome to the show.', exact=True)).to_be_visible()
        page.screenshot(path=str(output / 'imported.png'), full_page=True)
        assert sum('generate-script' in path for _, path in calls) == 1
        assert not errors, errors
        browser.close()
    print('PASS: Context workspace, retained edits, source analysis, versioning, recovered diagnostic sample, three-segment plan/generate/approve/assemble and script import. All API calls intercepted; no provider calls or real episode mutations.')


if __name__ == '__main__':
    main()
