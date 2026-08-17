# Production helpers for script generation and episode orchestration.

from .worker import HardenedPodcastWorker
from .segment_worker import SegmentAwarePodcastWorker

# Existing API imports keep using MergedDandyPodcastWorker. New 1-15 minute
# targets use the segment-aware generation plan; legacy targets >15 minutes
# delegate back to HardenedPodcastWorker behavior.
MergedDandyPodcastWorker = SegmentAwarePodcastWorker

__all__ = [
    "HardenedPodcastWorker",
    "SegmentAwarePodcastWorker",
    "MergedDandyPodcastWorker",
]
