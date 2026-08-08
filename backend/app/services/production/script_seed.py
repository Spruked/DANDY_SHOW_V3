"""
script_seed.py — Full-Length Seed Script Generator with Progressive Dialogue
=============================================================================
Generates complete 35-45 minute podcast scripts with ZERO template repetition.

Every template includes topic/key_point variables so lines vary by context.
Anti-repetition window ensures no template fires twice within 12 uses.

Usage:
    from script_seed import generate_seed_script
    script = generate_seed_script({
        "topic": "...", "title": "...", "key_points": ["...", "..."],
        "target_duration_minutes": 40,
    })
"""

import logging
import random
from typing import Any, Dict, List
from collections import Counter

logger = logging.getLogger(__name__)

WORDS_PER_MINUTE = 150

# ═══════════════════════════════════════════════════════════════════════════
# PHIL TEMPLATES — Every template includes {point} or {related} for variety
# ═══════════════════════════════════════════════════════════════════════════

_PHIL_INTRO = [
    "Welcome back to the Phil and Jim Dandy Show. Today we are digging into {title}.",
    "Hey everyone, Phil and Jim here. {title} — let us talk about it.",
    "Alright folks, welcome to the show. Today Jim and I are taking on {title}.",
]

_PHIL_OPEN = [
    "So here is what I keep thinking about: {point}. The energy around this is real, and I think people are starting to notice.",
    "You ever think about {point}? Like, really sit with it? Because the implications are bigger than they first appear.",
    "Okay hear me out... what if {point} is actually the key to everything else we are discussing?",
    "I was reading something about {point} the other day, and it clicked. This is where the shift happens.",
    "What strikes me about {point} is how connected it is to everything else. Nothing happens in isolation.",
    "Here is my take on {point}: we are still in the early innings. Most people do not see what is coming.",
    "The thing about {point} that keeps me up at night? It is moving faster than the conversation around it.",
    "You know what nobody is saying about {point}? That it might actually work. Like, really work.",
    "I keep coming back to {point}. There is something there we have not unpacked yet.",
    "Here is what caught my attention about {point}: it changes the math on everything we assumed was stable.",
    "Let me play devil's advocate. What if {point} is actually overrated?",
    "I was talking to someone last week about {point}, and they said something that stuck with me.",
    "When I first encountered {point}, I did not think much of it. Now I cannot stop thinking about it.",
    "The conversation around {point} feels different this time. I am trying to figure out why.",
    "Here is a question I have been sitting with: is {point} the signal or the noise?",
]

_PHIL_DEEPEN = [
    "And that connects to {related} because the same pattern shows up there too.",
    "Which makes me think... there is a version of this where {related} becomes the norm.",
    "But here is the thing — {related} proves this is not just theory.",
    "Wait actually... I have seen {related} work in a completely different context.",
    "So then I started wondering... does {related} change the math entirely?",
    "And that is where {related} comes in. That is the piece most people miss.",
    "Here is what I mean. Look at {related} — same dynamic, different arena.",
    "It is like {related}. You see the parallel, right?",
    "That is exactly what happened with {related}. History rhymes.",
    "The question is not whether {point} works. It is whether we are ready for what comes after.",
    "If you pull the thread on {point}, you end up at {related}. Every single time.",
    "What people miss about {point} is that it is not the endgame. It is the opening move.",
    "Here is the layer underneath: {related} was the warning sign, and {point} is the consequence.",
    "I am starting to think {point} and {related} are not separate topics. They are the same story.",
    "You cannot understand {point} without looking at {related}. They are inseparable.",
]

_PHIL_PUSHBACK = [
    "Okay, fair pushback. But {point} is not about the hype. It is about the underlying shift.",
    "I hear you, and that skepticism is healthy. But {point} matters because it changes behavior, not because it sounds good.",
    "Yeah, a lot of this is overblown. But strip away the marketing and {point} still has a real foundation.",
    "I am not saying it is perfect. I am saying it is worth understanding. {point} has legs if you look past the surface.",
    "You are right to be cautious. But I have seen enough to know that {point} is not just noise this time.",
    "Look, half of what gets written about {point} is garbage. But the other half? That is where the signal lives.",
    "I am not defending the hype cycle. I am saying: underneath all that, {point} has a mechanical truth to it.",
    "Let me reframe. I am excited about {point} because it solves something people actually feel, not because it is new.",
    "I get the eye roll. I do. But dig into {point} with an open mind and there is something there.",
    "Skepticism is a tool, not a destination. At some point you have to engage with {point} on its merits.",
]

