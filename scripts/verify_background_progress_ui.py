"""Browser fixtures for backend-started production; no real job writes."""
from pathlib import Path
from urllib.parse import urlsplit
from playwright.sync_api import expect, sync_playwright


def main():
    state = {"episode_id": "background", "job_id": "job_background", "status": "producing",
             "stage": "synthesizing", "progress": .25, "line_number": 50, "total_lines": 200, "engine": "qwen"}
    disconnected = False
    writes, errors = [], []
    def api(route):
        request = route.request
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            writes.append(request.url)
        path = urlsplit(request.url).path
        if path == "/api/episodes":
            result = {"episodes": [{"episode_id": "background", "title": "Backend-started episode", "status": state["status"]}]}
        elif path.endswith("/production-status"):
            if disconnected:
                route.abort()
                return
            result = state
        elif path.endswith("/system/diagnostics"):
            result = {"status": "ready", "selected_tts": "qwen", "checks": {}, "voice_registry": {}}
        elif path.endswith("/canonical-scripts"):
            result = {"versions": []}
        elif path.endswith("/assets"):
            result = {"assets": []}
        elif path.endswith("/context"):
            result = None
        elif path.endswith("/script"):
            result = {"script": []}
        elif path.endswith("/background"):
            result = {"job_id": "job_background", "config": {"title": "Backend-started episode"}}
        elif path.endswith("/jobs/job_background"):
            result = state
        else:
            result = {}
        route.fulfill(json=result)
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        page = browser.new_page(viewport={"width": 1366, "height": 903})
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.route("**/api/**", api)
        page.route_web_socket("**/ws/**", lambda ws: None)
        page.goto("http://localhost:8112/studio#system")
        bar = page.get_by_role("progressbar", name="Production progress for Backend-started episode", exact=True)
        expect(bar).to_have_attribute("value", "0.25")
        expect(page.get_by_text("Line 50/200", exact=True)).to_be_visible()
        page.get_by_role("button", name="PRODUCTION", exact=True).click()
        page.get_by_role("button", name="PREVIEW", exact=True).click()
        expect(bar).to_be_visible()
        state.update(progress=.45, line_number=90)
        expect(bar).to_have_attribute("value", "0.45")
        page.reload()
        expect(bar).to_have_attribute("value", "0.45")
        disconnected = True
        expect(page.get_by_text("Connection unavailable — showing the last saved progress.")).to_be_visible(timeout=8000)
        expect(bar).to_have_attribute("value", "0.45")
        disconnected = False
        state.update(stage="exporting", progress=.95)
        expect(bar).to_have_attribute("value", "0.95", timeout=8000)
        page.get_by_role("button", name="VIEW EPISODE", exact=True).click()
        expect(page.get_by_role("button", name="OPEN CONTEXT GENERATOR & EDITOR", exact=True)).to_be_visible()
        state.update(status="failed", stage="failed", error="Fixture export failed")
        expect(page.locator(".production-progress-tray").get_by_text("Fixture export failed", exact=True)).to_be_visible(timeout=8000)
        page.get_by_role("button", name="DISMISS", exact=True).click()
        expect(bar).to_have_count(0)
        assert not writes, writes
        assert not errors, errors
        output = Path(__file__).resolve().parents[1] / "archive/testing/results/background-progress"
        output.mkdir(parents=True, exist_ok=True)
        browser.close()
    print("PASS: backend-started job shown across tabs, reload, HTTP-only recovery, stale connection, exports and failure; no job mutations")


if __name__ == "__main__":
    main()
