from typing import Dict, List


ADS_CATALOG: Dict[str, Dict] = {
    "truemark": {"label": "TrueMark Mint", "tone": "authority"},
    "goat": {"label": "GOAT Engine", "tone": "curiosity"},
    "apex": {"label": "APEX Docs", "tone": "clarity"},
    "vaultforge": {"label": "VaultForge", "tone": "trust"},
    "orb": {"label": "ORB Assistant", "tone": "helpful"},
}

WORDS_PER_SECOND = 2.7  # ~160 wpm
TARGET_SECONDS = 18
MIN_SECONDS = 10
MAX_SECONDS = 22
TARGET_WORDS = int(TARGET_SECONDS * WORDS_PER_SECOND)  # ~48 words
MIN_WORDS = int(MIN_SECONDS * WORDS_PER_SECOND)        # ~27 words
MAX_WORDS = int(MAX_SECONDS * WORDS_PER_SECOND)        # ~59 words


def estimate_seconds(word_count: int) -> float:
    return word_count / WORDS_PER_SECOND


def _expand_ad(text: str) -> str:
    filler = " Get the details in the show notes."
    while len(text.split()) < MIN_WORDS:
        text = text + filler
    return text


def _trim_ad(text: str) -> str:
    words = text.split()
    if len(words) <= MAX_WORDS:
        return text
    return " ".join(words[:MAX_WORDS])


def _normalize_ad_length(text: str) -> str:
    words = text.split()
    if len(words) < MIN_WORDS:
        return _expand_ad(text)
    if len(words) > MAX_WORDS:
        return _trim_ad(text)
    return text


def summarize_context(script_lines: List[Dict], max_chars: int = 240) -> str:
    text = " ".join([l.get("text", "") for l in script_lines])
    return text[:max_chars]


def generate_ad_script(product_key: str, announcer: str, episode_context: str, duration_seconds: int = 20) -> List[Dict]:
    product = ADS_CATALOG.get(product_key, {"label": product_key, "tone": "confident"})
    label = product["label"]
    tone = product.get("tone", "confident")
    # Structure: hook / what / why / CTA
    hook = f"This episode is brought to you by {label}."
    what = episode_context or "Stay ahead with the tools built for you."
    why = f"{label} helps you move faster and keep your edge."
    cta = "Check the link in the show notes to get started."

    texts = [hook, what, why, cta]
    normalized_texts = []
    for t in texts:
        normalized_texts.append(_normalize_ad_length(t))

    lines = []
    for idx, t in enumerate(normalized_texts, start=1):
        lines.append(
            {
                "speaker": announcer,
                "text": t,
                "emotion": tone,
                "pause_after": 0.45 if idx == 1 else 0.35,
                "line_number": idx,
            }
        )

    # Final normalization on combined length
    total_words = sum(len(l["text"].split()) for l in lines)
    seconds = estimate_seconds(total_words)
    if seconds < MIN_SECONDS:
        # Expand CTA slightly
        lines[-1]["text"] = _expand_ad(lines[-1]["text"])
    elif seconds > MAX_SECONDS:
        lines[-1]["text"] = _trim_ad(lines[-1]["text"])

    # Reindex after potential adjustments
    for idx, line in enumerate(lines, start=1):
        line["line_number"] = idx
    return lines
