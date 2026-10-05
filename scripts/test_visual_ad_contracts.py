"""Real, isolated FFmpeg composer checks; never writes operator episodes."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import test_ad_contracts  # Configure the existing Python/media paths.
from PIL import Image
from pydub import AudioSegment
from pydub.generators import Sine
from app.schemas.ads import AdComposition, AdTextLayer
from app.services.social import slideshow_renderer as renderer


class VisualAdContracts(unittest.TestCase):
    def test_all_motions_have_visible_entrance_exit_and_hidden_outside_timing(self):
        image = Image.new("RGBA", (100, 50), "white")
        for motion in ("none", "fade", "slide", "zoom", "reveal", "pulse"):
            layer = AdTextLayer(id=motion, start=1, end=3, animation_in=motion, animation_out=motion)
            self.assertIsNone(renderer._layer_motion(image, layer, .5, (320, 180)))
            self.assertIsNone(renderer._layer_motion(image, layer, 3, (320, 180)))
            early = renderer._layer_motion(image, layer, 1.15, (320, 180))
            middle = renderer._layer_motion(image, layer, 2, (320, 180))
            late = renderer._layer_motion(image, layer, 2.85, (320, 180))
            signature = lambda frame: (frame[0].size, frame[0].tobytes(), frame[1:])
            if motion != "none":
                self.assertNotEqual(signature(early), signature(middle), motion)
                self.assertNotEqual(signature(late), signature(middle), motion)

    def test_real_video_has_requested_size_timing_audio_visuals_and_sfx(self):
        ffmpeg, ffprobe = os.environ["DANDY_FFMPEG"], os.environ["DANDY_FFPROBE"]
        with tempfile.TemporaryDirectory(prefix="dandy_composer_") as folder:
            root = Path(folder)
            voice, sfx, visual = root / "voice.wav", root / "sfx.wav", root / "clip.mp4"
            AudioSegment.silent(duration=2000, frame_rate=24000).export(voice, format="wav").close()
            Sine(880).to_audio_segment(duration=300).export(sfx, format="wav").close()
            subprocess.run([ffmpeg, "-v", "error", "-y", "-f", "lavfi", "-i", "color=blue:s=160x90:d=1",
                            "-c:v", "libx264", "-pix_fmt", "yuv420p", str(visual)], check=True, timeout=30)
            logo = root / "logo.png"
            Image.new("RGB", (100, 100), "red").save(logo)
            assets = [{"asset_id": key, "stored_path": str(path)} for key, path in
                      (("clip", visual), ("logo", logo), ("tone", sfx))]
            ad = {"ad_id": "isolated", "duration_seconds": 2, "audio_file": str(voice)}
            composition = AdComposition(
                aspect="16:9", text_layers=[{"id": "text", "content": "Exact café copy", "start": .2, "end": 1.8,
                                             "animation_in": "slide", "animation_out": "reveal"}],
                visuals=[{"id": "video", "asset_id": "clip", "start": 0, "end": 2, "animation_in": "none", "animation_out": "none"},
                         {"id": "image", "asset_id": "logo", "role": "logo", "width": .2, "start": .5, "end": 1.5,
                          "x": .8, "y": .8, "animation_in": "none", "animation_out": "none"}],
                sfx_tracks=[{"id": "effect", "asset_id": "tone", "start": 1, "volume_db": -6}])
            with patch.object(renderer, "RENDERS_DIR", root):
                result = renderer.render_composed_ad(ad, composition, assets)
            output = Path(result["path"])
            probe = json.loads(subprocess.check_output([ffprobe, "-v", "error", "-show_streams", "-show_format", "-of", "json", str(output)], timeout=15))
            video = next(stream for stream in probe["streams"] if stream["codec_type"] == "video")
            self.assertEqual((video["width"], video["height"]), (1920, 1080))
            self.assertTrue(any(stream["codec_type"] == "audio" for stream in probe["streams"]))
            self.assertAlmostEqual(float(probe["format"]["duration"]), 2, delta=.1)
            decoded = AudioSegment.from_file(output)
            self.assertLess(decoded[100:300].rms, 10)
            self.assertGreater(decoded[1050:1200].rms, 100)
            frames = []
            for timestamp in (.05, 1, 1.95):
                raw = subprocess.check_output([ffmpeg, "-v", "error", "-ss", str(timestamp), "-i", str(output),
                                               "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"], timeout=20)
                frames.append(Image.frombytes("RGB", (1920, 1080), raw))
            self.assertGreater(frames[0].getpixel((100, 100))[2], 200)
            self.assertGreater(frames[1].getpixel((1536, 864))[0], 200)
            self.assertLess(frames[2].getpixel((1536, 864))[0], 20)
            self.assertFalse(list(root.glob("ad_render_*")), "Render scratch leaked")

    def test_missing_video_cleans_up_failed_output(self):
        with tempfile.TemporaryDirectory(prefix="dandy_bad_render_") as folder:
            root = Path(folder)
            voice, video = root / "voice.wav", root / "invalid.mp4"
            AudioSegment.silent(duration=500).export(voice, format="wav").close()
            video.write_bytes(b"invalid video")
            composition = AdComposition(visuals=[{"id": "broken", "asset_id": "broken", "end": 1}])
            with patch.object(renderer, "RENDERS_DIR", root), self.assertRaisesRegex(RuntimeError, "Video decode"):
                renderer.render_composed_ad({"ad_id": "bad", "duration_seconds": 1, "audio_file": str(voice)},
                                            composition, [{"asset_id": "broken", "stored_path": str(video)}])
            self.assertFalse(list(root.glob("advisual_*")))
            self.assertFalse(list(root.glob("ad_render_*")))


if __name__ == "__main__":
    unittest.main(verbosity=2)
