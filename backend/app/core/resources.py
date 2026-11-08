"""Bound expensive local rendering without changing the production job contract."""
import threading
from contextlib import contextmanager
from fastapi import HTTPException

_RENDER_SLOT = threading.BoundedSemaphore(1)


@contextmanager
def render_slot():
    if not _RENDER_SLOT.acquire(blocking=False):
        raise HTTPException(429, "A media render is already running; retry after completion")
    try:
        yield
    finally:
        _RENDER_SLOT.release()
