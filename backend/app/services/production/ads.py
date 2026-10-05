from typing import Dict, List
import hashlib
import json


def ad_audio_fingerprint(lines):
    """Spoken copy, identity, delivery and pauses must match reusable audio."""
    payload = [{"speaker": line.get("speaker"), "text": line.get("text"),
                "emotion": line.get("emotion", "neutral"), "pause_after": line.get("pause_after", .4)}
               for line in lines]
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def mix_ad_tracks(ad, tracks, assets):
    """One local audio authority shared by visual rendering and episode assembly."""
    from pathlib import Path
    from pydub import AudioSegment
    with open(ad["audio_file"], "rb") as handle:
        voice = AudioSegment.from_file(handle)
    duration_ms = round(float(ad["duration_seconds"]) * 1000)
    if len(voice) > duration_ms + 150:
        raise ValueError("Spoken audio exceeds the requested ad duration; increase the target or shorten copy. No trimming or speed change was applied.")
    mixed = voice + AudioSegment.silent(duration=max(0, duration_ms - len(voice)), frame_rate=voice.frame_rate)
    asset_map = {asset["asset_id"]: asset for asset in assets}
    for track in tracks:
        record = asset_map.get(track["asset_id"])
        if not record or not Path(record["stored_path"]).is_file():
            raise ValueError(f"SFX asset {track['asset_id']} is missing from this ad")
        with open(record["stored_path"], "rb") as handle:
            sound = AudioSegment.from_file(handle) + float(track.get("volume_db", -12))
        if track.get("fade_in"):
            sound = sound.fade_in(min(len(sound), round(track["fade_in"] * 1000)))
        if track.get("fade_out"):
            sound = sound.fade_out(min(len(sound), round(track["fade_out"] * 1000)))
        start_ms = round(track.get("start", 0) * 1000)
        if start_ms + len(sound) > duration_ms:
            raise ValueError(f"SFX {track['id']} extends beyond the requested ad duration")
        mixed = mixed.overlay(sound, position=start_ms)
    return mixed


def generate_ad_lines(
    sponsor: str,
    product: str,
    offer: str,
    cta: str,
    duration_seconds: int,
    tone: str = "confident",
) -> List[Dict]:
    """Use supplied facts once; the audio stage enforces the requested duration.

    Missing offer details are not evidence for an exclusive deal or a product
    claim. Silence padding belongs to the renderer, never generated filler.
    """
    if not 5 <= duration_seconds <= 120:
        raise ValueError("Ad duration must be between 5 and 120 seconds")
    hook = f"{sponsor} presents {product}" if product else f"This message is from {sponsor}"
    texts = [hook.rstrip(". !?") + "."]
    for text in (offer, cta):
        if text and text.strip() and text.strip() not in texts:
            texts.append(text.strip())
    return [{"speaker": "announcer_male", "text": text, "emotion": tone,
             "pause_after": .4, "line_number": index}
            for index, text in enumerate(texts, start=1)]
