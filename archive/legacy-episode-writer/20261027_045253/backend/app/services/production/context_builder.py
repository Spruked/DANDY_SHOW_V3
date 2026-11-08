"""
context_builder.py — Intelligent Context Extraction for Phil & Jim SKG
======================================================================
Replaces the generic _build_context() that maps every template variable
to the same topic string (e.g. everything = "AI").

This module parses key_points and topic to derive meaningful, varied
values for every template slot so dialogue sounds natural and diverse.

Usage:
    from context_builder import build_rich_context

    context = build_rich_context(
        topic="artificial intelligence",
        key_points=[
            "Machine learning is transforming healthcare diagnostics",
            "Privacy concerns around training data are growing",
            "Small language models can run on edge devices now",
        ],
        title="The Future of AI",
        intensity="medium",
    )
    # context["tech_gadget"] == "diagnostic assistant"
    # context["market"] == "healthcare AI"
    # context["trend"] == "edge deployment"
"""

import logging
import random
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── Smart defaults library ──
# When we can't extract a specific value, use these varied defaults
# instead of repeating the topic string.

_DEFAULT_GADGETS = [
    "smart assistant", "voice helper", "auto-correct system",
    "recommendation engine", "search tool", "filter system",
    "notification service", "tracking platform", "analyzer app",
    "prediction tool", "content curator", "detection system",
]

_DEFAULT_TRENDS = [
    "automation", "remote everything", "subscription overload",
    "data mining", "personalization", "algorithmic feeds",
    "voice interfaces", "no-code tools", "platform consolidation",
]

_DEFAULT_COMPARISONS = [
    "a library card catalog", "a fax machine with better marketing",
    "an expensive fortune cookie", "a Magic 8-Ball in a suit",
    "a calculator that went to grad school",
    "a really ambitious spreadsheet",
    "a chatty encyclopedia",
]

_DEFAULT_INDUSTRIES = [
    "tech", "healthcare", "finance", "education",
    "media", "retail", "manufacturing", "energy",
]

_DEFAULT_FEATURES = [
    "speed boost", "cost savings", "ease of use",
    "better accuracy", "time reduction", "error prevention",
    "scalability", "integration options",
]

_DEFAULT_CAR_FEATURES = [
    "mileage", "reliability", "repair cost", "safety rating",
    "resale value", "warranty coverage", "parts availability",
]

_DEFAULT_BELIEFS = [
    "bigger is always better", "newer means improved",
    "complexity equals sophistication", "free means harmless",
    "popular means correct", "faster means smarter",
]

_DEFAULT_COUNTS = ["three", "four", "a dozen", "half a dozen", "a handful"]


def _extract_noun_phrases(text: str) -> List[str]:
    """Extract likely noun phrases from a sentence."""
    # Simple heuristic: sequences of capitalized or compound words
    text = re.sub(r'[^\w\s]', ' ', text)
    words = text.split()
    phrases = []
    current = []

    for word in words:
        w = word.strip()
        if not w:
            continue
        if w[0].isupper() or w in (
            "machine", "learning", "artificial", "intelligence",
            "language", "model", "data", "cloud", "edge", "blockchain",
            "automation", "algorithm", "platform", "service", "system",
        ):
            current.append(w.lower())
        else:
            if len(current) >= 2:
                phrases.append(" ".join(current))
            current = []

    if len(current) >= 2:
        phrases.append(" ".join(current))

    return phrases


