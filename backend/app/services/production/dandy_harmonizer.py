from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence

from .rhythm import RhythmState


class DandyHarmonizer:
    """
    Orchestrates Phil (expander) and Jim (filter) turn-taking.
    Handles pacing, wait-what injections, and segment boundaries.
    """

    def __init__(self, phil_skg, jim_skg):
        self.phil = phil_skg
        self.jim = jim_skg
        self.segment_counter = 0

    def generate_segment(self, topic: str, context: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        Produce a single conversational segment:
          Phil opener -> Jim response -> Phil expansion -> Jim compression
        """
        context = dict(context or {})
        context.setdefault("current_topic", topic)
        rhythm = RhythmState.from_context(context)
        context["rhythm"] = rhythm.to_dict()
        context["interaction_tempo"] = rhythm.interaction_tempo
        context["cognitive_intensity"] = rhythm.cognitive_intensity
        context["verbosity"] = rhythm.verbosity
        context["timing_profile"] = "stretch" if rhythm.interaction_tempo == "slow" else "tight" if rhythm.interaction_tempo == "fast" else "balanced"
        exchanges: List[Dict[str, Any]] = []
        self.segment_counter += 1

        # Opening: Phil starts, Jim grounds
        phil_open = self.phil.generate_response(context, conversation_stage="opening")
        phil_open["text"] = self._apply_rhythm_to_text(phil_open.get("text", ""), rhythm)
        exchanges.append(self._with_meta("phil", phil_open, "opening", rhythm))

        jim_first = self.jim.generate_response(context, phil_open["text"])
        jim_first["text"] = self._apply_rhythm_to_text(jim_first.get("text", ""), rhythm)
        exchanges.append(self._with_meta("jim", jim_first, "response", rhythm))

        # Expansion / wait-what handled inside Phil state machine
        phil_expand = self.phil.generate_response(
            context,
            jim_first["text"],
            conversation_stage="expansion",
            jim_response=jim_first,
        )
        phil_expand["text"] = self._apply_rhythm_to_text(phil_expand.get("text", ""), rhythm)
        exchanges.append(self._with_meta("phil", phil_expand, "expansion", rhythm))

        # Jim compression
        jim_close = self.jim.generate_response(context, phil_expand["text"])
        jim_close["text"] = self._apply_rhythm_to_text(jim_close.get("text", ""), rhythm)
        exchanges.append(self._with_meta("jim", jim_close, "closure", rhythm))

        return exchanges

    def run_loop(self, topics: Sequence[str]) -> List[Dict[str, Any]]:
        """Generate a list of exchanges across multiple topics."""
        transcript: List[Dict[str, Any]] = []
        for topic in topics:
            transcript.extend(self.generate_segment(topic))
        return transcript

    def _with_meta(self, speaker: str, payload: Dict[str, Any], stage: str, rhythm: RhythmState) -> Dict[str, Any]:
        enriched = dict(payload)
        enriched.setdefault("speaker", speaker)
        enriched.setdefault("stage", stage)
        enriched.setdefault("timestamp", datetime.now().isoformat())
        enriched.setdefault("segment_index", self.segment_counter)
        enriched.setdefault("rhythm", rhythm.to_dict())
        enriched.setdefault("timing", "stretch" if rhythm.interaction_tempo == "slow" else "tight" if rhythm.interaction_tempo == "fast" else "balanced")
        return enriched

    def _apply_rhythm_to_text(self, text: str, rhythm: RhythmState) -> str:
        raw = str(text or "").strip()
        if not raw:
            return raw
        max_words = 42
        if rhythm.verbosity == "low" or rhythm.human_load >= 0.80:
            max_words = 24
        elif rhythm.human_load >= 0.70 or rhythm.cognitive_intensity == "light":
            max_words = 32
        elif rhythm.verbosity == "high":
            max_words = 56
        words = raw.split()
        if len(words) <= max_words:
            return raw
        return f"{' '.join(words[:max_words]).rstrip('.,;: ')}."
