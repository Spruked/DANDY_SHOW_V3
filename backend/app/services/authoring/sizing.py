"""Heuristic size planning; no claim to reproduce an external model tokenizer."""
import math


def estimated_tokens(text):
    return math.ceil(len(text.encode('utf-8')) / 3)


def pack_size(text, settings):
    tokens = estimated_tokens(text)
    margin = math.ceil(tokens * .15) + 256
    window = settings.get('context_window_tokens', 32768)
    reserve = settings.get('reserved_output_tokens', 4096)
    return {'characters': len(text), 'utf8_bytes': len(text.encode('utf-8')), 'estimated_input_tokens': tokens,
            'export_format': 'markdown',
            'planning_margin_tokens': margin, 'context_window_tokens': window, 'reserved_output_tokens': reserve,
            'input_budget_tokens': window - reserve, 'fits_estimate': tokens + margin + reserve <= window,
            'estimator': 'UTF-8 bytes / 3, plus 15% and 256-token planning margin',
            'exact_tokenizer': False, 'model_name': settings.get('model_name', 'External LLM')}
