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

    def test_bad_batch_is_retried_as_a_complete_exchange(self):
        bad = "PHIL [warm]: The person was actively\nJIM [dry]: Show me a real scenario.indle"
        good = "PHIL [warm]: We can ask what evidence would support a presence claim.\nJIM [dry]: First establish consent, then describe the limits of that evidence."
        with patch.object(writer, "_call_bridge", side_effect=[(bad, "llamacpp"), (good, "llamacpp")]) as call:
            lines = writer.generate_segment("Presence", [], "expansion", [], n_exchanges=1)
        self.assertEqual(len(lines), 2)
        self.assertEqual(call.call_count, 2)
        self.assertTrue(all(writer.dialogue_issue(line["text"]) is None for line in lines))

    def test_missing_speaker_never_publishes_half_an_exchange(self):
        with patch.object(writer, "_call_bridge", return_value=("PHIL: This is a complete but unpaired turn.", "llamacpp")):
            self.assertEqual(writer.generate_segment("Presence", [], "expansion", [], n_exchanges=1), [])

    def test_token_limit_response_is_not_accepted_as_dialogue(self):
        with patch.object(writer, "_verified_model", return_value="pinned"), \
             patch.object(writer, "_post_json", return_value={"choices": [{"finish_reason": "length", "message": {"content": "PHIL: A truncated"}}]}):
            self.assertIsNone(writer._call_llamacpp("Write complete dialogue", n_exchanges=1))

    def test_structured_decoding_avoids_character_limits_and_preserves_all_lines(self):
        payload = {"lines": [{"speaker": "Phil", "emotion": "warm", "text": "Evidence of presence still needs clear limits and informed consent."},
                             {"speaker": "Jim", "emotion": "dry", "text": "Right, being there does not prove someone was paying attention."}]}
        with patch.object(writer, "_verified_model", return_value="pinned"), \
             patch.object(writer, "_post_json", return_value={"choices": [{"message": {"content": json.dumps(payload)}}]}) as post:
            lines = writer.generate_segment("POPS", [], "expansion", [], n_exchanges=1)
        request = post.call_args.args[1]
        self.assertNotIn("grammar", request)
        self.assertEqual(request["response_format"]["type"], "json_schema")
        self.assertEqual([line["text"] for line in lines], [line["text"] for line in payload["lines"]])

    def test_five_minute_plan_scales_with_word_budget(self):
        small = SegmentAwarePodcastWorker._stage_plan(160)
        full = SegmentAwarePodcastWorker._stage_plan(800)
        self.assertEqual(full[0][0], "opening")
        self.assertEqual(full[-1][0], "closing")
        self.assertGreater(sum(n for _, n in full), sum(n for _, n in small))

    def test_editorial_assignment_survives_long_persona_rules(self):
        brief = "EXPLICIT ASSIGNMENT: Close the episode and do not invent POPS capabilities."
        prompt = writer._build_prompt("POPS", [], "closing", writer._STAGES["closing"], [], "", 1,
                                      persona_brief="Persona rule. " * 1000, production_brief=brief)
        self.assertIn(brief, prompt)
        self.assertNotIn("{8,180}", writer._dialogue_grammar(1))

    def test_stage_plan_contains_opening_and_closing_and_keeps_instructions(self):
        worker = SegmentAwarePodcastWorker.__new__(SegmentAwarePodcastWorker)
        worker.project_config = {}
        worker._apply_personality_settings = Mock()
        worker._is_near_duplicate = lambda text, prior: False
        worker._repetition_score = lambda text, prior: 0
        worker._conversation_to_script = lambda values: values
        worker.communication_layer = Mock()
        worker.communication_layer.phil = None
        worker.communication_layer.jim = None
        worker.communication_layer._build_context.return_value = {"primary_source_summary": "Only the supplied definition is known."}
        worker.communication_layer._build_persona_brief.return_value = "Persona rule. " * 1000
        worker.communication_layer._repeat_key.side_effect = lambda text: text.lower()
        serial = 0
        def generate(**kwargs):
            nonlocal serial
            result = []
            for index in range(kwargs["n_exchanges"] * 2):
                serial += 1
                result.append({"speaker": "Phil" if index % 2 == 0 else "Jim", "text": f"Distinct evidence number {serial} deserves a careful and complete discussion.",
                               "generated_by": "llamacpp", "generation_stage": kwargs["stage"]})
            return result
        with patch.object(writer, "generate_segment", side_effect=generate) as call:
            result = worker._try_skg_generation({"target_duration": 300, "target_word_count": 800,
                "custom_instructions": "Do not invent POPS hardware."}, {}, ["Explain the term"], "POPS", "POPS", 0)
        self.assertTrue(result)
        self.assertEqual([c.kwargs["stage"] for c in call.call_args_list], ["opening", "expansion", "deepening", "reflection", "closing"])
        self.assertTrue(all("Do not invent POPS hardware." in c.kwargs["production_brief"] for c in call.call_args_list))
