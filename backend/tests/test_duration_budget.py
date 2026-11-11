"""Episode timing: dialogue + pauses + ads + theme must fit the complete target."""
import unittest

from app.services.production import duration
from app.services.production.ads import AD_SLOT_IDS

CFG = {
    "production": {"spoken_wpm": 160, "ad_policy": {"midroll_duration_seconds": 30}},
    "intro_outro": {"enabled": True,
                    "intro": {"clip_duration_ms": 14000, "silence_after_ms": 800},
                    "outro": {"clip_duration_ms": 14000, "silence_before_ms": 600}},
}


def slots(assigned=None):
    assigned = assigned or {}
    return [{"slot_id": s, "status": "assigned" if s in assigned else "reserved",
             "duration_seconds": assigned.get(s, 0)} for s in AD_SLOT_IDS]


class DurationBudgetTests(unittest.TestCase):
    def test_theme_seconds_from_config(self):
        self.assertAlmostEqual(duration.theme_seconds(CFG), 29.4)
        self.assertEqual(duration.theme_seconds({**CFG, "intro_outro": {"enabled": False}}), 0.0)

    def test_reserved_slots_hold_policy_length_assigned_use_measured(self):
        ads = duration.advertising_seconds(slots({"mid_roll_1": 42.5}), CFG)
        self.assertEqual(ads["assigned_seconds"], 42.5)
        self.assertEqual(ads["reserved_seconds"], 6 * 30)
        self.assertEqual(ads["total_seconds"], 222.5)

    def test_25_minute_episode_leaves_room_for_ads_theme_and_pauses(self):
        budget = duration.dialogue_budget(1500, slots(), CFG)
        self.assertEqual(budget["advertising_seconds"], 210)
        self.assertLess(budget["target_words"], 1500 / 60 * 160)  # not the naive 4000
        # Round-trip: estimated complete length lands on the target.
        words = budget["target_words"]
        turns = words / duration.DEFAULT_WORDS_PER_TURN
        spoken = words / 160 * 60 + turns * duration.DEFAULT_PAUSE_SECONDS
        total = spoken + budget["advertising_seconds"] + budget["theme_seconds"]
        self.assertAlmostEqual(total, 1500, delta=2)

    def test_minimum_dialogue_floor(self):
        self.assertEqual(duration.dialogue_budget(100, slots(), CFG)["target_words"], duration.MIN_DIALOGUE_WORDS)

    def test_line_seconds_uses_shared_rate(self):
        self.assertAlmostEqual(duration.line_seconds({"text": "one two three four", "pause_after": 0.5}, 160), 2.0)


if __name__ == "__main__":
    unittest.main()
