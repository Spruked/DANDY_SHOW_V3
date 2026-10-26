"""Contract tests use temporary storage and fake TTS/LLM; never touch episodes."""
import asyncio
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


if __name__ == "__main__":
    unittest.main()
