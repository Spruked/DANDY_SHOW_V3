"""Read-only browser fixture check of restored branch screens."""
import json
import os
from pathlib import Path
from urllib.parse import urlsplit
from playwright.sync_api import expect, sync_playwright


def main():
    errors = []
    lines = [{"speaker": "phil", "text": "Preserve the work before integrating new features.", "canonical_line_id": "line_1"},
             {"speaker": "jim", "text": "Then test the complete workflow with real evidence.", "canonical_line_id": "line_2"}]
    canonical = {"version_id": "canonical_v0001", "canonical_hash": "a" * 64, "script": lines}
    def api(route):
        path = urlsplit(route.request.url).path
        if path == "/api/episodes":
            data = {"episodes": [{"episode_id": "fixture", "title": "Integration review", "status": "script_ready"}]}
        elif path.endswith("/canonical-scripts"):
            data = {"active_version_id": canonical["version_id"], "versions": [{"version_id": canonical["version_id"], "word_count": 18}]}
        elif path.endswith("/canonical-scripts/canonical_v0001"):
            data = canonical
        elif path.endswith("/preview"):
            data = {"saved": True, "review_id": "preview_v0001", "canonical_version_id": canonical["version_id"],
                    "line_reviews": {}, "section_notes": {}, "overall_notes": "Ready for the production editor"}
        elif path.endswith("/script"):
            data = {"script": lines}
        elif path.endswith("/assets") or path == "/api/asset-library":
            data = {"assets": []}
        elif path.endswith("/ads"):
            data = {"ads": []}
        elif path == "/api/writer-status":
            data = {"bridge_reachable": True, "active_writer": "llamacpp"}
        elif path.endswith("/tts-engine"):
            data = {"selected_engine": "qwen", "allowed_engines": ["qwen"]}
        elif path.endswith("/system/diagnostics"):
            data = {"status": "ready", "checked_at": "2026-10-26T23:00:00Z", "checks": {}, "voice_registry": {}}
        else:
            data = {}
        route.fulfill(json=data)
    output = Path(__file__).resolve().parents[1] / "archive/testing/results/branch-ui"
    output.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        page = browser.new_page(viewport={"width": 1600, "height": 1000})
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.route("**/api/**", api)
        page.route_web_socket("**/ws/**", lambda ws: None)
        page.goto(os.getenv("DANDY_UI_URL", "http://127.0.0.1:15173"))
        for name in ["EPISODES", "PREVIEW", "PRODUCTION EDITOR", "ASSEMBLY", "ADS", "SOCIAL", "SYSTEM", "STUDIO"]:
            page.get_by_role("button", name=name, exact=True).click()
            expect(page.locator(".app-shell")).to_be_visible()
            page.screenshot(path=str(output / (name.lower().replace(" ", "-") + ".png")), full_page=True)
            assert not errors, (name, errors)
        browser.close()
    print(json.dumps({"status": "passed", "screens": 8, "browser_errors": errors, "screenshots": str(output)}))


if __name__ == "__main__":
    main()
