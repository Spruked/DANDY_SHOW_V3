"""Single source for episode timing assumptions.

The episode target is the complete mastered length: dialogue, the pauses
between turns, advertisements and theme audio. Every caller that converts
between words and seconds must use these helpers so estimates agree.
"""
from typing import Dict, Optional

DEFAULT_SPOKEN_WPM = 160
DEFAULT_PAUSE_SECONDS = 0.4
DEFAULT_WORDS_PER_TURN = 16
MIN_DIALOGUE_WORDS = 600


def _project_config(cfg: Optional[Dict]) -> Dict:
    if cfg is not None:
        return cfg
    from ...core.settings import load_project_config
    return load_project_config()


def spoken_wpm(cfg: Optional[Dict] = None) -> int:
    production = _project_config(cfg).get("production", {}) or {}
    return max(1, int(production.get("spoken_wpm", DEFAULT_SPOKEN_WPM)))


def line_seconds(line: Dict, wpm: int) -> float:
    words = len(str(line.get("text", "")).split())
    return words / wpm * 60 + float(line.get("pause_after", 0) or 0)


def theme_seconds(cfg: Optional[Dict] = None) -> float:
    """Intro and outro music beds as configured (narration plays over them)."""
    io_cfg = _project_config(cfg).get("intro_outro", {}) or {}
    if not io_cfg.get("enabled"):
        return 0.0
    intro, outro = io_cfg.get("intro", {}) or {}, io_cfg.get("outro", {}) or {}
    total_ms = (float(intro.get("clip_duration_ms", 0)) + float(intro.get("silence_after_ms", 0))
                + float(outro.get("clip_duration_ms", 0)) + float(outro.get("silence_before_ms", 0)))
    return round(total_ms / 1000, 3)


def advertising_seconds(slots, cfg: Optional[Dict] = None) -> Dict[str, float]:
    """Assigned slots use their measured length; reserved slots hold the policy length.

    Reserving time for unassigned slots keeps the 25-minute total intact when
    commercials are assigned after the script is written.
    """
    policy = (_project_config(cfg).get("production", {}) or {}).get("ad_policy", {}) or {}
    reserved_each = max(0.0, float(policy.get("midroll_duration_seconds", 30)))
    assigned = sum(float(slot.get("duration_seconds") or 0) for slot in slots if slot.get("status") == "assigned")
    reserved = sum(reserved_each for slot in slots if slot.get("status") != "assigned")
    return {"assigned_seconds": round(assigned, 3), "reserved_seconds": round(reserved, 3),
            "total_seconds": round(assigned + reserved, 3)}


def dialogue_budget(target_seconds: float, slots, cfg: Optional[Dict] = None) -> Dict[str, float]:
    """Words of host dialogue that fit the complete episode target."""
    cfg = _project_config(cfg)
    wpm = spoken_wpm(cfg)
    ads = advertising_seconds(slots, cfg)
    theme = theme_seconds(cfg)
    dialogue_seconds = max(60.0, float(target_seconds) - ads["total_seconds"] - theme)
    # seconds per word = speech time + its share of the pause after each turn
    seconds_per_word = 60 / wpm + DEFAULT_PAUSE_SECONDS / DEFAULT_WORDS_PER_TURN
    words = max(MIN_DIALOGUE_WORDS, round(dialogue_seconds / seconds_per_word))
    return {"target_seconds": float(target_seconds), "spoken_wpm": wpm,
            "advertising_seconds": ads["total_seconds"], "advertising_assigned_seconds": ads["assigned_seconds"],
            "advertising_reserved_seconds": ads["reserved_seconds"], "theme_seconds": theme,
            "dialogue_seconds": round(dialogue_seconds, 3), "target_words": words}


# ── Three-segment episodes ──────────────────────────────────────────────────
DEFAULT_SEGMENTS = {"count": 3, "talk_minutes": 10, "min_talk_minutes": 10, "max_talk_minutes": 12,
                    "max_pass_words": 700, "continuity_lines": 5,
                    "ad_layout": {"before_segment_1": ["pre_roll_1", "pre_roll_2"],
                                  "after_segment_1": ["mid_roll_1", "mid_roll_2"],
                                  "after_segment_2": ["mid_roll_3", "mid_roll_4"],
                                  "after_segment_3": ["post_roll_1"]}}


def segment_settings(cfg: Optional[Dict] = None) -> Dict:
    configured = (_project_config(cfg).get("production", {}) or {}).get("segments", {}) or {}
    return {**DEFAULT_SEGMENTS, **configured}


def seconds_per_word(cfg: Optional[Dict] = None) -> float:
    """Speech plus each word's share of the pause after its turn."""
    return 60 / spoken_wpm(cfg) + DEFAULT_PAUSE_SECONDS / DEFAULT_WORDS_PER_TURN


def segment_word_budget(talk_minutes: float, cfg: Optional[Dict] = None) -> int:
    """Talk length includes the pauses between turns."""
    return round(float(talk_minutes) * 60 / seconds_per_word(cfg))


def episode_runtime(talk_minutes, slots, cfg: Optional[Dict] = None, actual_words=None) -> Dict:
    """Broadcast runtime = segment talk + advertising slots + theme audio.

    talk_minutes is one value per segment. actual_words (optional, per segment)
    replaces the planned talk time with an estimate from written dialogue.
    """
    cfg = _project_config(cfg)
    per_word = seconds_per_word(cfg)
    segments = []
    for index, minutes in enumerate(talk_minutes, 1):
        planned = round(float(minutes) * 60, 3)
        words = (actual_words or [None] * len(talk_minutes))[index - 1]
        segments.append({"segment_index": index, "talk_minutes": float(minutes),
                         "planned_talk_seconds": planned,
                         "target_words": segment_word_budget(minutes, cfg),
                         "written_words": words,
                         "estimated_talk_seconds": round(words * per_word, 3) if words is not None else planned})
    ads = advertising_seconds(slots, cfg)
    theme = theme_seconds(cfg)
    talk = round(sum(item["estimated_talk_seconds"] for item in segments), 3)
    return {"segments": segments, "talk_seconds": talk, "advertising_seconds": ads["total_seconds"],
            "advertising_assigned_seconds": ads["assigned_seconds"],
            "advertising_reserved_seconds": ads["reserved_seconds"], "theme_seconds": theme,
            "runtime_seconds": round(talk + ads["total_seconds"] + theme, 3),
            "target_words": sum(item["target_words"] for item in segments), "spoken_wpm": spoken_wpm(cfg)}
