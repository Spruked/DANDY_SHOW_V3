"""
script_expander.py — Progressive Script Expansion Engine
==========================================================
Extends short SKG output to target duration with non-repetitive dialogue.
Uses the same progressive phase system and template pools as script_seed.py.

Usage:
    from script_expander import ScriptExpander
    expander = ScriptExpander()
    full_script = expander.expand(
        base_lines=skg_output,
        key_points=key_points,
        topic=topic,
        target_minutes=40,
    )
"""

import logging
import random
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════
# TEMPLATES — Every template includes {point} for context variation
# ═══════════════════════════════════════════════════════════════════════════

_PHIL_OPEN = [
    "So here is what I keep thinking about: {point}. The energy around this is real.",
    "You ever think about {point}? The implications are bigger than they first appear.",
    "Okay hear me out... what if {point} is actually the key to everything?",
    "I was reading about {point} and it clicked. This is where the shift happens.",
    "What strikes me about {point} is how connected it is to everything else.",
    "Here is my take on {point}: we are still in the early innings.",
    "The thing about {point} that keeps me up? It is moving faster than the conversation.",
    "You know what nobody is saying about {point}? That it might actually work.",
    "I keep coming back to {point}. There is something we have not unpacked.",
    "Here is what caught my attention about {point}: it changes the math on everything.",
    "Let me play devil's advocate. What if {point} is overrated?",
    "I talked to someone about {point} last week. They said something that stuck.",
    "When I first encountered {point}, I did not think much of it. Now I cannot stop.",
    "The conversation around {point} feels different this time. I am trying to figure out why.",
]

_PHIL_DEEPEN = [
    "And that connects to {related} because the same pattern shows up there.",
    "Which makes me think... {related} becomes the norm in a version of this.",
    "But here is the thing — {related} proves this is not just theory.",
    "Wait actually... I have seen {related} work in a different context.",
    "So then I started wondering... does {related} change the math entirely?",
    "And that is where {related} comes in. That is the piece most people miss.",
    "Here is what I mean. Look at {related} — same dynamic, different arena.",
    "It is like {related}. You see the parallel?",
    "That is what happened with {related}. History rhymes.",
    "The question is not whether {point} works. It is whether we are ready for what follows.",
    "If you pull the thread on {point}, you end up at {related}. Every time.",
    "What people miss about {point} is that it is not the endgame. It is the opening move.",
]

_PHIL_PUSHBACK = [
    "Okay, fair pushback. But {point} is not about the hype. It is about the underlying shift.",
    "I hear you, and that skepticism is healthy. But {point} matters because it changes behavior.",
    "Yeah, a lot of this is overblown. But strip away the marketing and {point} still has a foundation.",
    "I am not saying it is perfect. I am saying it is worth understanding. {point} has legs.",
    "You are right to be cautious. But I have seen enough to know {point} is not just noise.",
    "Half of what gets written about {point} is garbage. But the other half? That is where the signal lives.",
    "I am not defending the hype cycle. I am saying: underneath, {point} has mechanical truth.",
    "Let me reframe. I am excited about {point} because it solves something people actually feel.",
    "I get the eye roll. But dig into {point} with an open mind and there is something there.",
    "Skepticism is a tool, not a destination. At some point you have to engage with {point} on its merits.",
]

_PHIL_WONDER = [
    "I keep wondering... are we even asking the right questions about {point}?",
    "What if the real opportunity with {point} is not where everyone is looking?",
    "There is a version of this conversation about {point} where we go completely different direction.",
    "I do not have the answer about {point}. But the question itself is worth something.",
    "Sometimes the idea that sounds dumb at first about {point} is the one that works.",
    "What if we are thinking about {point} backwards? What if the constraint is the feature?",
    "Here is a thought experiment: what if {point} had launched ten years ago?",
    "The most interesting thing about {point} is not what it does. It is what it makes possible.",
    "What gets lost with {point}? The human side. Behind every data point, someone decided.",
    "What if the real story about {point} is not about the technology? What if it is about the people?",
    "I keep thinking about the second-order effects of {point}. We are not talking about those enough.",
    "Here is what keeps me up: {point} is going to change things whether we are ready or not.",
]

