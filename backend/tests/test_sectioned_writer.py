"""Sectioned episode writing and strict response parsing (no provider calls)."""
import json
import unittest
from unittest.mock import patch

from app.services.production import llm_writer as writer

PHRASES = ["the record speaks when presence is questioned", "desktop organizes timelines and evidence",
           "mobile capture keeps field notes honest", "children deserve fairness from both parents",
           "evidence that contradicts us matters too", "showing up and proving it are different",
           "abuse is real and must be taken seriously", "most fathers deserve to be assessed on evidence",
           "documentation is discipline not revenge", "accountability protects everybody involved"]


def turns(first, count, offset):
    speakers = ['phil', 'jim'] if first == 'phil' else ['jim', 'phil']
    return [{'speaker': speakers[i % 2],
             'text': f"Point {offset + i}: {PHRASES[(offset + i) % len(PHRASES)]} and that is worth saying in full "
                     f"because listeners {offset + i} need the whole picture today.",
             'emotion': 'thoughtful', 'pause_after': 0.4} for i in range(count)]


class ParserTests(unittest.TestCase):
    def test_block_layout_is_parsed_strictly(self):
        raw = ("PHIL: Showing up and proving it are different things.\nEmotion: earnest\npause_after: 0.6\n"
               "JIM: Then tell me how the record helps.\nEmotion: skeptical\npause_after: 0.5\n")
        parsed = writer.parse_dialogue(raw)
        self.assertEqual([t['speaker'] for t in parsed], ['phil', 'jim'])
        self.assertEqual(parsed[0]['pause_after'], 0.6)

    def test_block_layout_with_stray_line_is_rejected_not_trimmed(self):
        raw = ("PHIL: Showing up matters.\nEmotion: earnest\npause_after: 0.6\n"
               "(laughs)\nJIM: Sure.\nEmotion: dry\npause_after: 0.5\n")
        with self.assertRaisesRegex(RuntimeError, 'neither'):
            writer.parse_dialogue(raw)

    def test_section_respects_expected_first_speaker(self):
        with self.assertRaisesRegex(RuntimeError, 'must be jim'):
            writer.parse_dialogue(json.dumps(turns('phil', 2, 0)), first_speaker='jim')


class SectionedGenerationTests(unittest.TestCase):
    def fake_provider(self, words_per_turn_target=None):
        calls = []

        def call(prompt, **kwargs):
            calls.append(prompt)
            first = 'jim' if 'The first turn is jim' in prompt else 'phil'
            return json.dumps(turns(first, 20, len(calls) * 20))
        return call, calls

    def test_full_episode_written_in_sections_with_running_context(self):
        call, calls = self.fake_provider()
        progress = []
        with patch.object(writer, '_call_nvidia', side_effect=call):
            script = writer.generate_episode_script('CTX', target_words=1650, progress=progress.append)
        self.assertEqual(len(calls), 3)
        self.assertIn('OPENING section', calls[0])
        self.assertIn('MIDDLE section', calls[1])
        self.assertIn('FINAL section', calls[2])
        self.assertIn('(nothing yet)', calls[0])
        self.assertIn(script[19]['text'], calls[1])              # later sections see prior dialogue
        self.assertTrue(calls[0].rstrip().endswith('"pause_after": 0.4}]'))  # format contract is last
        self.assertEqual([p['section'] for p in progress], [1, 2, 3])
        speakers = [line['speaker'] for line in script]
        self.assertTrue(all(a != b for a, b in zip(speakers, speakers[1:])))
        self.assertEqual(script[-1]['line_number'], len(script))

    def test_unparseable_section_retried_once_then_fails(self):
        with patch.object(writer, '_call_nvidia', return_value='Here is my plan for the episode.') as call:
            with self.assertRaisesRegex(RuntimeError, 'neither'):
                writer.generate_episode_script('CTX', target_words=1100)
        self.assertEqual(call.call_count, 2)

    def test_retry_recovers_a_section(self):
        good = json.dumps(turns('phil', 8, 0))
        with patch.object(writer, '_call_nvidia', side_effect=['not json', good]):
            script = writer.generate_episode_script('CTX', sample=True)
        self.assertEqual(len(script), 8)

    def test_cancellation_stops_between_sections(self):
        import threading
        cancel = threading.Event()
        call, calls = self.fake_provider()

        def cancelling(prompt, **kwargs):
            cancel.set()
            return call(prompt, **kwargs)
        with patch.object(writer, '_call_nvidia', side_effect=cancelling):
            with self.assertRaisesRegex(RuntimeError, 'cancelled'):
                writer.generate_episode_script('CTX', target_words=1650, cancel_event=cancel)
        self.assertEqual(len(calls), 1)


if __name__ == '__main__':
    unittest.main()
