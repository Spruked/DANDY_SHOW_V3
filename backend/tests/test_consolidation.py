"""Contract tests use temporary storage and fake TTS/LLM; never touch episodes."""
import asyncio
from copy import deepcopy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from app.api import production
from app.services.production.worker import HardenedPodcastWorker


class ProductionTests(unittest.TestCase):
    def test_websocket_and_status_route_contract(self):
        from fastapi.testclient import TestClient
        from app.main import app
        from app.websockets.manager import manager
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(production, "episode_dir", return_value=Path(directory)), \
             TestClient(app) as client:
            self.assertEqual(client.get("/api/episodes/test/production-status").json()["status"], "new")
            production.save_json(Path(directory) / "status.json", {"status": "producing", "progress": 0.5})
            self.assertEqual(client.get("/api/episodes/test/production-status").json()["progress"], 0.5)
            with client.websocket_connect("/ws/test") as ws:
                self.assertEqual(ws.receive_json()["type"], "connected")
                client.portal.call(manager.broadcast, "test", {"type": "production_progress", "progress": 0.5})
                self.assertEqual(ws.receive_json()["progress"], 0.5)
                ws.send_text("still compatible")
                self.assertEqual(ws.receive_json()["type"], "echo")

    def run_job(self, fail=False, export_fail=False):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            def episode_dir(episode_id):
                path = root / "episodes" / episode_id
                path.mkdir(parents=True, exist_ok=True)
                return path
            class Worker:
                def produce_episode(self, **kwargs):
                    kwargs["progress_callback"]({"stage": "synthesizing", "progress": 0.5})
                    if fail:
                        raise RuntimeError("TTS unavailable")
                    audio = episode_dir("test") / "audio.mp3"
                    audio.write_bytes(b"fake audio for orchestration test")
                    return {"audio_file": str(audio), "metadata": {}}
            async def run():
                with patch.object(production, "episode_dir", side_effect=episode_dir), \
                     patch.object(production, "MergedDandyPodcastWorker", Worker), \
                     patch.object(production, "load_media_cues", return_value={}), \
                     patch.object(production, "export_social_package", side_effect=RuntimeError("export failed") if export_fail else None), \
                     patch("app.websockets.manager.manager.broadcast", new_callable=AsyncMock) as broadcast:
                    await asyncio.to_thread(production._run_produce_background,
                        "test", "job_test", [{"speaker": "phil", "text": "A real test line", "generated_by": "manual_edit"}],
                        "Title", "Topic", "Text", None, {}, event_loop=asyncio.get_running_loop())
                    await asyncio.sleep(0)
                    events = [call.args[1] for call in broadcast.call_args_list]
                    return events
            events = asyncio.run(run())
            import json
            status = json.loads((episode_dir("test") / "status.json").read_text())
            job = json.loads((root / "episodes/.drafts/jobs/job_test.json").read_text())
            self.assertEqual(status, job)
            self.assertTrue(any(event["type"] == "production_progress" for event in events))
            if fail or export_fail:
                self.assertEqual(status["status"], "failed")
                self.assertEqual(events[-1]["type"], "production_error")
                self.assertNotIn("production_complete", [event["type"] for event in events])
                if fail:
                    self.assertFalse((episode_dir("test") / "audio.mp3").exists())
            else:
                self.assertEqual(status["status"], "produced")
                self.assertEqual(status["progress"], 1)
                self.assertEqual(events[-1]["type"], "production_complete")

    def test_persisted_progress_and_completion(self):
        self.run_job()

    def test_tts_failure_does_not_create_silent_success(self):
        self.run_job(fail=True)

    def test_export_failure_is_not_reported_as_complete(self):
        self.run_job(export_fail=True)

    def test_chunk_progress_and_missing_audio(self):
        worker = HardenedPodcastWorker.__new__(HardenedPodcastWorker)
        worker.voices_config = {"phil": {"primary_voice": "test"}}
        events = []
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(worker, "_synthesize_line", return_value="kokoro"):
            with self.assertRaisesRegex(RuntimeError, "no audio"):
                worker._synthesize_segments([{"speaker": "phil", "text": "Test dialogue"}], Path(directory), "test", events.append)
        self.assertEqual(events, [])


class RegenerationTests(unittest.TestCase):
    def setUp(self):
        self.script = [{"speaker": "phil" if i % 2 == 0 else "jim",
                        "text": f"Discussion point {i} has specific evidence and practical consequences for the people involved today.",
                        "generated_by": "governance_bridge", "line_number": i + 1, "pause_after": 0.4,
                        "custom_metadata": {"preserve": i}} for i in range(12)]
        self.raw = "PHIL [curious]: The revised evidence shows a different practical outcome for the families using this service today.\nJIM [pragmatic]: We should measure that outcome before assuming the change has solved the original problem for everyone."

    def request(self, raw=None, start=2, end=4, changed=False):
        from fastapi.testclient import TestClient
        from app.main import app
        reads = [deepcopy(self.script), deepcopy(self.script)]
        if changed:
            reads[1][0]["text"] = "Concurrent edit"
        with patch.object(production, "load_script", side_effect=[{"script": value} for value in reads]), \
             patch.object(production, "load_episode_detail", return_value={"config": {"target_duration": 60, "topic": "Evidence"}}), \
             patch.object(production, "build_source_context", return_value={}), \
             patch("app.services.production.llm_writer._call_bridge", return_value=(self.raw if raw is None else raw, "governance_bridge")), \
             patch.object(production, "save_script") as save, TestClient(app) as client:
            response = client.post("/api/episodes/edit-script", json={"episode_id": "test", "edit_type": "regenerate_section", "section_start": start, "section_end": end})
            saved = save.call_args.args[1] if save.called else None
        return response, saved

    def test_only_selected_slice_changes(self):
        response, saved = self.request()
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(saved[:2], self.script[:2])
        self.assertEqual(saved[4:], self.script[4:])
        self.assertNotEqual(saved[2:4], self.script[2:4])
        self.assertEqual(saved[2]["line_number"], 3)
        self.assertEqual(saved[3]["generated_by"], "governance_bridge")

    def test_bad_range_is_rejected_without_saving(self):
        response, saved = self.request(start=-1)
        self.assertEqual(response.status_code, 400)
        self.assertIsNone(saved)

    def test_offline_writer_leaves_script_unchanged(self):
        response, saved = self.request(raw="")
        self.assertEqual(response.status_code, 502)
        self.assertIsNone(saved)

    def test_quality_checks_reject_unresolved_templates(self):
        response, saved = self.request(raw=self.raw.replace("revised evidence", "{missing_source}"))
        self.assertEqual(response.status_code, 502)
        self.assertIsNone(saved)

    def test_wrong_speaker_order_is_rejected(self):
        response, saved = self.request(raw=self.raw.replace("PHIL [curious]", "JIM [curious]"))
        self.assertEqual(response.status_code, 502)
        self.assertIsNone(saved)

    def test_concurrent_edit_is_not_overwritten(self):
        response, saved = self.request(changed=True)
        self.assertEqual(response.status_code, 409)
        self.assertIsNone(saved)


if __name__ == "__main__":
    unittest.main()