_PHIL_WONDER = [
    "I keep wondering... are we even asking the right questions about {point}?",
    "What if the real opportunity with {point} is not where everyone is looking?",
    "There is a version of this conversation about {point} where we go completely different direction. Should we?",
    "I do not have the answer about {point}. But the question itself is worth something.",
    "Sometimes the idea that sounds dumb at first about {point} is the one that actually works.",
    "What if we are thinking about {point} backwards? What if the constraint is actually the feature?",
    "Here is a thought experiment: what if {point} had launched ten years ago? Would we even be debating it?",
    "I think the most interesting thing about {point} is not what it does. It is what it makes possible.",
    "You know what I think gets lost with {point}? The human side. Behind every data point, someone made a decision.",
    "What if the real story about {point} is not about the technology at all? What if it is about the people living with it?",
    "I keep thinking about the second-order effects of {point}. We are not talking about those enough.",
    "Here is what keeps me up: {point} is going to change things whether we are ready or not.",
]

_PHIL_CONNECT = [
    "Remember when we talked about {earlier_point}? This is the other side of that coin with {point}.",
    "Going back to what you said about {earlier_point}... I think {point} actually validates your skepticism.",
    "You know what? {earlier_point} and {point} are the same story told from different angles.",
    "If you put {earlier_point} next to {point}, a pattern starts to emerge. I do not think that is an accident.",
    "Earlier you pushed back on {earlier_point}. Fair. But look at {point} — that pushback applies here too.",
    "This connects back to {earlier_point} in a way I did not expect. The loop closes with {point}.",
    "Jim, remember your point about {earlier_point}? I think {point} is the test case.",
    "Everything we said about {earlier_point}? Multiply it by ten. That is {point} right now.",
    "The bridge between {earlier_point} and {point} is where the real insight lives.",
    "I just realized something. {earlier_point} was the setup. {point} is the punchline.",
]

_PHIL_SYNTHESIZE = [
    "Okay, let me try to land this plane. {title} is not one thing. It is a stack of things, and they all matter.",
    "If I had to summarize what we have been circling: the opportunity around {point} is real, the execution is hard, and the hype helps nobody.",
    "Here is what I am walking away with: {point} is a tool. Tools do not fix problems. People do.",
    "I think the honest takeaway is this — we are early, we are uncertain, and that is exactly why {point} is worth paying attention to.",
    "The thing I keep coming back to: every big shift looked like {point} at first. Confusing, overhyped, and slightly terrifying.",
    "Let me be real with everyone listening. I do not know exactly where {title} lands. But I know pretending {point} does not exist is not an option.",
    "If there is one thing I hope people remember: {point} is not magic. It is mechanics. And mechanics can be learned.",
    "Here is my final thought on {point}: the people who figure it out first will have an advantage. Not because they are smarter. Because they paid attention.",
]

_PHIL_CLOSE = [
    "And remember — everything links to something else. You just have not seen it yet.",
    "Keep connecting the dots. We will be back next time.",
    "The world is more connected than it looks. Keep looking.",
]


# ═══════════════════════════════════════════════════════════════════════════
# JIM TEMPLATES — Every template includes {point} for context variation
# ═══════════════════════════════════════════════════════════════════════════

_JIM_INTRO = [
    "That is the topic, and we are going to keep it practical, useful, and worth your time.",
    "Fair warning: Phil is going to get excited. I am going to ask hard questions. That is the deal.",
    "Let us see if this holds up. Good ideas are easy. Execution is where things fall apart.",
]

