"""
script_seed.py — Full-Length Seed Script Generator
===================================================
Enhanced replacement that produces complete 30-45 minute podcast scripts.

The original generated ~14 lines (~1.3 minutes). This version:
  - Accepts target_duration_minutes and scales output accordingly
  - Rotates through key_points with varied dialogue patterns
  - Includes transitions, audience engagement, and proper closing
  - Maintains Phil/Jim voice characteristics throughout

Usage:
    from script_seed import generate_seed_script

    script = generate_seed_script({
        "topic": "artificial intelligence",
        "title": "The AI Revolution",
        "key_points": ["Point 1", "Point 2", "Point 3"],
        "target_duration_minutes": 40,
    })
"""

import logging
import random
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

WORDS_PER_MINUTE = 155
AVG_WORDS_PER_LINE = 15

# ── Phil voice templates (The Expander) ──
_PHIL_INTROS = [
    "Welcome back to the Phil and Jim Dandy Show. Today we are digging into {title}.",
    "Hey everyone, Phil and Jim here. {title} — let's talk about it.",
    "Alright folks, welcome to the show. Today Jim and I are taking on {title}.",
    "Good to have you with us. {title} is on the table today, and Phil is... well, Phil about it.",
]

_PHIL_POINT_TEMPLATES = [
    "So here's what I keep thinking about: {point}. The energy around this is real, and I think people are starting to notice.",
    "You ever think about {point}? Like, really sit with it? Because the implications are bigger than they first appear.",
    "Okay hear me out... what if {point} is actually the foundation for everything else we're discussing?",
    "I was reading something about {point} the other day, and it clicked. This is where the shift happens.",
    "What strikes me about {point} is how connected it is to everything else. Nothing happens in isolation.",
    "Here's my take on {point}: we're still in the early innings. Most people don't see what's coming.",
    "The thing about {point} that keeps me up at night? It's moving faster than the conversation around it.",
    "You know what nobody's saying about {point}? That it might actually work. Like, really work.",
]

_PHIL_CONNECTOR_TEMPLATES = [
    "And that naturally brings us to {next_point}. You can't talk about one without the other.",
    "Which connects directly to {next_point}. See the thread? It's all woven together.",
    "But here's where it intersects with {next_point} — and this is what most people miss.",
    "Speaking of which... {next_point}. I know, it seems unrelated. It's not.",
    "And if you're following the logic, {next_point} is the next domino.",
]

_PHIL_EXPLORATORY = [
    "I keep wondering... are we asking the right questions here?",
    "What if the real opportunity isn't where everyone's looking?",
    "There's a version of this conversation where we completely change direction. Should we?",
    "I don't have the answer. But I think the question itself is worth something.",
    "Sometimes the dumbest sounding idea is the one that actually works.",
]

# ── Jim voice templates (The Filter) ──
_JIM_INTROS = [
    "That is the topic, and we are going to keep it practical, useful, and worth your time.",
    "Fair warning: Phil's going to get excited. I'm going to ask hard questions. That's the deal.",
    "Let's see if this holds up. Good ideas are easy. Execution is where things fall apart.",
]

_JIM_RESPONSE_TEMPLATES = [
    "Hold on... {point} sounds good when you say it like that. But I've heard this before. What makes it different this time?",
    "Yeah but... {point} — where's the proof? Show me someone who's actually doing this successfully.",
    "That doesn't make sense to me. If {point} is so obvious, why isn't everyone already doing it?",
    "Who told you that? Because the people selling {point} usually have something to gain from your enthusiasm.",
    "Look, I'm not against {point}. I'm against pretending it's simpler than it is. What's the real cost?",
    "Here's my question: does {point} actually help a regular person, or is this just for people with money and time?",
    "Laura would hear {point} and ask one thing: does it make Tuesday easier? If not, what's the point?",
    "I'll believe {point} when I see it working in a place that doesn't have a PR team.",
]

_JIM_GROUNDING_TEMPLATES = [
    "Let's pump the brakes. Before we get carried away, what's the downside?",
    "Experience is what you get right after you need it. Someone's going to learn hard lessons here.",
    "The tool isn't the solution. The solution is knowing what you're actually trying to fix.",
    "My grandfather had a saying: just because you can, doesn't mean you should. Applies here.",
    "Here's what I know for sure: complexity sells, but simplicity actually works.",
    "At the end of the day, it's either useful or it's not. Everything else is marketing.",
]

_JIM_TRANSITIONS = [
    "Alright, let's look at this from a different angle.",
    "Before we move on, I want to poke at that a little more.",
    "That's one side of it. Here's the other.",
    "Fair point. But what about the practical side?",
]

# ── Audience engagement ──
_AUDIENCE_HOOKS = [
    "If you're listening and you've dealt with this, you know exactly what I mean.",
    "Some of you are shaking your heads right now. I get it.",
    "Here's a question for everyone driving right now: when's the last time this actually worked for you?",
    "Think about your own situation. Does this match what you're seeing?",
]

# ── Outro ──
_JIM_OUTROS = [
    "And that wraps up our take on {title}. Phil talked too much. I talked just enough.",
    "That's the show for today. If you got something out of this, tell someone. If not... well, we tried.",
    "Thanks for spending time with us. Remember: ideas are cheap. Execution is everything.",
    "Signing off. Jim Dandy, Phil Dandy. Stay practical out there.",
]

