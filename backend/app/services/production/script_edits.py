"""Small editorial transforms adapted from the earlier Dandy studio."""
from copy import deepcopy


def adjust_tone(script, adjustment, start=0, end=None):
    result = deepcopy(script)
    for line in result[start:end]:
        speaker = str(line.get("speaker", "")).lower()
        if speaker not in {"phil", "jim"}:
            continue
        text = line.get("text", "")
        if adjustment == "more_humorous":
            if speaker == "phil":
                if "!" not in text:
                    line["text"] = text + "!"
                line["emotion"] = "excited"
            else:
                if "you know?" not in text.lower():
                    line["text"] = text + " You know?"
                line["emotion"] = "dry_wit"
        elif adjustment == "more_serious":
            line["text"] = text.replace("!", ".")
            line["emotion"] = "thoughtful" if speaker == "phil" else "analytical"
        elif adjustment == "faster_paced":
            line["pause_after"] = 0.2
        elif adjustment == "slower_paced":
            line["pause_after"] = 1.0
            if speaker == "jim":
                line["emotion"] = "deliberate"
        else:
            # Preserve the existing API contract for direct emotion adjustments.
            line["emotion"] = adjustment
        # Keep authorship provenance; this is a recorded editorial transformation.
        line["edited_by"] = "tone_control"
        line["tone_adjustment"] = adjustment
    return result