def _extract_key_nouns(text: str) -> List[str]:
    """Extract individual important nouns from text."""
    text = re.sub(r'[^\w\s]', ' ', text.lower())
    stop_words = {
        "the", "a", "an", "is", "are", "was", "were", "be", "been",
        "being", "have", "has", "had", "do", "does", "did", "will",
        "would", "could", "should", "may", "might", "must", "shall",
        "can", "need", "dare", "ought", "used", "to", "of", "in",
        "for", "on", "with", "at", "by", "from", "as", "into",
        "through", "during", "before", "after", "above", "below",
        "between", "out", "off", "over", "under", "again", "further",
        "then", "once", "here", "there", "when", "where", "why",
        "how", "all", "each", "few", "more", "most", "other", "some",
        "such", "no", "nor", "not", "only", "own", "same", "so",
        "than", "too", "very", "just", "but", "and", "or", "yet",
        "this", "that", "these", "those", "i", "me", "my", "we",
        "our", "you", "your", "he", "him", "his", "she", "her",
        "it", "its", "they", "them", "their", "what", "which",
        "who", "whom", "s", "t", "don", "doesn", "didn", "wasn",
        "weren", "haven", "hasn", "hadn", "won", "wouldn", "couldn",
        "shouldn", "isn", "aren", "ain", "ma", "mightn", "mustn",
        "needn", "shan", "shouldn", "wasn", "weren", "won", "wouldn",
    }
    words = [w for w in text.split() if len(w) > 3 and w not in stop_words]
    return words


def _extract_domain(topic: str, key_points: List[str]) -> str:
    """Guess the industry/domain from topic + key_points."""
    all_text = " ".join([topic] + key_points).lower()

    domain_keywords = {
        "healthcare": ["health", "medical", "patient", "diagnosis", "clinical", "hospital", "doctor"],
        "finance": ["finance", "banking", "investment", "money", "trading", "crypto", "fintech"],
        "education": ["education", "learning", "student", "school", "university", "teaching"],
        "media": ["media", "content", "streaming", "social", "podcast", "video", "entertainment"],
        "retail": ["retail", "shopping", "e-commerce", "consumer", "product", "store"],
        "manufacturing": ["manufacturing", "factory", "production", "industrial", "supply chain"],
        "technology": ["software", "app", "platform", "code", "developer", "SaaS", "API"],
        "automotive": ["car", "vehicle", "automotive", "driving", "EV", "electric vehicle"],
    }

    scores = {}
    for domain, keywords in domain_keywords.items():
        scores[domain] = sum(1 for kw in keywords if kw in all_text)

    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "technology"