_PHIL_CONNECT = [
    "Remember {earlier_point}? This is the other side of that coin with {point}.",
    "Going back to what you said about {earlier_point}... {point} validates your skepticism.",
    "{earlier_point} and {point} are the same story told from different angles.",
    "If you put {earlier_point} next to {point}, a pattern emerges. Not an accident.",
    "Your pushback on {earlier_point}? Fair. And it applies to {point} too.",
    "This connects back to {earlier_point} in a way I did not expect. The loop closes with {point}.",
    "Jim, remember your point about {earlier_point}? I think {point} is the test case.",
    "Everything we said about {earlier_point}? Multiply by ten. That is {point} right now.",
]

_PHIL_SYNTHESIZE = [
    "Let me land this plane. {point} is not one thing. It is a stack of things.",
    "The opportunity around {point} is real, the execution is hard, and the hype helps nobody.",
    "Here is what I am walking away with: {point} is a tool. Tools do not fix problems. People do.",
    "We are early, we are uncertain, and that is exactly why {point} is worth paying attention to.",
    "Every big shift looked like {point} at first. Confusing, overhyped, slightly terrifying.",
    "I do not know where {title} lands. But pretending {point} does not exist is not an option.",
    "If there is one thing I hope people remember: {point} is not magic. It is mechanics.",
    "The people who figure out {point} first will have an advantage. Not because they are smarter. Because they paid attention.",
]

_JIM_CHALLENGE = [
    "Hold on... {point} sounds good. But I have heard this before. What makes it different?",
    "Yeah but... {point} — where is the proof? Show me someone doing this successfully.",
    "If {point} is so obvious, why is not everyone doing it?",
    "Who told you that? The people selling {point} have something to gain.",
    "I am not against {point}. I am against pretending it is simpler than it is.",
    "Does {point} help a regular person, or just people with money and time?",
    "I will believe {point} when I see it where there is no PR team.",
    "You are getting excited about {point} before checking the foundation again.",
    "Too many 'revolutionary' things end up in a drawer. {point} needs to prove different.",
    "Is {point} real or just well-marketed? That is what I am trying to figure out.",
    "The enthusiasm about {point} is contagious. But enthusiasm is not evidence.",
    "Here is what I want to know about {point}: who loses? Because somebody always loses.",
    "I am willing to be convinced about {point}. But I need more than a promise and a slide deck.",
    "Call me old-fashioned, but {point} needs to survive a Tuesday afternoon before I trust it.",
    "Before I buy into {point}, I want to see the receipts. Not the projections. The receipts.",
]

_JIM_GROUND = [
    "Let us pump the brakes on {point}. What is the downside?",
    "Experience with {point} is what you get right after you need it. Hard lessons coming.",
    "The tool is not the solution. Knowing what you are fixing with {point} is the solution.",
    "At the end of the day, {point} is either useful or it is not. Everything else is marketing.",
    "Just because you can do {point}, does not mean you should.",
    "Complexity sells, but simplicity around {point} actually works.",
    "I am not saying no to {point}. I am saying prove it. Show me the mechanism.",
    "Does {point} make Tuesday easier? If not, what is the point?",
    "The engineering behind {point} might be solid. That does not mean people need it.",
    "If you cannot see how {point} works, be suspicious.",
    "I want {point} to work. I am just not pretending the obstacles do not exist.",
    "The best idea about {point} does not matter if the user does not understand it.",
    "Can you explain {point} to someone who does not care? If not, it is not ready.",
]

_JIM_WISDOM = [
    "My grandfather used to say: just because you can, does not mean you should. Right about {point}.",
    "I have seen the pattern around {point}. The promise arrives first. The bill arrives later.",
    "What actually lasts with {point} does not need a hype cycle.",
    "I am counting the cost of {point}. And the cost is higher than most people admit.",
    "The boring stuff works with {point}. The unsexy, daily, show-up-and-do-it stuff.",
    "The problem with {point} is the people selling it who have never done the work.",
    "My kid tried {point}. He gets excited, hits a wall, learns. That is the real process.",
    "Here is my honest read on {point}: interesting does not pay the bills. Useful does.",
    "Most people do not need {point}. They need the basics done better.",
    "The people who need {point} are not writing articles about it. That should tell you something.",
    "{point} might be solving a problem that only exists because we created it.",
    "Your time matters. Do not give it away to {point} until it has earned it.",
    "I have seen {point} come and go in different packaging. The wrapper changes. The reality stays.",
    "Most people will use {point} wrong, blame the tool, and never look in the mirror.",
    "The difference between {point} working and failing is usually the person using it.",
]

