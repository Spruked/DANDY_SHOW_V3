"""Exercise the context/import UI with intercepted API calls; no episode writes."""
import json
import os
from pathlib import Path
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright, expect


def main():
    sources, lines, calls, errors = [], [], [], []
    packet = None
    owner = {'authority': 'owner_direction', 'revision_id': '', 'per_source_notes': {}}
    revision = 0

    def api(route):
        nonlocal packet, lines, owner, revision
        request = route.request
        path = urlsplit(request.url).path
        calls.append((request.method, path))
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
        elif path.endswith('/episodes/fixture'):
            data = {'episode_id': 'fixture', 'title': 'Context workflow test', 'config': {'topic': 'Evidence', 'target_duration': 300}, 'script': lines}
        else:
            data = {}
        route.fulfill(json=data)

    output = Path(__file__).resolve().parents[1] / 'archive/testing/results/context-ui'
    output.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(channel='msedge', headless=True)
        page = browser.new_page(viewport={'width': 1366, 'height': 1000})
        page.on('pageerror', lambda e: errors.append(str(e)))
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
        for label in ['Direction', 'Sources', 'Brief', 'Show Bible', 'Source Facts', 'Format', 'Ad Slots', 'Build & Export', 'Short Copy']:
            page.get_by_role('tab', name=label, exact=True).click()
            expect(page.get_by_role('tabpanel')).to_have_count(1)
        page.get_by_role('tab', name='Direction', exact=True).focus()
        page.keyboard.press('ArrowRight')
        expect(page.get_by_role('tab', name='Sources', exact=True)).to_have_attribute('aria-selected', 'true')
        page.keyboard.press('Home')
        expect(page.get_by_role('tab', name='Direction', exact=True)).to_have_attribute('aria-selected', 'true')
        page.screenshot(path=str(output / 'context-958.png'), full_page=True)
        page.get_by_role('button', name='IMPORT FINISHED SCRIPT', exact=True).first.click()
        page.get_by_placeholder('PHIL: Opening line…\nJIM: Response…\nPHIL: Next point…').fill('PHIL: Welcome to the show.\nJIM: Let us examine the evidence.')
        page.get_by_role('button', name='IMPORT SCRIPT', exact=True).last.click()
        page.get_by_role('button', name='PRODUCTION', exact=True).click()
        page.get_by_role('button', name='EPISODES', exact=True).click()
        expect(page.get_by_text('Welcome to the show.', exact=True)).to_be_visible()
        page.screenshot(path=str(output / 'imported.png'), full_page=True)
        assert not any('generate-script' in path for _, path in calls)
        assert not errors, errors
        browser.close()
    print('PASS: dedicated Context workspace, nine section tabs, keyboard switching, retained edits, source analysis, priority, size planning, versioning and script import; no real API mutations')


if __name__ == '__main__':
    main()