def _build_varied_context(
    topic: str,
    key_points: List[str],
    title: str,
    domain: str,
) -> Dict[str, str]:
    """Build template variables with REAL variety, not just topic repeated."""

    # Extract noun phrases from key points for richer slot filling
    all_nouns = []
    for kp in key_points:
        all_nouns.extend(_extract_key_nouns(kp))
        all_nouns.extend(_extract_noun_phrases(kp))

    # Deduplicate while preserving order
    seen = set()
    unique_nouns = []
    for n in all_nouns:
        if n not in seen and len(n) > 3:
            seen.add(n)
            unique_nouns.append(n)

    # Use key_points as the primary source of varied content
    def kp(idx: int, default: Optional[str] = None) -> str:
        if idx < len(key_points):
            return key_points[idx]
        return default or topic

    def noun(idx: int, default: Optional[str] = None) -> str:
        if idx < len(unique_nouns):
            return unique_nouns[idx]
        return default or topic

    # Pick varied defaults based on domain
    domain_gadgets = {
        "healthcare": ["diagnostic tool", "health monitor", "patient portal", "imaging system"],
        "finance": ["trading app", "budget tracker", "investment platform", "payment system"],
        "education": ["learning platform", "study app", "tutor system", "course tool"],
        "technology": ["coding assistant", "dev tool", "API service", "automation platform"],
        "automotive": ["navigation system", "diagnostic tool", "safety sensor", "EV charger"],
    }
    gadgets = domain_gadgets.get(domain, _DEFAULT_GADGETS)

    # ── Build the full context map ──
    ctx: Dict[str, str] = {
        # Core routing keys
        "current_topic": topic,
        "script_points": key_points,
        "topic": topic,
        "title": title,

        # Phil opener slots — varied from key points
        "possibility": noun(0, f"how {topic} changes things"),
        "thing": noun(0, topic),
        "idea": kp(0, topic),
        "thought": noun(1, f"the direction {topic} is heading"),
        "connection": noun(1, f"where {topic} intersects with daily life"),
        "connected_idea": kp(1, f"what happens when {topic} scales"),
        "domain": domain,
        "reason": f"{topic} addresses a real gap people feel",
        "insight": kp(0, f"the core shift behind {topic}"),
        "correction_or_deeper_thought": kp(1, f"the part most people miss about {topic}"),
        "deeper_question": f"whether {topic} actually improves life or just complicates it",

        # Product/integration slots
        "product": noun(0, topic),
        "tech_product": noun(0, topic),
        "tech_gadget": random.choice(gadgets),
        "tech_trend": noun(1, random.choice(_DEFAULT_TRENDS)),
        "tool": noun(0, topic),
        "feature": noun(0, random.choice(_DEFAULT_FEATURES)),

        # Comparison slots — NEVER just the topic
        "absurd_comparison": random.choice(_DEFAULT_COMPARISONS),
        "analog_comparison": random.choice(_DEFAULT_COMPARISONS),
        "conventional_thing": f"how people normally think about {topic}",
        "unconventional_thing": noun(0, f"what {topic} actually enables"),
        "common_belief": random.choice(_DEFAULT_BELIEFS),
        "obvious_thing": f"the surface-level benefit of {topic}",
        "hidden_thing": noun(2, f"the long-term consequence of {topic}"),

        # Jim challenge slots
        "clarification_attempt": f"the part about {noun(0, topic)}",
        "practical_objection": f"{topic} actually works in the real world",
        "reality_check": f"what adopting {topic} really costs in time and money",

        # Business slots
        "market": f"{domain} {topic}".replace(f"{domain} {domain}", domain),
        "trend": noun(1, random.choice(_DEFAULT_TRENDS)),
        "opportunity": noun(0, f"where {topic} creates new value"),
        "industry": domain,
        "sector": domain,
        "hidden_dynamic": noun(2, f"the power shift behind {topic}"),
        "realization": kp(0, f"what clicked for me about {topic}"),

        # Car templates (when relevant)
        "car_feature": random.choice(_DEFAULT_CAR_FEATURES),
        "car_spec": random.choice(_DEFAULT_CAR_FEATURES),
        "count": random.choice(_DEFAULT_COUNTS),
    }

    return ctx


def build_rich_context(
    topic: str,
    key_points: List[str],
    title: str = "",
    audience: str = "general",
    intensity: str = "medium",
    source_context: str = "",
    personality_settings: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Build a rich, varied context dictionary for Phil & Jim SKG templates.

    This replaces the generic _build_context() that mapped every template
    variable to the topic string. Instead, we:

    1. Extract meaningful nouns and phrases from key_points
    2. Detect the industry/domain
    3. Map template variables to ACTUALLY DIFFERENT values
    4. Provide domain-aware defaults

    Returns a dict with ALL template variables both SKGs expect,
    plus the original routing keys for the communication layer.
    """
    # Clean inputs
    topic = (topic or "the current topic").strip()
    title = (title or topic.replace("_", " ").title()).strip()
    key_points = [kp.strip() for kp in key_points if kp and str(kp).strip()]

    # Append source context as extra key point if provided
    if source_context:
        key_points.append(f"Source material: {source_context[:500]}")

    # Detect domain
    domain = _extract_domain(topic, key_points)

    # Build varied context
    ctx = _build_varied_context(topic, key_points, title, domain)

    # Add routing keys the communication layer needs
    ctx.update({
        "audience": audience,
        "intensity": intensity,
        "source_context": source_context,
        "personality_settings": personality_settings,
    })

    logger.info(
        "[ContextBuilder] Built context for '%s' | domain=%s | key_points=%d | "
        "unique_nouns=%d",
        title, domain, len(key_points), len(set(_extract_key_nouns(" ".join(key_points)))),
    )

    return ctx


def quick_context(topic: str, key_points: List[str]) -> Dict[str, Any]:
    """One-liner for basic usage."""
    return build_rich_context(topic=topic, key_points=key_points)