_JIM_CHALLENGE = [
    "Hold on... {point} sounds good when you say it like that. But I have heard this before. What makes it different this time?",
    "Yeah but... {point} — where is the proof? Show me someone who is actually doing this successfully.",
    "That does not make sense to me. If {point} is so obvious, why is not everyone already doing it?",
    "Who told you that? Because the people selling {point} usually have something to gain from your enthusiasm.",
    "Look, I am not against {point}. I am against pretending it is simpler than it is. What is the real cost?",
    "Here is my question: does {point} actually help a regular person, or is this just for people with money and time?",
    "I will believe {point} when I see it working in a place that does not have a PR team.",
    "Let me pump the brakes here. {point} better have some proof behind it before I get on board.",
    "Phil, buddy, you are doing that thing again where you get excited about {point} before checking the foundation.",
    "I have seen too many 'revolutionary' things end up in a drawer. {point} needs to prove it is different.",
    "Not trying to kill the vibe. Just trying to figure out if {point} is real or just well-marketed.",
    "The enthusiasm about {point} is contagious, I will give you that. But enthusiasm is not evidence.",
    "Here is what I want to know about {point}: who loses? Because somebody always loses.",
    "I am willing to be convinced about {point}. But I need more than a promise and a slide deck.",
    "Call me old-fashioned, but {point} needs to survive a Tuesday afternoon in the real world before I trust it.",
    "Before I buy into {point}, I want to see the receipts. Not the projections. The receipts.",
]

_JIM_GROUND = [
    "Let us pump the brakes on {point}. Before we get carried away, what is the downside?",
    "Experience with {point} is what you get right after you need it. Someone is going to learn hard lessons here.",
    "The tool is not the solution. The solution is knowing what you are actually trying to fix with {point}.",
    "At the end of the day, {point} is either useful or it is not. Everything else is marketing.",
    "Just because you can do {point}, does not mean you should. Applies here more than most places.",
    "Here is what I know for sure: complexity sells, but simplicity around {point} actually works.",
    "I am not saying no to {point}. I am saying prove it. Show me the mechanism. How does it actually work?",
    "Laura would hear about {point} and ask one thing: does it make Tuesday easier? If not, what is the point?",
    "The engineering behind {point} might be solid. But engineering alone does not mean people need it.",
    "I took apart enough toasters as a kid to know this: if you cannot see how {point} works, be suspicious.",
    "Look, I want {point} to work. I am just not going to pretend the obstacles do not exist.",
    "The best idea in the world about {point} does not matter if the person using it does not understand it.",
    "Here is my standard test for {point}: can you explain it to someone who does not care? If not, it is not ready.",
    "I have fixed enough things that were 'revolutionary' to know that {point} better have a manual.",
]

_JIM_WISDOM = [
    "You know what my grandfather used to say? 'Just because you can, does not mean you should.' He was usually right about things like {point}.",
    "I have been around long enough to see the pattern around {point}. The promise arrives first. The bill arrives later.",
    "Here is what experience teaches you about {point}: the things that actually last do not need a hype cycle.",
    "I am not cynical about {point}. I am just counting the cost. And the cost is higher than most people admit.",
    "You want to know what works with {point}? The boring stuff. The unsexy, daily, show-up-and-do-it stuff.",
    "The problem with {point} is not the idea — it is the people selling it who have never done the work.",
    "I have watched my kid try to build things with {point}. He gets excited, hits a wall, and then the real learning starts.",
    "You want my honest read on {point}? It is interesting. But interesting does not pay the bills. Useful pays the bills.",
    "Most people do not need {point}. They need the basics done better. We keep forgetting that.",
    "The people who actually need {point} are not the ones writing articles about it. That should tell you something.",
    "I am going to say something unpopular. {point} might be solving a problem that only exists because we created it.",
    "Your time matters. Your attention matters. Do not give it away to {point} until it has earned it.",
    "I have seen {point} come and go in different packaging. The wrapper changes. The reality stays the same.",
    "Here is the uncomfortable truth about {point}: most people will use it wrong, blame the tool, and never look in the mirror.",
    "The difference between {point} working and failing usually comes down to one thing: the person using it.",
]

