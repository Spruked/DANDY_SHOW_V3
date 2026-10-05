import math
from typing import Dict, List


def mix_ad_tracks(ad, tracks, assets):
    """One local audio authority shared by visual rendering and episode assembly."""
    from pathlib import Path
    from pydub import AudioSegment
    voice = AudioSegment.from_file(ad["audio_file"])
    duration_ms = round(float(ad["duration_seconds"]) * 1000)
    if len(voice) > duration_ms + 150:
        raise ValueError("Spoken audio exceeds the requested ad duration; increase the target or shorten copy. No trimming or speed change was applied.")
    mixed = voice + AudioSegment.silent(duration=max(0, duration_ms - len(voice)), frame_rate=voice.frame_rate)
    asset_map = {asset["asset_id"]: asset for asset in assets}
    for track in tracks:
        record = asset_map.get(track["asset_id"])
        if not record or not Path(record["stored_path"]).is_file():
            raise ValueError(f"SFX asset {track['asset_id']} is missing from this ad")
        sound = AudioSegment.from_file(record["stored_path"]) + float(track.get("volume_db", -12))
        if track.get("fade_in"):
            sound = sound.fade_in(min(len(sound), round(track["fade_in"] * 1000)))
        if track.get("fade_out"):
            sound = sound.fade_out(min(len(sound), round(track["fade_out"] * 1000)))
        start_ms = round(track.get("start", 0) * 1000)
        if start_ms + len(sound) > duration_ms:
            raise ValueError(f"SFX {track['id']} extends beyond the requested ad duration")
        mixed = mixed.overlay(sound, position=start_ms)
    return mixed


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
