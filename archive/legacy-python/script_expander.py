"""
script_expander.py — Script Length Expansion Engine
====================================================
Solves the CRITICAL failure where orchestrate_banter() produces ~6 lines
(~30 seconds) instead of the 300-500 lines needed for a 30-45 minute podcast.

This module takes ANY script (SKG output or seed) and extends it to hit
the target word count by generating additional Phil/Jim exchanges that
rotate through key_points while maintaining character voice.

Usage:
    from script_expander import ScriptExpander

    expander = ScriptExpander(words_per_minute=155)
    full_script = expander.expand(
        base_lines=skg_output,           # 6 lines from SKG
        key_points=key_points,           # From episode config
        topic=topic,                     # Episode topic
        target_minutes=40,               # Target duration
        existing_context=context,        # From context_builder
    )
    # full_script now has ~350-450 lines
"""

import logging
import random
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ── Expansion Templates — Phil (The Expander) ──
_PHIL_SEGUE_TEMPLATES = [
    "You ever think about how {point} connects to the bigger picture?",
    "Okay hear me out... what if {point} is actually the key to everything?",
    "I was messing with something related to {point} the other day, and it got me thinking...",
    "So I had this thought... {point}, which makes me think about where this is all heading.",
    "This might be dumb but... what if we're looking at {point} all wrong?",
    "What if the real story with {point} isn't what everyone's talking about?",
    "You know what nobody's discussing? {point}. And I think that's a mistake.",
    "I keep coming back to {point}. There's something there we haven't unpacked yet.",
    "Here's what keeps me up at night: {point}. Am I wrong to obsess over this?",
    "Let me play devil's advocate for a second. What if {point} is actually overrated?",
]

_PHIL_DEEPEN_TEMPLATES = [
    "And that connects to {related} because the same pattern shows up there too.",
    "Which makes me think... there's a version of this where {related} becomes the norm.",
    "But here's the thing — {related} proves this isn't just theory.",
    "Wait actually... I've seen {related} work in a completely different context.",
    "So then I started wondering... does {related} change the math entirely?",
    "And that's where {related} comes in. That's the piece most people miss.",
]

_PHIL_OPENERS = [
    "Welcome back to the Phil and Jim Dandy Show. Today we're digging into {topic}.",
    "Alright folks, Phil and Jim here. {topic} — let's get into it.",
    "Hey everyone, welcome to the show. Jim and I have been going back and forth on {topic}.",
]

# ── Expansion Templates — Jim (The Filter) ──
_JIM_CHALLENGE_TEMPLATES = [
    "Hold on... do you honestly think {point} holds up in the real world?",
    "Yeah but... {point} sounds good on paper. What about in practice?",
    "That doesn't make sense to me. If {point} is so great, why isn't everyone doing it?",
    "Who told you that? Because {point} feels like one of those things that works until it doesn't.",
    "Let me pump the brakes here. {point} — have you actually seen this work?",
    "I'm not convinced. {point} has been around for a while and it still hasn't caught on.",
    "Alright, I'll play along. But {point} better have some proof behind it.",
    "Phil, buddy, you're doing that thing again where you get excited before checking the foundation.",
]

_JIM_GROUND_TEMPLATES = [
    "Here's my question: what's the actual cost of {point}? Not the marketing version — the real cost.",
    "Look, I'm not saying {point} is useless. I'm saying show me the mechanism. How does it actually work?",
    "Laura would look at {point} and ask one question: does it make life easier or more complicated?",
    "I took apart enough toasters as a kid to know this: if you can't see how it works, be suspicious.",
    "The engineering might be solid. But engineering alone doesn't mean people need it.",
    "I've seen too many 'revolutionary' things end up in a drawer. {point} needs to prove it's different.",
]

_JIM_WISDOM_TEMPLATES = [
    "You know what my grandfather used to say? 'Just because you can, doesn't mean you should.'",
    "At the end of the day, it's a tool. It either saves you time or it doesn't.",
    "The best advice I ever got? If it runs on subscription, ask who really owns it.",
    "Laura sees the forest, I'm stuck on the bark. But sometimes the bark matters.",
    "Experience is what you get right after you need it. {point} will teach some hard lessons.",
    "The problem with new ideas isn't the idea — it's the people selling it who've never done the work.",
]

_JIM_CLOSERS = [
    "Alright, that's our take on {topic}. Phil said too much, I said just enough.",
    "And that wraps it up. If you got something out of this, tell a friend. If not... blame Phil.",
    "Thanks for spending time with us today. Remember: ideas are cheap, execution is everything.",
    "That's the show. Jim Dandy, Phil Dandy, signing off. Stay practical out there.",
]

# ── Transition phrases ──
_TRANSITIONS = [
    "Let's shift gears for a minute.",
    "Alright, moving on...",
    "That brings us to the next piece.",
    "Speaking of which...",
    "Let's talk about something related.",
    "Here's where it gets interesting.",
]


