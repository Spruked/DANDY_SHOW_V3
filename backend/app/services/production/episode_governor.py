"""Bounded episode orchestration for the Phil/Jim dialogue writer.

The governor owns turn order and shared conversation state. Character SKGs
remain responsible for their own identity and constraints; llama.cpp only
renders the supplied directive as dialogue.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class TurnDirective:
    speaker: str
    stage: str
    intent: str
    tone: str
    must_avoid: List[str] = field(default_factory=list)
    must_include: List[str] = field(default_factory=list)
    max_words: int = 80
    momentum: str = "forward"
    friction: str = "light"
    constraints: List[str] = field(default_factory=list)
    context_snapshot: str = ""

    def to_prompt_block(self) -> str:
        """Return only directive state; fallback text is deliberately excluded."""
        avoid = ", ".join(self.must_avoid) or "none"
        include = ", ".join(self.must_include) or "none"
        constraints = "; ".join(self.constraints) or "finished thought"
        return (
            f"{self.speaker} TURN DIRECTIVE:\n"
            f"- stage: {self.stage}\n"
            f"- intent: {self.intent}\n"
            f"- tone: {self.tone}\n"
            f"- must avoid: {avoid}\n"
            f"- must include: {include}\n"
            f"- max words: {self.max_words}\n"
            f"- momentum: {self.momentum}\n"
            f"- friction: {self.friction}\n"
            f"- constraints: {constraints}\n"
            f"- context snapshot: {self.context_snapshot or '(opening)'}"
        )


class EpisodeGovernor:
    """Coordinate character SKGs without merging their state machines."""

    def __init__(self, phil_skg: Any = None, jim_skg: Any = None, *, history: Optional[List[str]] = None):
        self.phil_skg = phil_skg
        self.jim_skg = jim_skg
        self.history = list(history or [])
        self.covered_concepts: List[str] = []
        self.open_threads: List[str] = []
        self.turn_index = 0

    def plan_next_turn(self, *, stage: str, beat_number: int, beat_description: str) -> TurnDirective:
        speaker = "Phil" if self.turn_index % 2 == 0 else "Jim"
        character = self.phil_skg if speaker == "Phil" else self.jim_skg
        core = getattr(character, "CORE_PERSONALITY", {}) if character is not None else {}
        if speaker == "Phil":
            intent = "open or expand the assigned beat with a fresh connection"
            tone = "curious, connective, sincere"
            max_words = 85
            friction = "invite Jim to test the idea"
        else:
            intent = "test, ground, or challenge the assigned beat"
            tone = "practical, dry, protective"
            max_words = 65
            friction = "challenge one assumption without restarting"
        character_avoid = []
        if speaker == "Phil":
            character_avoid = list((core.get("behavioral_constraints") or {}).get("must_never") or [])
        else:
            character_avoid = list((core.get("character_lock") or {}).get("wrong_if") or [])
        return TurnDirective(
            speaker=speaker,
            stage=stage,
            intent=intent,
            tone=tone,
            must_avoid=(self.covered_concepts[-6:] + character_avoid[:4]),
            must_include=[f"beat {beat_number}: {beat_description}"],
            max_words=max_words,
            friction=friction,
            constraints=["speak only for the assigned character", "advance the beat", "do not summarize prior turns"],
            context_snapshot=" | ".join(self.history[-2:]),
        )

    def validate_completion(self, directive: TurnDirective, text: str) -> bool:
        cleaned = str(text or "").strip()
        if not cleaned or len(cleaned.split()) > directive.max_words * 2:
            return False
        lowered = cleaned.lower()
        return not any(marker in lowered for marker in ("<think>", "analysis:", "fallback_text"))

    def record_turn(self, speaker: str, text: str, *, beat_number: Optional[int] = None) -> None:
        cleaned = " ".join(str(text or "").split())
        if not cleaned:
            return
        self.history.append(f"{speaker.upper()}: {cleaned}")
        self.covered_concepts.append(cleaned[:120])
        self.covered_concepts = self.covered_concepts[-24:]
        self.turn_index += 1

    def state_snapshot(self) -> Dict[str, Any]:
        return {
            "turn_index": self.turn_index,
            "covered_concepts": list(self.covered_concepts[-12:]),
            "open_threads": list(self.open_threads),
            "prior_exchange": self.history[-2:],
        }
