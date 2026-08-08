from typing import Dict, List


def detect_content_lane(title: str, topic: str, script_text: str = "") -> str:
    combined = f"{title} {topic} {script_text}".lower()

    tech_keywords = ("rtx", "3050", "python", "merge", "gpu", "coding", "fastapi", "react", "vite", "tech")
    market_keywords = ("sheep", "sales", "katahdin", "goat", "mint", "market", "alpha certsig", "true mark mint")
    deep_dive_keywords = ("deep dive", "best of", "archive", "long form", "compilation")

    if any(keyword in combined for keyword in tech_keywords):
        return "tech_talk"
    if any(keyword in combined for keyword in market_keywords):
        return "market_updates"
    if any(keyword in combined for keyword in deep_dive_keywords):
        return "deep_dive"
    return "main_show"


def _headline_for_lane(lane: str, title: str) -> str:
    if lane == "tech_talk":
        return "TECH TALK AND STUFF"
    if lane == "market_updates":
        return "MARKET UPDATES"
    if lane == "deep_dive":
        return "DEEP DIVE"
    return title


def _hashtags_for_lane(lane: str) -> List[str]:
    base = [
        "#PhilAndJimDandyShow",
        "#PodcastPromo",
        "#SponsorSpotlight",
        "#GOAT",
    ]
    if lane == "tech_talk":
        return base + ["#TechTalk", "#Python", "#FastAPI", "#React"]
    if lane == "market_updates":
        return base + ["#MarketUpdate", "#TrueMarkMint", "#Katahdin", "#Sales"]
    if lane == "deep_dive":
        return base + ["#DeepDive", "#LongForm", "#BestOf"]
    return base


def build_post_copy(
    episode_id: str,
    title: str,
    topic: str,
    links: List[str] | None = None,
    script_text: str = "",
) -> Dict:
    links = links or []
    content_lane = detect_content_lane(title=title, topic=topic, script_text=script_text)
    headline = _headline_for_lane(content_lane, title)
    body = [
        headline,
        "",
        f"Show: {title}",
        "",
        f"Topic: {topic}",
        "",
        "Listen now and follow the full Phil and Jim Dandy Show experience.",
        "A Pro Prime Series Production 2026",
    ]
    if links:
        body.append("")
        body.extend(links)
    return {
        "episode_id": episode_id,
        "content_lane": content_lane,
        "headline": headline,
        "copy": "\n".join(body),
        "hashtags": _hashtags_for_lane(content_lane),
    }
