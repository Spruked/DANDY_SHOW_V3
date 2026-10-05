from typing import Dict, List


ADS_CATALOG: Dict[str, Dict] = {
    "truemark": {"label": "TrueMark Mint", "tone": "authority"},
    "goat": {"label": "GOAT Engine", "tone": "curiosity"},
    "apex": {"label": "APEX Docs", "tone": "clarity"},
    "vaultforge": {"label": "VaultForge", "tone": "trust"},
    "orb": {"label": "ORB Assistant", "tone": "helpful"},
}

def summarize_context(script_lines: List[Dict], max_chars: int = 240) -> str:
    text = " ".join(line.get("text", "") for line in script_lines)
    return text[:max_chars]


def generate_ad_script(product_key: str, announcer: str, episode_context: str,
                       duration_seconds: int = 20, *, sponsor: str = "",
                       product_name: str = "", offer: str = "", cta: str = "") -> List[Dict]:
    """Catalog labels supply identity, not unverified claims or repeated filler.

    Keep episode_context in the call contract for existing callers. Episode
    dialogue is never repurposed as sponsor copy. Target duration is applied
    to actual audio, without expanding or trimming the operator's text.
    """
    from ..production.ads import generate_ad_lines
    product = ADS_CATALOG.get(product_key, {"label": product_key, "tone": "confident"})
    lines = generate_ad_lines(sponsor or product["label"], product_name, offer,
                              cta or "See the show notes for details.", duration_seconds,
                              product.get("tone", "confident"))
    for line in lines:
        line["speaker"] = announcer
    return lines
