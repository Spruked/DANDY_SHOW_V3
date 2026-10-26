import io
import json
import unittest
from unittest.mock import patch
from app.services.production import llm_writer as writer


class WriterModelTests(unittest.TestCase):
    def test_wrong_model_blocks_generation(self):
        with patch.object(writer.urllib.request, "urlopen", return_value=io.BytesIO(json.dumps({"data": [{"id": "other.gguf"}]}).encode())), patch.object(writer, "_post_json") as post:
            with self.assertRaises(RuntimeError):
                writer._call_bridge("Write dialogue")
            post.assert_not_called()

    def test_verified_model_is_sent_to_llamacpp(self):
        model = "C:/models/" + writer._REQUIRED_MODEL_FILE
        with patch.object(writer, "_verified_model", return_value=model), patch.object(writer, "_post_json", return_value={"choices": [{"message": {"content": "PHIL: A fresh idea."}}]}) as post:
            text, provider = writer._call_bridge("Write dialogue")
            self.assertEqual(provider, "llamacpp")
            self.assertEqual(post.call_args.args[1]["model"], model)
            self.assertIn("fresh idea", text)

    def test_offline_status_has_no_fallback(self):
        with patch.object(writer, "_verified_model", side_effect=RuntimeError("offline")):
            status = writer.writer_status()
            self.assertFalse(status["bridge_reachable"])
            self.assertFalse(status["allow_model_fallback"])
            self.assertEqual(status["writer_backend"], "offline")
