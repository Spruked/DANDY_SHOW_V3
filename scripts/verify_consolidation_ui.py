"""Browser contract check with intercepted API/WS fixtures; writes no episode data.

Requires playwright in the local environment and installed Microsoft Edge.
Run with Vite running: .venv\Scripts\python.exe scripts/verify_consolidation_ui.py
"""
import json
import os
from urllib.parse import urlsplit

from playwright.sync_api import expect, sync_playwright


def main():
    script = [{"speaker": "phil", "text": "A specific point worth discussing", "line_number": 1},
              {"speaker": "jim", "text": "Show me the practical evidence", "line_number": 2}]
    edits, sockets, errors, created_jobs = [], [], [], []
    status = {"status": "new", "progress": 0}

    def api(route):
        nonlocal script, status
        path = urlsplit(route.request.url).path
        if path == "/api/health":
            result = {"status": "healthy"}
        elif path == "/api/writer-status":
            result = {"bridge_reachable": True, "active_writer": "llm_bridge"}
        elif path == "/api/episodes":
            result = {"episodes": [{"episode_id": "test", "title": "UI contract fixture"}]}
        elif path.endswith("/production-status"):
            result = status
        elif path.endswith("/script"):
            result = {"script": script}
        elif path.endswith("/assets"):
            result = {"assets": []}
        elif path == "/api/episodes/edit-script":
            body = route.request.post_data_json
            edits.append(body)
            if body["edit_type"] == "regenerate_section":
                script[0] = {**script[0], "text": "Fresh rewritten dialogue for this section"}
            elif body["edit_type"] == "adjust_tone":
                script = [{**line, "pause_after": 0.2} for line in script]
            result = {"status": "script_ready", "updated_script": script}
        elif path == "/api/episodes/create":
            created_jobs.append(route.request.post_data_json)
            result = {"job_id": "job_test", "episode_id": "test"}
        elif path == "/api/episodes/test":
            result = {"job_id": "job_test", "config": {"topic": "Fixture", "title": "UI contract fixture"}}
        elif path == "/api/episodes/produce":
            status = {"type": "production_progress", "status": "producing", "stage": "synthesizing",
                      "progress": 0.5, "line_number": 1, "total_lines": 2,
                      "engine_stats": {"kokoro": 1}, "engine_line_stats": {"kokoro": 1}}
            result = {"status": "queued"}
        else:
            result = {}  # Optional OBS/mixer panels mount before selecting Episodes.
        route.fulfill(json=result)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="msedge", headless=True)
        page = browser.new_page(viewport={"width": 1600, "height": 1000})
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.route("**/api/**", api)
        page.route_web_socket("**/ws/**", lambda ws: sockets.append(ws))
        page.goto(os.getenv("DANDY_UI_URL", "http://127.0.0.1:5173"))
        page.get_by_role("button", name="EPISODES", exact=True).click()
        expect(page.get_by_text("A specific point worth discussing", exact=True)).to_be_visible()
        page.get_by_role("button", name="REGENERATE SECTION", exact=True).click()
        page.get_by_label("First line", exact=True).fill("1")
        page.get_by_label("Last line", exact=True).fill("1")
        page.locator(".modal-box").get_by_role("button", name="REGENERATE", exact=True).click()
        expect(page.get_by_text("Fresh rewritten dialogue for this section", exact=True)).to_be_visible()
        assert edits[-1]["section_start"] == 0 and edits[-1]["section_end"] == 1
        page.get_by_role("button", name="TONE / PACING", exact=True).click()
        page.get_by_label("Tone adjustment").select_option("faster_paced")
        page.get_by_role("button", name="APPLY", exact=True).click()
        expect(page.locator(".modal-box")).to_have_count(0)
        assert edits[-1]["tone_adjustment"] == "faster_paced"
        assert edits[-1]["section_start"] == 0 and edits[-1]["section_end"] == 2
        page.get_by_role("button", name="PRODUCE", exact=True).click()
        expect(page.get_by_role("button", name="PRODUCING…", exact=True)).to_be_disabled()
        assert not created_jobs, "Production must reuse the persisted job without resetting episode state"
        for ws in sockets:
            ws.send(json.dumps(status))
        expect(page.get_by_text("synthesizing · 50%", exact=True)).to_be_visible()
        expect(page.get_by_text("TTS chunks: kokoro: 1", exact=False)).to_be_visible()
        status = {"type": "production_error", "status": "failed", "stage": "failed", "progress": 0.5, "error": "Fixture TTS failure"}
        for ws in sockets:
            ws.send(json.dumps(status))
        expect(page.get_by_text("· Fixture TTS failure", exact=True)).to_be_visible()
        expect(page.get_by_role("button", name="PRODUCE", exact=True)).to_be_enabled()
        page.reload()
        page.get_by_role("button", name="EPISODES", exact=True).click()
        expect(page.get_by_text("· Fixture TTS failure", exact=True)).to_be_visible()
        assert not errors, errors
        browser.close()
    print("PASS: regeneration range, tone controls, production progress, engine statistics, failure recovery; no episode writes")


if __name__ == "__main__":
    main()
