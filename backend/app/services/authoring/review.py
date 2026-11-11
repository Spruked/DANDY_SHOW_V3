"""Informational draft review: duplicated exchanges and speaker identity.

Dandy Show dialogue repetition policy: product and brand names, slogans, key
messages, callbacks and returning topics are normal and never flagged. Only
substantial verbatim duplication of a complete exchange (several consecutive
turns copied word for word) is reported, for the owner to judge. Warnings
never delete, rewrite, reject or block anything.
"""
import re
from typing import Dict, List, Optional

MIN_EXCHANGE_TURNS = 2     # an exchange: at least two consecutive turns copied verbatim
MIN_EXCHANGE_WORDS = 25    # and long enough that it is not a slogan or a short interjection


def normalized(text: str) -> str:
    from ..storage.episode_store import _normal_text
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", "", _normal_text(str(text)))).strip()


def _duplicate_runs(lines: List[Dict], sources: List[tuple]) -> List[Dict]:
    """Longest verbatim runs of consecutive turns in `lines` that also occur in a source sequence.

    `sources` is a list of (label, lines, is_self). For is_self the match must end before it starts.
    """
    keys = [normalized(line["text"]) for line in lines]
    found, covered = [], set()
    for start in range(len(lines)):
        if start in covered:
            continue
        best = None
        for label, source, is_self in sources:
            source_keys = [normalized(line["text"]) for line in source]
            for origin in range(len(source)):
                length = 0
                while (start + length < len(lines) and origin + length < len(source)
                       and keys[start + length] and keys[start + length] == source_keys[origin + length]
                       and (not is_self or origin + length < start)):
                    length += 1
                if length and (best is None or length > best[2]):
                    best = (label, origin, length, source)
        if not best:
            continue
        label, origin, length, source = best
        words = sum(len(lines[start + k]["text"].split()) for k in range(length))
        if length >= MIN_EXCHANGE_TURNS and words >= MIN_EXCHANGE_WORDS:
            covered.update(range(start, start + length))
            first, last = source[origin], source[origin + length - 1]
            if label == "this draft":
                where = f"lines {origin + 1}-{origin + length} of this draft"
            else:
                where = f"{label} lines {first.get('segment_line', origin + 1)}-{last.get('segment_line', origin + length)}"
            found.append({"id": f"duplicate_exchange_{start + 1}", "kind": "duplicate_exchange",
                          "informational": True, "line": start + 1, "end_line": start + length,
                          "text": lines[start]["text"],
                          "detail": f"Lines {start + 1}-{start + length} ({length} turns, {words} words) repeat "
                                    f"{where} word for word. Owner decides whether this is intentional."})
    return found


def review_dialogue(lines: List[Dict], earlier: Optional[List[Dict]] = None) -> List[Dict]:
    """Informational warnings with line numbers. `earlier` are approved lines from previous segments."""
    by_segment: Dict[int, List[Dict]] = {}
    for line in earlier or []:
        by_segment.setdefault(line.get("segment_index"), []).append(line)
    sources = [(f"segment {index}" if index else "earlier dialogue", seg_lines, False)
               for index, seg_lines in by_segment.items()]
    sources.append(("this draft", lines, True))
    warnings = _duplicate_runs(lines, sources)
    for position, line in enumerate(lines, 1):
        name = line["speaker"]
        if re.match(rf"^(?:you know,\s*|hey,?\s*|listen,?\s*)?{name}[,!?:]", line["text"], re.I):
            warnings.append({"id": f"self_address_{position}", "kind": "self_address", "informational": True,
                             "line": position, "text": line["text"],
                             "detail": f"{name} appears to address himself; review character identity"})
    return sorted(warnings, key=lambda w: w["line"])
