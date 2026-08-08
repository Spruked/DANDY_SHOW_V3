# Production helpers for script generation and episode orchestration.

from .worker import HardenedPodcastWorker

# Backward-compat alias so existing API code needs no changes
MergedDandyPodcastWorker = HardenedPodcastWorker

__all__ = ["HardenedPodcastWorker", "MergedDandyPodcastWorker"]