_JIM_CONCEDE = [
    "Okay. You might have something with {point}. The foundation is stronger than I thought.",
    "I will meet you halfway. {point} has potential. Potential and performance are different.",
    "I have been thinking about {point} differently. It is not the solution. But it might be part of one.",
    "Fair point about {point}. That changes how I look at it. Not all the way. But some.",
    "I came into {point} skeptical. I am still skeptical. But less than I was.",
    "You got me on {point}. Better argument than I expected. It deserves more credit.",
    "I still have questions about {point}. But you have made me think differently. Not easy to do.",
    "Here is where I land: {point} is real. The question is whether we are mature enough.",
    "I am not ready to cheerlead {point}. But I am done dismissing it. That is progress.",
    "Okay, Phil. You win this round on {point}. Do not let it go to your head.",
]

_JIM_TRANSITION = [
    "Alright, let us look at {point} from a different angle.",
    "Before we move on from {point}, I want to poke at that more.",
    "That is one side of {point}. Here is the other.",
    "Fair point about {point}. But what about the practical side?",
    "I hear you on {point}. Now let me flip it.",
    "Let me ask you this about {point}...",
    "Consider the opposite of {point} for a second.",
    "I want to come back to something about {point} earlier.",
    "If {point} works as advertised, what happens next?",
    "That is the optimistic read on {point}. Now give me the pessimistic one.",
    "I want to believe in {point}. Convince me one more time.",
    "Who is actually winning with {point}? That is what I keep asking.",
    "Let me be the devil's advocate on {point} for one more minute.",
    "I think we are talking around the real issue with {point}. Let me name it.",
    "What would change my mind about {point}? One concrete example. Just one.",
]

_JIM_SYNTHESIZE = [
    "If I am being honest — and I always am — {point} is a mixed bag. And that is okay.",
    "Do not bet the farm on {point}. But do not ignore it either. Stay skeptical. That is the job.",
    "Your time matters. Do not give it to {point} until it has earned it.",
    "Stay curious about {point} but keep your wallet closed until you see proof.",
    "You are the one who lives with {point}. Not the people selling it.",
    "Hope is not a strategy. Neither is fear. What you need about {point} is clarity.",
    "My grandfather would have looked at {point} and said: expensive. But he also would have said: wait and see.",
]

_HOST_HOOKS = [
    "If you have dealt with {point}, you know exactly what I mean.",
    "Some of you are shaking your heads about {point}. I get it.",
    "Think about your own situation with {point}. Does this match what you are seeing?",
    "If this conversation about {point} is resonating, you are not alone.",
    "When is the last time {point} actually worked for you?",
]

_TRANSITION_PHRASES = [
    "Let us shift gears for a minute.",
    "That brings us to the next piece.",
    "Speaking of which...",
    "Here is where it gets interesting.",
    "Let me connect a dot for you.",
    "This next part ties into everything we just said.",
    "Now here is something that follows naturally.",
    "Let me pivot for a moment.",
    "This is the part where things get real.",
    "If you have been following along, this next piece is crucial.",
    "I want to build on what we just covered.",
    "The thread continues here.",
    "Let me add another layer to this.",
    "Now for the piece that pulls it together.",
    "Here is the connection most people miss.",
]

