"""Verify clean episode inventory and compact navigation without creating data."""
import sys
from pathlib import Path
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright, expect


def main():
    live = '--live' in sys.argv
    errors, writes = [], []
    output = Path(__file__).resolve().parents[1] / 'archive/testing/results/context-ui'
    output.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(channel='msedge', headless=True)
        page = browser.new_page(viewport={'width': 1366, 'height': 903})
        page.add_init_script("localStorage.setItem('dandyEpisodeId', 'eps-003'); localStorage.setItem('dandyActiveTab', 'context')")
        page.on('pageerror', lambda error: errors.append(str(error)))
        def route_api(route):
            request = route.request
            if request.method not in {'GET', 'HEAD', 'OPTIONS'}:
                writes.append(request.url)
                route.abort()
            elif live:
                route.continue_()
            else:
                path = urlsplit(request.url).path
                route.fulfill(json={'episodes': []} if path == '/api/episodes' else {})
        page.route('**/api/**', route_api)
        page.goto('http://localhost:8112/studio#context')
        expect(page.get_by_role('heading', name='Context Generator & Editor', exact=True)).to_be_visible()
        expect(page.get_by_role('button', name='NEW EPISODE', exact=True)).to_be_visible()
        page.get_by_role('button', name='NEW EPISODE', exact=True).click()
        expect(page.get_by_text('Create Episode', exact=True)).to_be_visible()
        expect(page.get_by_role('textbox', name='Episode Title', exact=True)).to_be_visible()
        expect(page.get_by_role('textbox', name='Main Topic', exact=True)).to_be_visible()
        expect(page.get_by_role('textbox', name='Episode Brief', exact=True)).to_be_visible()
        expect(page.get_by_role('slider', name='Target episode duration', exact=True)).to_be_visible()
        expect(page.get_by_text('Create Segment', exact=True)).to_have_count(0)
        expect(page.get_by_role('textbox', name='Episode ID', exact=True)).to_have_count(0)
        expect(page.get_by_text('INTERNAL GENERATION PLAN', exact=False)).to_have_count(0)
        page.get_by_role('button', name='CANCEL', exact=True).click()
        expect(page.locator('.ep-row')).to_have_count(0)
        expect(page.get_by_role('navigation', name='Main workspaces').get_by_role('button')).to_have_count(5)
        page.wait_for_function("localStorage.getItem('dandyEpisodeId') === null")
        assert page.locator('.top-nav').bounding_box()['height'] < 140
        page.get_by_role('button', name='PRODUCTION', exact=True).click()
        expect(page.get_by_role('navigation', name='PRODUCTION sections').get_by_role('button')).to_have_count(4)
        expect(page.get_by_role('button', name='DELETE EPISODE', exact=True)).to_have_count(0)
        expect(page.get_by_role('button', name='DOWNLOAD MP3', exact=True)).to_have_count(0)
        page.get_by_role('button', name='CONTEXT GENERATOR & EDITOR', exact=True).click()
        page.set_viewport_size({'width': 958, 'height': 903})
        expect(page.get_by_role('heading', name='Context Generator & Editor', exact=True)).to_be_visible()
        page.screenshot(path=str(output / ('empty-live.png' if live else 'empty-fixture.png')), full_page=True)
        assert not writes, writes
        assert not errors, errors
        browser.close()
    print('PASS: empty episode list, stale selection cleared, five compact workspaces, grouped production, no old audio controls; no data mutations')


if __name__ == '__main__':
    main()
