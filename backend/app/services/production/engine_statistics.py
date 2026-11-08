"""TTS provenance accounting shared by production progress and metadata."""
from collections import Counter, defaultdict


def summarize_engines(segments):
    """Count TTS chunks and distinct script lines separately (a line can use two engines)."""
    lines_by_engine = defaultdict(set)
    for segment in segments:
        lines_by_engine[segment["engine"]].add(segment["line_index"])
    return {
        "engine_stats": dict(Counter(segment["engine"] for segment in segments)),
        "engine_line_stats": {engine: len(lines) for engine, lines in lines_by_engine.items()},
        "synthesized_line_count": len({segment["line_index"] for segment in segments}),
    }