_PERSONAL_STORY_LINES = {
    "open": [
        {"speaker": "phil", "text": "Happy Toes begins as a father trying to reach his daughter through words.", "emotion": "warm", "pause_after": 0.35},
        {"speaker": "jim", "text": "That is the part to keep centered. Before the literary experiment, there is a daughter and a father.", "emotion": "measured", "pause_after": 0.55},
    ],
    "deepen": [
        {"speaker": "phil", "text": "The book matters because it lets one private poem echo through many different voices.", "emotion": "curious", "pause_after": 0.35},
        {"speaker": "jim", "text": "And if those voices work, they should make the original feeling clearer, not bury it.", "emotion": "pragmatic", "pause_after": 0.55},
    ],
    "pushback": [
        {"speaker": "jim", "text": "The practical test is whether the reader still feels the love underneath the structure.", "emotion": "skeptical", "pause_after": 0.55},
        {"speaker": "phil", "text": "Right. The reinterpretations only matter if they protect the emotional core of the poem.", "emotion": "warm", "pause_after": 0.4},
    ],
    "wonder": [
        {"speaker": "phil", "text": "What stays with me is how a simple poem can become a record of presence across distance.", "emotion": "curious", "pause_after": 0.4},
        {"speaker": "jim", "text": "That is legacy in plain language: proof that someone was thinking about you.", "emotion": "measured", "pause_after": 0.6},
    ],
    "connect": [
        {"speaker": "phil", "text": "The literary voices become a kind of jury, each one testing a different side of the same feeling.", "emotion": "warm", "pause_after": 0.35},
        {"speaker": "jim", "text": "As long as the verdict comes back to Abby, fatherhood, and the original poem, it works.", "emotion": "warm", "pause_after": 0.5},
    ],
    "synthesize": [
        {"speaker": "phil", "text": "The heart of Happy Toes is not complexity. It is love finding another form.", "emotion": "warm", "pause_after": 0.4},
        {"speaker": "jim", "text": "Keep the origin honest, and the larger book has something real to stand on.", "emotion": "measured", "pause_after": 0.55},
    ],
}


def _is_bad_point(text: str, topic: str) -> bool:
    if not text:
        return True
    if len(text) > 60:
        return True
    if len(text.split()) > 8:
        return True
    if topic.lower() in text.lower():
        return True
    return False


def _is_personal_story_context(topic, key_points, title="", existing_context=None, kwargs=None) -> bool:
    if existing_context and existing_context.get("domain") == "personal_story":
        return True
    if kwargs and kwargs.get("domain") == "personal_story":
        return True
    haystack = " ".join(
        str(value)
        for value in [
            topic,
            title,
            " ".join(str(point) for point in key_points or [] if point),
        ]
    ).lower()
    return any(
        keyword in haystack
        for keyword in ("happy toes", "abby", "poem", "fatherhood", "legacy", "incarceration", "literary", "reinterpretation", "book")
    )


class _AntiRepeatPool:
    """Template pool with anti-repetition tracking."""

    def __init__(self, window_size: int = 12):
        self._used: Dict[str, List[int]] = {}
        self._window = window_size

    def pick(self, category: str, templates: List[str]) -> str:
        if not templates:
            return ""
        recent = self._used.setdefault(category, [])
        available = [i for i in range(len(templates)) if i not in recent]
        if not available:
            recent.clear()
            available = list(range(len(templates)))
        choice = random.choice(available)
        recent.append(choice)
        if len(recent) > self._window:
            recent.pop(0)
        return templates[choice]