def _pick(templates: List[str]) -> str:
    return random.choice(templates)


def _format_template(template: str, context: Dict[str, str]) -> str:
    """Safe template formatting with fallback to context keys."""
    try:
        return template.format(**context)
    except KeyError as e:
        missing_key = str(e).strip("'")
        context[missing_key] = context.get("topic", "that")
        return template.format(**context)
    except Exception:
        return template


class ScriptExpander:
    """
    Expands a short script base into a full-length podcast script.

    Strategy:
      1. Take the SKG-generated base (typically 4-12 lines)
      2. Calculate how many additional lines needed for target duration
      3. Build segments around each key_point (4-6 exchanges each)
      4. Add transitions between segments
      5. Ensure Phil/Jim balance (~55/45 split)
      6. Return complete script
    """

    def __init__(self, words_per_minute: int = 155):
        self.words_per_minute = words_per_minute
        # Each exchange pair (Phil + Jim) is roughly 25-35 words
        self.words_per_exchange = 30

    def expand(
        self,
        base_lines: List[Dict[str, Any]],
        key_points: List[str],
        topic: str,
        target_minutes: int = 40,
        title: str = "",
        existing_context: Optional[Dict[str, Any]] = None,
        min_exchanges_per_point: int = 3,
        max_exchanges_per_point: int = 6,
    ) -> List[Dict[str, Any]]:
        """
        Expand base_lines to reach target_minutes duration.

        Args:
            base_lines: Initial lines from SKG generation (may be empty)
            key_points: Episode key points to build segments around
            topic: Episode topic
            target_minutes: Target podcast length (30-45 typical)
            title: Episode title
            existing_context: Optional context dict from context_builder
            min_exchanges_per_point: Minimum Phil+Jim exchanges per key_point
            max_exchanges_per_point: Maximum Phil+Jim exchanges per key_point

        Returns:
            Complete script with enough lines for target duration
        """
        target_words = target_minutes * self.words_per_minute
        current_words = sum(
            len(str(line.get("text", line.get("line", ""))).split())
            for line in base_lines
        )

        logger.info(
            "[ScriptExpander] Starting: %d words / %d target (%.1f%%)",
            current_words, target_words, (current_words / max(target_words, 1)) * 100,
        )

        # Start with base lines, filtering out any with [unknown]
        script: List[Dict[str, Any]] = []
        for line in base_lines:
            text = str(line.get("text", line.get("line", "")))
            if "[unknown]" not in text.lower():
                script.append(dict(line))
            else:
                logger.warning("[ScriptExpander] Filtered line with [unknown]: %s", text[:60])

        # ── If base is empty or nearly empty, start fresh ──
        if len(script) < 2:
            script = self._generate_opening(topic, title)
            current_words = sum(len(line["text"].split()) for line in script)

        # ── Build context for template filling ──
        ctx = self._build_expansion_context(topic, key_points, title, existing_context)

        # ── Generate segments for each key_point ──
        segment_idx = 0
        round_robin = 0  # Track which template variant to use

        while current_words < target_words and segment_idx < 200:  # Safety limit
            kp_idx = segment_idx % max(len(key_points), 1)
            point = key_points[kp_idx] if key_points else topic

            ctx["point"] = point
            ctx["related"] = key_points[(kp_idx + 1) % max(len(key_points), 1)] if len(key_points) > 1 else point

            # Determine how many exchanges for this segment (vary it)
            exchanges = random.randint(min_exchanges_per_point, max_exchanges_per_point)

            # Add transition between segments (except first)
            if segment_idx > 0 and random.random() > 0.3:
                transition = _pick(_TRANSITIONS)
                script.append({
                    "speaker": "host",
                    "text": transition,
                    "emotion": "neutral",
                    "pause_after": 0.3,
                    "line_number": len(script) + 1,
                    "generated_by": "expander",
                })
                current_words += len(transition.split())

            # Generate exchanges
            for ex in range(exchanges):
                if current_words >= target_words:
                    break

                # Alternate who starts (mostly Phil)
                phil_first = (round_robin % 2 == 0) or random.random() > 0.3
                round_robin += 1

                if phil_first:
                    # Phil opens with a segue or deepen
                    if ex == 0:
                        phil_text = _format_template(_pick(_PHIL_SEGUE_TEMPLATES), ctx)
                    else:
                        phil_text = _format_template(_pick(_PHIL_DEEPEN_TEMPLATES), ctx)

                    script.append({
                        "speaker": "phil",
                        "text": phil_text,
                        "emotion": "excited",
                        "pause_after": 0.35,
                        "line_number": len(script) + 1,
                        "generated_by": "expander",
                    })
                    current_words += len(phil_text.split())

                    # Jim responds
                    if random.random() > 0.4:
                        jim_text = _format_template(_pick(_JIM_CHALLENGE_TEMPLATES), ctx)
                        jim_emotion = "skeptical"
                    elif random.random() > 0.5:
                        jim_text = _format_template(_pick(_JIM_GROUND_TEMPLATES), ctx)
                        jim_emotion = "pragmatic"
                    else:
                        jim_text = _format_template(_pick(_JIM_WISDOM_TEMPLATES), ctx)
                        jim_emotion = "measured"

                    script.append({
                        "speaker": "jim",
                        "text": jim_text,
                        "emotion": jim_emotion,
                        "pause_after": 0.55,
                        "line_number": len(script) + 1,
                        "generated_by": "expander",
                    })
                    current_words += len(jim_text.split())
                else:
                    # Jim opens (variation)
                    jim_text = _format_template(_pick(_JIM_GROUND_TEMPLATES), ctx)
                    script.append({
                        "speaker": "jim",
                        "text": jim_text,
                        "emotion": "pragmatic",
                        "pause_after": 0.55,
                        "line_number": len(script) + 1,
                        "generated_by": "expander",
                    })
                    current_words += len(jim_text.split())

                    phil_text = _format_template(_pick(_PHIL_SEGUE_TEMPLATES), ctx)
                    script.append({
                        "speaker": "phil",
                        "text": phil_text,
                        "emotion": "excited",
                        "pause_after": 0.35,
                        "line_number": len(script) + 1,
                        "generated_by": "expander",
                    })
                    current_words += len(phil_text.split())

            segment_idx += 1

        # ── Add closing ──
        if current_words < target_words * 1.05:  # Don't add closing if already over
            closing = self._generate_closing(topic, title)
            for line in closing:
                script.append({
                    **line,
                    "line_number": len(script) + 1,
                    "generated_by": "expander",
                })
                current_words += len(line["text"].split())

        final_words = sum(len(line["text"].split()) for line in script)
        logger.info(
            "[ScriptExpander] Complete: %d lines, %d words (target: %d, %.1f%%)",
            len(script), final_words, target_words, (final_words / max(target_words, 1)) * 100,
        )

        return script

    def _generate_opening(self, topic: str, title: str) -> List[Dict[str, Any]]:
        """Generate a show opening when SKG base is empty."""
        ctx = {"topic": topic, "title": title or topic}
        lines = [
            {
                "speaker": "phil",
                "text": _format_template(_pick(_PHIL_OPENERS), ctx),
                "emotion": "enthusiastic",
                "pause_after": 0.5,
                "line_number": 1,
                "generated_by": "expander",
            },
            {
                "speaker": "jim",
                "text": f"That is the topic, and we are going to keep it practical, useful, and worth your time.",
                "emotion": "measured",
                "pause_after": 0.5,
                "line_number": 2,
                "generated_by": "expander",
            },
        ]
        return lines

    def _generate_closing(self, topic: str, title: str) -> List[Dict[str, Any]]:
        """Generate a show closing."""
        ctx = {"topic": topic, "title": title or topic}
        jim_close = _format_template(_pick(_JIM_CLOSERS), ctx)
        return [
            {
                "speaker": "jim",
                "text": jim_close,
                "emotion": "warm",
                "pause_after": 0.5,
                "line_number": 0,  # Will be reassigned
                "generated_by": "expander",
            },
            {
                "speaker": "phil",
                "text": "And remember — everything links to something else. You just have not seen it yet.",
                "emotion": "warm",
                "pause_after": 0.5,
                "line_number": 0,
                "generated_by": "expander",
            },
        ]

    def _build_expansion_context(
        self,
        topic: str,
        key_points: List[str],
        title: str,
        existing_context: Optional[Dict[str, Any]],
    ) -> Dict[str, str]:
        """Build a string-only context dict for template formatting."""
        if existing_context:
            # Convert to plain strings (filter out non-string values)
            ctx = {}
            for k, v in existing_context.items():
                if isinstance(v, str):
                    ctx[k] = v
                elif isinstance(v, (list, tuple)) and len(v) > 0:
                    ctx[k] = str(v[0]) if isinstance(v[0], str) else str(v)
                else:
                    ctx[k] = str(v)
            return ctx

        # Minimal context if none provided
        return {
            "topic": topic,
            "title": title or topic,
            "point": topic,
            "related": topic,
        }


def expand_script(
    base_lines: List[Dict[str, Any]],
    key_points: List[str],
    topic: str,
    target_minutes: int = 40,
    **kwargs: Any,
) -> List[Dict[str, Any]]:
    """One-liner convenience function."""
    expander = ScriptExpander()
    return expander.expand(
        base_lines=base_lines,
        key_points=key_points,
        topic=topic,
        target_minutes=target_minutes,
        **kwargs,
    )
