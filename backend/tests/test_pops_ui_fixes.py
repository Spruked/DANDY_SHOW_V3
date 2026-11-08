"""Regressions from the POPS_UI_001 browser handoff."""
import io
import json
import unittest
from unittest.mock import Mock, patch

from app.services.production import llm_writer as writer
from app.services.production.segment_worker import SegmentAwarePodcastWorker


class WriterQualityTests(unittest.TestCase):
    def test_reported_fragments_and_unfinished_turns_are_rejected(self):
        for text in ["Show me a real scenario.indle", "How does this work? Inde", "The person was actively"]:
            with self.subTest(text=text):
                self.assertIsNotNone(writer.dialogue_issue(text))
        self.assertIsNone(writer.dialogue_issue("We need evidence before claiming this works."))



    def test_token_limit_response_is_not_accepted_as_dialogue(self):
        with patch.object(writer, "_verified_model", return_value="pinned"), \
             patch.object(writer, "_post_json", return_value={"choices": [{"finish_reason": "length", "message": {"content": "PHIL: A truncated"}}]}):
            self.assertIsNone(writer._call_llamacpp("Write complete dialogue", n_exchanges=1))




