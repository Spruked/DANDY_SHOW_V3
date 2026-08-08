# Single shared SentenceTransformer instance for Phil + Jim SKGs
# Prevents CUDA OOM on RTX 3050 6GB when both SKGs run in same process.

from sentence_transformers import SentenceTransformer
import torch
import logging

_shared_encoder = None


def get_shared_encoder(device: str = "cuda") -> SentenceTransformer:
    global _shared_encoder
    if _shared_encoder is None:
        logging.info(f"[SharedEncoder] Loading SentenceTransformer on {device}")
        _shared_encoder = SentenceTransformer("all-MiniLM-L6-v2", device=device)
        logging.info("[SharedEncoder] Loaded - single instance active")
    return _shared_encoder


def release_shared_encoder():
    """Call on shutdown to free VRAM before Kokoro loads if needed."""
    global _shared_encoder
    if _shared_encoder is not None:
        del _shared_encoder
        _shared_encoder = None
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        logging.info("[SharedEncoder] Released")
