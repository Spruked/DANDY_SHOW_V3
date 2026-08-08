import math
from typing import Dict, List


def _estimate_words(duration_seconds: int, words_per_minute: int = 150) -> int:
    # Conservative speaking rate; ad reads are usually tighter/faster.
    wps = words_per_minute / 60
    return max(15, int(duration_seconds * wps * 0.9))


def generate_ad_lines(
    sponsor: str,
    product: str,
    offer: str,
    cta: str,
    duration_seconds: int,
    tone: str = "confident",
) -> List[Dict]:
    target_words = _estimate_words(duration_seconds)
    hook = f"{sponsor} presents {product}" if product else f"{sponsor} has you covered"
    offer_text = offer or "Exclusive for listeners."
    cta_text = cta or "Learn more in the show notes."

    lines: List[Dict] = [
        {
            "speaker": "intro_male",
            "text": f"{hook}. {offer_text}",
            "emotion": tone,
            "pause_after": 0.4,
        },
        {
            "speaker": "intro_female",
            "text": f"Quick hit: {offer_text}. {cta_text}",
            "emotion": tone,
            "pause_after": 0.4,
        },
    ]

    # If we need more words to reach target, add a single closer line.
    word_count = sum(len(l["text"].split()) for l in lines)
    if word_count < target_words:
        remaining = target_words - word_count
        closer = (
            f"{sponsor}—{offer_text}—{cta_text}"
        )
        # Trim closer roughly to remaining words.
        closer_words = closer.split()[: max(3, int(remaining))]
        lines.append(
            {
                "speaker": "intro_male",
                "text": " ".join(closer_words),
                "emotion": tone,
                "pause_after": 0.3,
            }
        )

    # Reindex line_number for clarity when inserted into script.
    for idx, line in enumerate(lines, start=1):
        line["line_number"] = idx
    return lines