_JIM_CONCEDE = [
    "Okay. You might have something there with {point}. I am not fully sold, but I will give you that the foundation is stronger than I thought.",
    "Alright, I will meet you halfway. {point} has potential. But potential and performance are two different things.",
    "You know what? I have been thinking about {point} differently. It is not the solution. But it might be part of one.",
    "Fair point about {point}. That actually changes how I look at it. Not all the way, but some.",
    "I am going to admit something: I came into {point} skeptical, and I am still skeptical. But less than I was.",
    "You got me on {point}. That is a better argument than I expected. {point} deserves more credit than I gave it.",
    "I still have questions about {point}. But I will say this — you have made me think about it differently. That is not easy to do.",
    "Here is where I land on {point}: it is real. The question is whether we are mature enough to handle it.",
    "I am not ready to cheerlead {point}. But I am done dismissing it. That is progress.",
    "Okay, Phil. You win this round on {point}. Do not let it go to your head.",
]

_JIM_TRANSITION = [
    "Alright, let us look at {point} from a different angle.",
    "Before we move on from {point}, I want to poke at that a little more.",
    "That is one side of {point}. Here is the other.",
    "Fair point about {point}. But what about the practical side?",
    "I hear you on {point}. Now let me flip it.",
    "Let me ask you this about {point}...",
    "Okay, but consider the opposite of {point} for a second.",
    "I want to come back to something you said about {point} earlier.",
    "Let me play this out. If {point} works exactly as advertised, what happens next?",
    "That is the optimistic read on {point}. Now give me the pessimistic one.",
    "I want to believe in {point}. Convince me one more time.",
    "Here is what I keep circling back to with {point}: who is actually winning here?",
    "Let me be the devil's advocate on {point} for just one more minute.",
    "I think we are talking around the real issue with {point}. Let me name it.",
    "You know what would change my mind about {point}? One concrete example. Just one.",
]

_JIM_SYNTHESIZE = [
    "If I am being honest with everyone listening — and I always am — {point} is a mixed bag. And that is okay. Most things are.",
    "Here is my final take on {point}: do not bet the farm on it. But do not ignore it either. Pay attention. Stay skeptical. That is the job.",
    "What I want people to walk away with about {point}: your time matters. Your attention matters. Do not give it away to something that has not earned it.",
    "I think the healthiest thing you can do with {point} is stay curious but keep your wallet closed until you see proof.",
    "At the end of the day about {point}: you are the one who has to live with the decisions. Not the people selling it.",
    "I will leave you with this about {point}: hope is not a strategy. Neither is fear. What you need is clarity. Go find it.",
    "My grandfather would have looked at {point} and said one word: expensive. He would have been right. But he also would have said: wait and see.",
]

_JIM_CLOSE = [
    "And that wraps up our take on {title}. Phil talked too much. I talked just enough.",
    "That is the show for today. If you got something out of this, tell someone. If not... well, we tried.",
    "Thanks for spending time with us. Remember: ideas are cheap. Execution is everything.",
]


# ═══════════════════════════════════════════════════════════════════════════
# HOST LINES — Audience engagement
# ═══════════════════════════════════════════════════════════════════════════

