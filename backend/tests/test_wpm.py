import unittest

from app.services.production.wpm import measure_turn, measure_turns, word_count


class RenderedWpmTests(unittest.TestCase):
    def test_word_count_and_turn_measurement(self):
        self.assertEqual(word_count("Hold on. That does not make sense."), 7)
        result = measure_turn("Hold on. That does not make sense.", 4.6667)
        self.assertAlmostEqual(result["spoken_wpm"], 90.0, places=0)

    def test_turn_measurement_excludes_inter_turn_silence(self):
        result = measure_turns([
            {"text": "What if it works?", "audio_seconds": 2.0},
            {"text": "Hold on.", "audio_seconds": 2.0},
        ])
        self.assertEqual(result["words"], 6)
        self.assertAlmostEqual(result["spoken_wpm"], 90.0, places=0)


if __name__ == "__main__":
    unittest.main()