_PHIL_OUTROS = [
    "And remember — everything links to something else. You just haven't seen it yet.",
    "Keep connecting the dots. We'll be back next time.",
    "The world's more connected than it looks. Keep looking.",
]


def _pick(options: List[str]) -> str:
    return random.choice(options)


def generate_seed_script(config: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Generate a FULL-LENGTH seed script based on episode config.

    Args:
        config: Dict with keys:
            - topic: str
            - title: str (optional, defaults to topic.title())
            - key_points: List[str]
            - target_duration_minutes: int (optional, default 40)
            - description: str (optional, used for extra context)

    Returns:
        List of script line dicts with speaker, text, emotion, pause_after, line_number
    """
    topic = config.get("topic", "the current topic")
    title = config.get("title") or topic.replace("_", " ").title()
    key_points = [kp for kp in config.get("key_points", []) if kp]
    target_minutes = int(config.get("target_duration_minutes", config.get("target_duration", 2400)) // 60) if config.get("target_duration_minutes") or config.get("target_duration") else 40
    if target_minutes < 1:
        target_minutes = 40

    target_words = target_minutes * WORDS_PER_MINUTE
    script: List[Dict[str, Any]] = []
    line_num = 0
    word_count = 0

    def add_line(speaker: str, text: str, emotion: str, pause: float = 0.5) -> None:
        nonlocal line_num, word_count
        line_num += 1
        word_count += len(text.split())
        script.append({
            "speaker": speaker,
            "text": text,
            "emotion": emotion,
            "pause_after": pause,
            "line_number": line_num,
        })

    # ── INTRO (2-3 lines) ──
    intro_phil = _pick(_PHIL_INTROS).format(title=title)
    add_line("phil", intro_phil, "enthusiastic", 0.5)

    intro_jim = _pick(_JIM_INTROS)
    add_line("jim", intro_jim, "measured", 0.5)

    # ── MAIN SEGMENTS ──
    # Each key_point gets multiple exchange cycles
    cycles_per_point = max(2, min(6, target_minutes // max(len(key_points) * 3, 1)))

    for kp_idx, point in enumerate(key_points):
        readable = point.replace("_", " ")
        next_point = key_points[(kp_idx + 1) % len(key_points)].replace("_", " ") if key_points else readable

        # Transition between key points (except first)
        if kp_idx > 0:
            connector = _pick(_PHIL_CONNECTOR_TEMPLATES).format(next_point=next_point)
            add_line("phil", connector, "curious", 0.4)

        # Multiple exchange cycles per key point
        for cycle in range(cycles_per_point):
            # Phil introduces or deepens
            phil_text = _pick(_PHIL_POINT_TEMPLATES).format(point=readable)
            add_line("phil", phil_text, "excited", 0.35)

            # Jim challenges or grounds (vary the pattern)
            if cycle % 3 == 0:
                jim_text = _pick(_JIM_RESPONSE_TEMPLATES).format(point=readable)
                jim_emotion = "skeptical"
                pause = 0.55
            elif cycle % 3 == 1:
                jim_text = _pick(_JIM_GROUNDING_TEMPLATES)
                jim_emotion = "pragmatic"
                pause = 0.6
            else:
                jim_text = _pick(_JIM_TRANSITIONS)
                jim_emotion = "measured"
                pause = 0.5

            add_line("jim", jim_text, jim_emotion, pause)

            # Phil pushes back or explores (every other cycle)
            if cycle % 2 == 0:
                phil_follow = _pick(_PHIL_EXPLORATORY)
                add_line("phil", phil_follow, "curious", 0.4)

            # Audience engagement hook (first cycle only per point)
            if cycle == 0:
                hook = _pick(_AUDIENCE_HOOKS)
                add_line("host", hook, "neutral", 0.3)

            # Check if we've hit target
            if word_count >= target_words:
                break

        if word_count >= target_words:
            break

    # ── If still short, add filler exchanges ──
    filler_rounds = 0
    while word_count < target_words and filler_rounds < 100:
        filler_rounds += 1
        point = random.choice(key_points).replace("_", " ") if key_points else topic

        phil_filler = _pick(_PHIL_EXPLORATORY)
        add_line("phil", phil_filler, "curious", 0.35)

        jim_filler = _pick(_JIM_GROUNDING_TEMPLATES)
        add_line("jim", jim_filler, "pragmatic", 0.55)

    # ── OUTRO (2-3 lines) ──
    if word_count < target_words * 1.1:  # Only add outro if not way over
        jim_outro = _pick(_JIM_OUTROS).format(title=title)
        add_line("jim", jim_outro, "warm", 0.5)

        phil_outro = _pick(_PHIL_OUTROS)
        add_line("phil", phil_outro, "warm", 0.5)

    logger.info(
        "[SeedScript] Generated %d lines, %d words (target: %d min = %d words)",
        len(script), word_count, target_minutes, target_words,
    )

    return script


# ── Backward-compatible alias ──
def generate_fallback_script(config: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Alias for generate_seed_script for clarity in fallback paths."""
    return generate_seed_script(config)
