"""Isolated ad contract regressions. Run: .venv/Scripts/python scripts/test_ad_contracts.py.

All writes use TemporaryDirectory; no live API, episodes, or inference is used.
Real FFmpeg audio checks run against generated WAV/MP3 fixtures.
"""
import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from contextlib import ExitStack
from unittest.mock import patch, Mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
for media_bin in (ROOT / "staging/ffmpeg/ffmpeg-master-latest-win64-gpl/bin",
                  ROOT.parent / "Dandy/staging/ffmpeg/ffmpeg-master-latest-win64-gpl/bin"):
    if (media_bin / "ffmpeg.exe").is_file():
        os.environ["PATH"] = str(media_bin) + os.pathsep + os.environ.get("PATH", "")
        os.environ["DANDY_FFMPEG"] = str(media_bin / "ffmpeg.exe")
        os.environ["DANDY_FFPROBE"] = str(media_bin / "ffprobe.exe")
        break

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydub import AudioSegment
from app.api import ads, production
from app.core import settings
from app.services.storage import episode_store as storage
from app.services.production.worker import HardenedPodcastWorker
from app.services.production.segment_worker import SegmentAwarePodcastWorker
from app.services.production.ads import generate_ad_lines
from app.services.production.ads import ad_audio_fingerprint, mix_ad_tracks
from app.services.ads.ad_engine import generate_ad_script