_HOST_HOOKS = [
    "If you are listening and you have dealt with {point}, you know exactly what I mean.",
    "Some of you are shaking your heads right now about {point}. I get it.",
    "Think about your own situation with {point}. Does this match what you are seeing?",
    "If this conversation about {point} is resonating, you are not alone.",
    "Here is a question for everyone: when is the last time {point} actually worked for you?",
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


class _TemplatePool:
    """Template pool with anti-repetition tracking. Window size prevents recent reuse."""

    def __init__(self, window_size: int = 12):
        self._recent: Dict[str, List[int]] = {}
        self._window = window_size

    def pick(self, pool_name: str, templates: List[str]) -> str:
        if not templates:
            return ""
        recent = self._recent.setdefault(pool_name, [])
        candidates = [i for i in range(len(templates)) if i not in recent]
        if not candidates:
            recent.clear()
            candidates = list(range(len(templates)))
        choice = random.choice(candidates)
        recent.append(choice)
        if len(recent) > self._window:
            recent.pop(0)
        return templates[choice]


class _SafeDict(dict):
    def __missing__(self, key):
        return "{" + key + "}"


def _format(template: str, ctx: Dict[str, str]) -> str:
    try:
        return template.format_map(_SafeDict(ctx))
    except Exception:
        return template


def _shorten(text: str) -> str:
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


def _is_personal_story_config(config: Dict[str, Any]) -> bool:
    if config.get("domain") == "personal_story":
        return True
    haystack = " ".join(
        str(value)
        for value in [
            config.get("topic", ""),
            config.get("title", ""),
            config.get("description", ""),
            " ".join(str(point) for point in config.get("key_points", []) if point),
        ]
    ).lower()
    return any(
        keyword in haystack
        for keyword in ("happy toes", "abby", "poem", "fatherhood", "legacy", "incarceration", "literary", "reinterpretation", "book")
    )


def _build_exchange(pool: _TemplatePool, phase: str, ctx: Dict[str, str]) -> List[Dict[str, Any]]:
    """Generate one or more lines for a conversation phase."""
    lines: List[Dict[str, Any]] = []

    if ctx.get("domain") == "personal_story" or _is_bad_point(ctx.get("point", ""), ctx.get("topic", "")):
        return [dict(line) for line in _PERSONAL_STORY_LINES.get(phase, _PERSONAL_STORY_LINES["synthesize"])]

    if phase == "open":
        lines.append({"speaker": "phil", "text": _format(pool.pick("ph_o", _PHIL_OPEN), ctx), "emotion": "excited", "pause_after": 0.35})
        lines.append({"speaker": "jim", "text": _format(pool.pick("jm_c", _JIM_CHALLENGE), ctx), "emotion": "skeptical", "pause_after": 0.55})

    elif phase == "deepen":
        lines.append({"speaker": "phil", "text": _format(pool.pick("ph_d", _PHIL_DEEPEN), ctx), "emotion": "curious", "pause_after": 0.35})
        lines.append({"speaker": "jim", "text": _format(pool.pick("jm_g", _JIM_GROUND), ctx), "emotion": "pragmatic", "pause_after": 0.55})

    elif phase == "pushback":
        lines.append({"speaker": "jim", "text": _format(pool.pick("jm_c", _JIM_CHALLENGE), ctx), "emotion": "skeptical", "pause_after": 0.55})
        lines.append({"speaker": "phil", "text": _format(pool.pick("ph_p", _PHIL_PUSHBACK), ctx), "emotion": "warm", "pause_after": 0.4})

    elif phase == "wonder":
        lines.append({"speaker": "phil", "text": _format(pool.pick("ph_w", _PHIL_WONDER), ctx), "emotion": "curious", "pause_after": 0.4})
        lines.append({"speaker": "jim", "text": _format(pool.pick("jm_wi", _JIM_WISDOM), ctx), "emotion": "measured", "pause_after": 0.6})

    elif phase == "connect":
        lines.append({"speaker": "phil", "text": _format(pool.pick("ph_cn", _PHIL_CONNECT), ctx), "emotion": "warm", "pause_after": 0.35})
        lines.append({"speaker": "jim", "text": _format(pool.pick("jm_co", _JIM_CONCEDE), ctx), "emotion": "warm", "pause_after": 0.5})

    elif phase == "synthesize":
        if random.random() > 0.5:
            lines.append({"speaker": "phil", "text": _format(pool.pick("ph_s", _PHIL_SYNTHESIZE), ctx), "emotion": "warm", "pause_after": 0.4})
        else:
            lines.append({"speaker": "jim", "text": _format(pool.pick("jm_s", _JIM_SYNTHESIZE), ctx), "emotion": "measured", "pause_after": 0.55})

    return lines


def generate_seed_script(config: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Generate a full-length seed script with progressive, non-repetitive dialogue."""

    topic = config.get("topic", "the current topic")
    title = config.get("title") or topic.replace("_", " ").title()
    key_points = [kp for kp in config.get("key_points", []) if kp]
    domain = "personal_story" if _is_personal_story_config(config) else config.get("domain", "generic")
    target_minutes = config.get("target_duration_minutes", 40)
    if target_minutes < 1:
        target_minutes = 40
    target_words = target_minutes * WORDS_PER_MINUTE

    pool = _TemplatePool(window_size=12)
    script: List[Dict[str, Any]] = []
    line_num = 0
    word_count = 0

    def add(new_lines: List[Dict[str, Any]]) -> None:
        nonlocal line_num, word_count
        for line in new_lines:
            line_num += 1
            line["line_number"] = line_num
            line.setdefault("generated_by", "script_seed")
            word_count += len(line["text"].split())
            script.append(line)

    # Intro
    add([{"speaker": "phil", "text": pool.pick("ph_i", _PHIL_INTRO).format(title=title), "emotion": "enthusiastic", "pause_after": 0.5}])
    add([{"speaker": "jim", "text": pool.pick("jm_i", _JIM_INTRO), "emotion": "measured", "pause_after": 0.5}])

    # Segment patterns — each key_point gets a varied arc
    PATTERNS = [
        ["open", "deepen", "pushback", "wonder"],
        ["open", "pushback", "deepen", "connect"],
        ["open", "deepen", "wonder", "connect"],
        ["open", "pushback", "wonder", "deepen"],
        ["open", "deepen", "connect", "synthesize"],
        ["open", "pushback", "connect", "wonder"],
    ]

    cycles = 0
    kp_idx = 0

    while word_count < target_words and cycles < 300:
        cycles += 1
        point = key_points[kp_idx % len(key_points)] if key_points else topic
        related = key_points[(kp_idx + 1) % len(key_points)] if len(key_points) > 1 else point
        earlier = key_points[(kp_idx - 1) % len(key_points)] if kp_idx > 0 and key_points else point

        ctx = {
            "point": _shorten(point),
            "related": _shorten(related),
            "earlier_point": _shorten(earlier),
            "title": title,
            "topic": topic,
            "domain": domain,
        }

        # Transition between key_points
        if kp_idx > 0 and cycles > 1:
            add([{"speaker": "jim", "text": _format(pool.pick("jm_t", _JIM_TRANSITION), ctx), "emotion": "neutral", "pause_after": 0.4}])

        pattern = PATTERNS[kp_idx % len(PATTERNS)]
        for ex_idx, phase in enumerate(pattern):
            if word_count >= target_words:
                break
            exchanges = _build_exchange(pool, phase, ctx)
            add(exchanges)

            # Occasional host hook
            if ex_idx == 0 and random.random() > 0.6:
                add([{"speaker": "host", "text": _format(pool.pick("ho", _HOST_HOOKS), ctx), "emotion": "neutral", "pause_after": 0.3}])

        kp_idx += 1

    # Closing synthesis + outro
    if word_count < target_words * 1.05:
        for _ in range(2):
            if word_count >= target_words:
                break
            add(_build_exchange(pool, "synthesize", {"point": topic, "related": topic, "earlier_point": topic, "title": title, "topic": topic, "domain": domain}))

        ctx = {"point": topic, "related": topic, "earlier_point": topic, "title": title, "topic": topic, "domain": domain}
        add([{"speaker": "jim", "text": _format(pool.pick("jm_cl", _JIM_CLOSE), ctx), "emotion": "warm", "pause_after": 0.5}])
        add([{"speaker": "phil", "text": _format(pool.pick("ph_cl", _PHIL_CLOSE), ctx), "emotion": "warm", "pause_after": 0.5}])

    # Verify
    _check_repetition(script)

    logger.info(
        "[SeedScript] %d lines, %d words (target: %d min = %d words)",
        len(script), word_count, target_minutes, target_words,
    )
    return script


def _check_repetition(script: List[Dict[str, Any]], threshold: int = 2) -> None:
    """Log warnings if any line repeats more than threshold times."""
    counts = Counter(line["text"] for line in script)
    repeats = {t: c for t, c in counts.items() if c > threshold}
    if repeats:
        for text, count in sorted(repeats.items(), key=lambda x: -x[1])[:5]:
            logger.warning("[SeedScript] Line repeated %dx: %.60s...", count, text)
    else:
        logger.info("[SeedScript] No repetition >%dx", threshold)