class ScriptExpander:
    """Progressive script expander with non-repetitive, phase-aware templates."""

    def __init__(self, words_per_minute: int = 150):
        self.words_per_minute = words_per_minute
        self._pool = _AntiRepeatPool(window_size=12)

    def expand(self, base_lines, key_points, topic, target_minutes=40, title="", existing_context=None, **kwargs):
        target_words = target_minutes * self.words_per_minute
        current_words = sum(len(str(line.get("text", line.get("line", ""))).split()) for line in base_lines)
        domain = "personal_story" if _is_personal_story_context(topic, key_points, title, existing_context, kwargs) else kwargs.get("domain", "generic")

        script = []
        for line in base_lines:
            text = str(line.get("text", line.get("line", "")))
            if "[unknown]" not in text.lower():
                script.append({"speaker": line.get("speaker", "phil"), "text": text, "emotion": line.get("emotion", "neutral"), "pause_after": line.get("pause_after", 0.4), "line_number": 0, "generated_by": line.get("generated_by", "unknown")})

        if not script:
            script = [{"speaker": "phil", "text": f"Welcome to the show. Today: {title or topic}.", "emotion": "enthusiastic", "pause_after": 0.5, "line_number": 0},
                      {"speaker": "jim", "text": "Good ideas are easy. Execution is where things fall apart.", "emotion": "measured", "pause_after": 0.5, "line_number": 0}]
            for line in script:
                line["generated_by"] = "expander"
            current_words = sum(len(line["text"].split()) for line in script)

        ctx = self._build_ctx(topic, key_points, title or topic, existing_context)
        ctx["domain"] = domain
        PATTERNS = [
            ["open", "deepen", "pushback"],
            ["open", "pushback", "deepen"],
            ["open", "deepen", "wonder"],
            ["open", "pushback", "connect"],
            ["open", "wonder", "deepen"],
            ["open", "deepen", "connect"],
        ]

        segment_count = 0
        kp_idx = 0
        line_num = len(script)

        while current_words < target_words and segment_count < 400:
            segment_count += 1
            kp_mod = kp_idx % max(len(key_points), 1)
            point = key_points[kp_mod] if key_points else topic
            related = key_points[(kp_mod + 1) % max(len(key_points), 1)] if len(key_points) > 1 else point
            earlier = key_points[(kp_mod - 1) % max(len(key_points), 1)] if kp_mod > 0 and key_points else point

            ctx.update({"point": self._short(point), "related": self._short(related), "earlier_point": self._short(earlier), "title": title or topic, "domain": domain})

            if segment_count > 1 and random.random() > 0.4:
                tmpl = self._pool.pick("tr", _TRANSITION_PHRASES)
                line_num += 1
                script.append({"speaker": "host", "text": tmpl, "emotion": "neutral", "pause_after": 0.3, "line_number": line_num, "generated_by": "expander"})
                current_words += len(tmpl.split())

            pattern = PATTERNS[segment_count % len(PATTERNS)]
            for phase in pattern:
                if current_words >= target_words:
                    break
                if ctx.get("domain") == "personal_story" or _is_bad_point(ctx.get("point", ""), ctx.get("topic", "")):
                    new_lines = [dict(line) for line in _PERSONAL_STORY_LINES.get(phase, _PERSONAL_STORY_LINES["synthesize"])]
                else:
                    new_lines = self._phase_lines(phase, ctx)
                for line in new_lines:
                    line_num += 1
                    line["line_number"] = line_num
                    line["generated_by"] = "expander"
                    script.append(line)
                    current_words += len(line["text"].split())
                if random.random() > 0.7:
                    hook = self._pool.pick("ho", _HOST_HOOKS).format(**ctx)
                    line_num += 1
                    script.append({"speaker": "host", "text": hook, "emotion": "neutral", "pause_after": 0.3, "line_number": line_num, "generated_by": "expander"})
                    current_words += len(hook.split())
            kp_idx += 1

        if current_words < target_words * 1.05:
            ctx_end = {"point": topic, "related": topic, "earlier_point": topic, "title": title or topic, "topic": topic, "domain": domain}
            for _ in range(2):
                if current_words >= target_words:
                    break
                if ctx_end.get("domain") == "personal_story" or _is_bad_point(ctx_end.get("point", ""), ctx_end.get("topic", "")):
                    lines = [dict(line) for line in _PERSONAL_STORY_LINES["synthesize"]]
                else:
                    lines = self._phase_lines("synthesize", ctx_end)
                for line in lines:
                    line_num += 1
                    line["line_number"] = line_num
                    line["generated_by"] = "expander"
                    script.append(line)
                    current_words += len(line["text"].split())
            script.append({"speaker": "jim", "text": f"And that wraps up our take on {title or topic}. Phil talked too much. I talked just enough.", "emotion": "warm", "pause_after": 0.5, "line_number": line_num + 1, "generated_by": "expander"})
            script.append({"speaker": "phil", "text": "And remember — everything links to something else. You just have not seen it yet.", "emotion": "warm", "pause_after": 0.5, "line_number": line_num + 2, "generated_by": "expander"})

        logger.info("[Expander] %d lines, %d words (target: %d, %.1f%%)", len(script), current_words, target_words, (current_words / max(target_words, 1)) * 100)
        return script

    def _phase_lines(self, phase, ctx):
        p = self._pool
        lines = []
        if ctx.get("domain") == "personal_story" or _is_bad_point(ctx.get("point", ""), ctx.get("topic", "")):
            return [dict(line) for line in _PERSONAL_STORY_LINES.get(phase, _PERSONAL_STORY_LINES["synthesize"])]
        if phase == "open":
            lines.append({"speaker": "phil", "text": p.pick("p_o", _PHIL_OPEN).format(**ctx), "emotion": "excited", "pause_after": 0.35})
            lines.append({"speaker": "jim", "text": p.pick("j_c", _JIM_CHALLENGE).format(**ctx), "emotion": "skeptical", "pause_after": 0.55})
        elif phase == "deepen":
            lines.append({"speaker": "phil", "text": p.pick("p_d", _PHIL_DEEPEN).format(**ctx), "emotion": "curious", "pause_after": 0.35})
            lines.append({"speaker": "jim", "text": p.pick("j_g", _JIM_GROUND).format(**ctx), "emotion": "pragmatic", "pause_after": 0.55})
        elif phase == "pushback":
            lines.append({"speaker": "jim", "text": p.pick("j_c", _JIM_CHALLENGE).format(**ctx), "emotion": "skeptical", "pause_after": 0.55})
            lines.append({"speaker": "phil", "text": p.pick("p_p", _PHIL_PUSHBACK).format(**ctx), "emotion": "warm", "pause_after": 0.4})
        elif phase == "wonder":
            lines.append({"speaker": "phil", "text": p.pick("p_w", _PHIL_WONDER).format(**ctx), "emotion": "curious", "pause_after": 0.4})
            lines.append({"speaker": "jim", "text": p.pick("j_wi", _JIM_WISDOM).format(**ctx), "emotion": "measured", "pause_after": 0.6})
        elif phase == "connect":
            lines.append({"speaker": "phil", "text": p.pick("p_cn", _PHIL_CONNECT).format(**ctx), "emotion": "warm", "pause_after": 0.35})
            lines.append({"speaker": "jim", "text": p.pick("j_co", _JIM_CONCEDE).format(**ctx), "emotion": "warm", "pause_after": 0.5})
        elif phase == "synthesize":
            if random.random() > 0.5:
                lines.append({"speaker": "phil", "text": p.pick("p_s", _PHIL_SYNTHESIZE).format(**ctx), "emotion": "warm", "pause_after": 0.4})
            else:
                lines.append({"speaker": "jim", "text": p.pick("j_s", _JIM_SYNTHESIZE).format(**ctx), "emotion": "measured", "pause_after": 0.55})
        return lines

    def _build_ctx(self, topic, key_points, title, existing):
        ctx = {"topic": topic, "title": title, "point": topic, "related": topic, "earlier_point": topic}
        if existing:
            for k, v in existing.items():
                if isinstance(v, str):
                    ctx[k] = v
        return ctx

    @staticmethod
    def _short(text):
        cleaned = " ".join(str(text or "").replace("_", " ").split()).strip()
        cleaned = cleaned.rstrip(".,;:")
        cleaned = cleaned.removeprefix("How ")
        cleaned = cleaned.removeprefix("What ")
        cleaned = cleaned.removeprefix("Why ")
        for marker in (" and became ", " and why ", " and the ", " which ", ","):
            if marker in cleaned and len(cleaned.split()) > 10:
                cleaned = cleaned.split(marker, 1)[0].strip()
                break
        words = cleaned.split()
        if len(words) > 10:
            words = words[:10]
        while words and words[-1].lower() in {"and", "or", "but", "of", "to", "for", "with", "during", "about", "into"}:
            words.pop()
        return " ".join(words) or str(text or "").strip()


def expand_script(base_lines, key_points, topic, target_minutes=40, **kwargs):
    return ScriptExpander().expand(base_lines=base_lines, key_points=key_points, topic=topic, target_minutes=target_minutes, **kwargs)
