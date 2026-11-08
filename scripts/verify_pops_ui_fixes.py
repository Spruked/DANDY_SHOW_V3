"""Read-only browser verification of POPS_UI_001; never approves or edits it."""
import json
import re
from pathlib import Path
from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]


def main():
    draft = json.loads((ROOT / "episodes/POPS_UI_001/production_editor/drafts/draft_v0001.json").read_text(encoding="utf-8"))
    review = draft["preview_review"]
    note = next(item["note"] for item in review["line_reviews"].values() if item.get("note"))
    output = ROOT / "archive/testing/results/pops-ui-fixes"
    output.mkdir(parents=True, exist_ok=True)
    errors, writes = [], []
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        page = browser.new_page(viewport={"width": 958, "height": 903})
        page.add_init_script("localStorage.setItem('dandyEpisodeId', 'POPS_UI_001')")
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on("request", lambda request: writes.append(request.url) if request.method not in {"GET", "HEAD", "OPTIONS"} else None)
        page.goto("http://localhost:8112/studio#production-editor")
        expect(page.get_by_text("2 PREVIEW SAVED", exact=True)).to_be_visible()
        expect(page.get_by_role("button", name="OPEN FROM PREVIEW", exact=True)).to_be_enabled()
        expect(page.get_by_role("button", name="APPROVE PRODUCTION VERSION", exact=True)).to_be_disabled()
        expect(page.get_by_text(note, exact=False).first).to_be_visible()
        expect(page.get_by_text(review["overall_notes"], exact=False).first).to_be_visible()
        state = page.locator("aside").last
        expect(state.get_by_text(re.compile(r"○\s+Approved"))).to_be_visible()
        page.screenshot(path=str(output / "editor-958.png"), full_page=True)
        page.set_viewport_size({"width": 1366, "height": 903})
        page.screenshot(path=str(output / "editor-1366.png"), full_page=True)
        page.set_viewport_size({"width": 958, "height": 903})
        page.get_by_role("button", name="PREVIEW", exact=True).click()
        send = page.get_by_role("button", name="SEND TO PRODUCTION EDITOR", exact=True)
        expect(send).to_be_enabled()
        box, sidebar = send.bounding_box(), page.locator(".preview-page > aside").last.bounding_box()
        assert box and sidebar
        assert box["y"] + box["height"] <= sidebar["y"] or box["x"] + box["width"] <= sidebar["x"], (box, sidebar)
        page.screenshot(path=str(output / "preview-958.png"), full_page=True)
        page.get_by_role("button", name="EPISODES", exact=True).click()
        expect(page.get_by_role("button", name="DOWNLOAD MP3", exact=True)).to_be_disabled()
        assert not errors, errors
        assert not writes, writes
        browser.close()
    print("PASS: saved handoff, retained notes, unapproved state, narrow layout and no-audio download; zero episode writes")


if __name__ == "__main__":
    main()