class AdContracts(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory(prefix="dandy_ad_test_")))
        episodes = self.root / "episodes"
        for module, name, value in (
            (storage, "EPISODES_ROOT", episodes), (storage, "DRAFTS_ROOT", episodes / ".drafts"),
            (storage, "JOBS_ROOT", episodes / ".drafts/jobs"), (ads, "EPISODES_ROOT", episodes),
            (ads, "PROJECT_ROOT", self.root),
        ):
            self.stack.enter_context(patch.object(module, name, value))
        self.voices = {key: {"primary_voice": "voice_" + key} for key in
                       ("phil", "jim", "announcer_male", "announcer_female", "custom_reader")}
        self.stack.enter_context(patch.object(settings, "load_voices_config", return_value=self.voices))
        app = FastAPI()
        app.include_router(ads.router, prefix="/api")
        self.client = self.stack.enter_context(TestClient(app))
        self.url = "/api/episodes/isolated/ads"
        storage.save_script("isolated", [{"speaker": "phil", "text": "Opening."},
                                         {"speaker": "jim", "text": "Closing."}])

    def create(self, **kwargs):
        response = self.client.post(self.url, json={"sponsor": "Sample", "custom_script": "Exact copy.", **kwargs})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["ad"]

    def worker(self):
        worker = SegmentAwarePodcastWorker.__new__(SegmentAwarePodcastWorker)
        worker.base_path = self.root
        worker.voices_config = self.voices
        worker.project_config = {"tts": {"primary_engine": "qwen"}}
        worker.qwen_tts_config = {"enabled": True, "voices": {key: "qwen_" + key for key in self.voices}}
        return worker

    def test_copy_duration_and_registered_voices_round_trip(self):
        copy_text = "Phil: Exact first line — café.\r\nJim: Keep  two spaces!\nFinal CTA."
        for duration in (5, 60, 90, 120):
            for voice in self.voices:
                with self.subTest(duration=duration, voice=voice):
                    ad = self.create(custom_script=copy_text, duration_seconds=duration, announcer_key=voice)
                    self.assertEqual(ad["custom_script"], copy_text)
                    self.assertEqual(ad["duration_seconds"], duration)
                    self.assertEqual([line["speaker"] for line in ad["script"]], ["phil", "jim", voice])
                    self.assertEqual(ad["script"][1]["text"], "Keep  two spaces!")
                    self.assertIn(ad, storage.list_ads("isolated"))

    def test_custom_registry_prefix_is_resolved(self):
        ad = self.create(custom_script="custom_reader: Read this literally.", announcer_key="jim")
        self.assertEqual(ad["script"][0]["speaker"], "custom_reader")
        self.assertEqual(ad["script"][0]["text"], "Read this literally.")

    def test_unregistered_inline_voice_fails(self):
        del self.voices["jim"]
        response = self.client.post(self.url, json={"sponsor": "Sample", "custom_script": "Jim: Missing voice."})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(storage.list_ads("isolated"), [])

    def test_invalid_duration_and_voice_do_not_save(self):
        for payload in ({"duration_seconds": 4}, {"duration_seconds": 121}, {"announcer_key": "missing"}):
            response = self.client.post(self.url, json={"sponsor": "Sample", **payload})
            self.assertEqual(response.status_code, 422)
        self.assertEqual(storage.list_ads("isolated"), [])

    def test_insertion_bounds_idempotence_and_tags(self):
        ad = self.create(custom_script="Phil: One.\nJim: Two.")
        before = copy.deepcopy(storage.load_script("isolated"))
        self.assertEqual(self.client.post(f"{self.url}/{ad['ad_id']}/insert", json={"line_index": 3}).status_code, 400)
        self.assertEqual(storage.load_script("isolated"), before)
        route = f"{self.url}/{ad['ad_id']}/insert"
        self.assertEqual(self.client.post(route, json={"line_index": 1}).json()["insert_at"], 1)
        self.assertEqual(self.client.post(route, json={"line_index": 0}).json()["status"], "already_inserted")
        lines = storage.load_script("isolated")["script"]
        self.assertEqual([line["line_number"] for line in lines], [1, 2, 3, 4])
        self.assertEqual([line["ad_line_index"] for line in lines if line.get("is_ad")], [1, 2])
        self.assertNotIn("ad_id", storage.list_ads("isolated")[0]["script"][0])

    def test_invalid_create_and_insert_does_not_leave_an_ad(self):
        response = self.client.post(self.url, json={"sponsor": "Sample", "insert_into_script": True, "line_index": 99})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(storage.list_ads("isolated"), [])

    def test_metadata_sidecars_are_not_ads(self):
        ad = self.create()
        (storage.ads_dir("isolated") / f"{ad['ad_id']}_assets.json").write_text('[]', encoding="utf-8")
        self.assertEqual(len(storage.list_ads("isolated")), 1)

    def test_composition_save_validates_assets_and_timing(self):
        ad = self.create(duration_seconds=5)
        route = f"{self.url}/{ad['ad_id']}/composition"
        for payload in ({"visuals": [{"id": "image", "asset_id": "missing", "end": 5}]},
                        {"sfx_tracks": [{"id": "sound", "asset_id": "missing"}]},
                        {"text_layers": [{"id": "text", "end": 6}]}):
            self.assertEqual(self.client.put(route, json=payload).status_code, 422)

    def test_composition_properties_survive_save_reload(self):
        ad = self.create(duration_seconds=5)
        payload = {"version": 1, "aspect": "4:5", "background_color": "#123456", "visuals": [], "sfx_tracks": [],
                   "text_layers": [{"id": "text", "content": "Literal text.", "role": "cta", "start": 1, "end": 4,
                    "animation_in": "slide", "animation_out": "reveal", "animation_duration": .7, "easing": "linear",
                    "x": .3, "y": .6, "font": "Georgia", "size": 42, "align": "right", "color": "#aabbcc"}]}
        response = self.client.put(f"{self.url}/{ad['ad_id']}/composition", json=payload)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(storage.list_ads("isolated")[0]["composition"], payload)

    def test_unknown_worker_voice_fails_instead_of_remapping(self):
        with self.assertRaisesRegex(RuntimeError, "[Vv]oice|[Ss]peaker"):
            self.worker()._normalize_speaker("missing_reader")

    def test_selected_engine_failure_never_calls_another_provider(self):
        worker = self.worker()
        worker.project_config["tts"]["primary_engine"] = "kokoro"
        worker._try_kokoro = Mock(side_effect=RuntimeError("fixture unavailable"))
        worker._try_qwen_bridge = Mock()
        worker._synthesize_edge = Mock()
        with self.assertRaisesRegex(RuntimeError, "Kokoro"):
            worker._synthesize_line("Literal.", "phil", "neutral", self.root / "out.mp3")
        worker._try_qwen_bridge.assert_not_called()
        worker._synthesize_edge.assert_not_called()

    def test_saved_audio_reuse_requires_copy_delivery_and_voice_match(self):
        ad, response = self.produce_fixture(500)
        self.assertEqual(response.status_code, 200, response.text)
        ad = response.json()["ad"]
        lines = [{**line, "ad_id": ad["ad_id"]} for line in ad["script"]]
        worker = self.worker()
        worker._synthesize_line = Mock(side_effect=AssertionError("Saved ads must not synthesize again"))
        result = worker._synthesize_segments(lines, self.root, "isolated")
        self.assertEqual(result[0]["audio_file"], ad["audio_file"])
        for key, value in (("text", "Changed copy"), ("speaker", "jim"), ("pause_after", 1.8), ("emotion", "calm")):
            changed = copy.deepcopy(lines)
            changed[0][key] = value
            with self.subTest(key=key), self.assertRaisesRegex(RuntimeError, "does not match"):
                worker._synthesize_segments(changed, self.root, "isolated")
        worker.qwen_tts_config["voices"]["announcer_male"] = "different_voice"
        with self.assertRaisesRegex(RuntimeError, "voice settings"):
            worker._synthesize_segments(lines, self.root, "isolated")
        worker._synthesize_line.assert_not_called()

    def test_saved_ad_sfx_is_the_same_mix_used_in_episode_assembly(self):
        from pydub.generators import Sine
        ad, response = self.produce_fixture(500)
        self.assertEqual(response.status_code, 200, response.text)
        ad = response.json()["ad"]
        sound = self.root / "sfx.wav"
        Sine(880).to_audio_segment(duration=300).export(sound, format="wav").close()
        assets = [{"asset_id": "tone", "stored_path": str(sound)}]
        tracks = [{"id": "effect", "asset_id": "tone", "start": 1.0, "volume_db": -6}]
        ad["composition"] = {"sfx_tracks": tracks}
        storage.save_ad("isolated", ad)
        (storage.ads_dir("isolated") / f"{ad['ad_id']}_assets.json").write_text(json.dumps(assets), encoding="utf-8")
        reference = mix_ad_tracks(ad, tracks, assets)
        self.assertGreater(reference[1000:1200].rms, 100)
        segments = self.worker()._synthesize_segments([{**line, "ad_id": ad["ad_id"]} for line in ad["script"]], self.root, "isolated")
        with open(segments[0]["audio_file"], "rb") as handle:
            mixed = AudioSegment.from_file(handle, format="mp3")
        self.assertEqual(len(mixed), 5000)
        self.assertGreater(mixed[1000:1200].rms, 100)
        self.assertLess(mixed[2000:2200].rms, 10)

    def test_tts_chunking_preserves_words_and_punctuation(self):
        text = "alpha, beta; gamma: " * 30
        self.assertEqual(" ".join(self.worker()._split_for_tts(text)), " ".join(text.split()))

    def test_catalog_has_no_repeated_filler_or_episode_claims(self):
        lines = generate_ad_script("truemark", "jim", "Episode text is not a sponsor claim.", 120)
        text = " ".join(line["text"] for line in lines)
        self.assertNotIn("Episode text is not a sponsor claim.", text)
        self.assertLessEqual(text.lower().count("show notes"), 1)

    def test_generic_copy_does_not_invent_offer_or_repeat_it(self):
        lines = generate_ad_lines("Sample", "Widget", "", "Visit example.test.", 90)
        text = " ".join(line["text"] for line in lines)
        self.assertNotIn("Exclusive", text)
        self.assertEqual(text.count("Visit example.test."), 1)

    def produce_fixture(self, milliseconds):
        worker = self.worker()
        def synthesize(lines, output_dir, episode_id):
            path = output_dir / "fixture.wav"
            AudioSegment.silent(duration=milliseconds, frame_rate=24000).export(path, format="wav").close()
            return [{"audio_file": str(path), "speaker": "announcer_male", "engine": "qwen", "voice_name": "qwen_announcer_male", "pause_after": 0}]
        worker._synthesize_segments = synthesize
        self.stack.enter_context(patch.object(production, "_get_worker", return_value=worker))
        ad = self.create(duration_seconds=5)
        return ad, self.client.post(f"{self.url}/{ad['ad_id']}/produce")

    def test_short_audio_is_padded_and_actual_voice_is_recorded(self):
        ad, response = self.produce_fixture(500)
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()["ad"]
        with open(result["audio_file"], "rb") as handle:
            self.assertAlmostEqual(len(AudioSegment.from_file(handle, format="mp3")) / 1000, 5, places=2)
        self.assertEqual(result["custom_script"], ad["custom_script"])
        self.assertEqual(result["voice_resolution"][0]["resolved_voice_id"], "qwen_announcer_male")

    def test_overlong_audio_is_rejected_without_publishing(self):
        ad, response = self.produce_fixture(5500)
        self.assertEqual(response.status_code, 422, response.text)
        self.assertNotIn("audio_file", storage.list_ads("isolated")[0])


if __name__ == "__main__":
    unittest.main(verbosity=2)
