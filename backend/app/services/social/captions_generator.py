from typing import Dict, List


def _clean_text(value: str, max_chars: int) -> str:
    return " ".join(value.split())[:max_chars].strip()


def build_hook_text(title: str, topic: str, script_lines: List[Dict]) -> str:
    if script_lines:
        first_text = _clean_text(script_lines[0].get("text", ""), 72)
        if first_text:
            return first_text
    if topic:
        return _clean_text(topic, 72)
    return _clean_text(title, 72)


def build_caption_cues(script_lines: List[Dict], total_duration_seconds: float) -> List[Dict]:
    if not script_lines:
        return []

    durations = []
    total_weight = 0
    for line in script_lines:
        text = line.get("text", "")
        weight = max(1, len(text.split()))
        durations.append(weight)
        total_weight += weight

    if total_weight <= 0:
        total_weight = len(script_lines)

    cues: List[Dict] = []
    current_time = 0.0
    max_cues = 8
    min_duration = 1.8

    for idx, line in enumerate(script_lines[:max_cues]):
        text = _clean_text(line.get("text", ""), 80)
        if not text:
            continue
        speaker = str(line.get("speaker", "speaker")).upper()
        duration = max(min_duration, (durations[idx] / total_weight) * max(total_duration_seconds, min_duration * len(script_lines)))
        start = round(current_time, 2)
        end = round(min(total_duration_seconds, current_time + duration), 2)
        cues.append(
            {
                "speaker": speaker,
                "text": f"{speaker}: {text}",
                "start": start,
                "end": end,
            }
        )
        current_time = end
        if current_time >= total_duration_seconds:
            break

    return cues
