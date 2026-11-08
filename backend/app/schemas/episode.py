from typing import List, Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, Field


class EpisodeCreateRequest(BaseModel):
    episode_id: str = Field(default_factory=lambda: "ep_" + uuid4().hex[:12], min_length=1)
    title: str = ""
    topic: str = Field(..., min_length=1)
    description: str = ""
    key_points: List[str] = Field(default_factory=list)
    # Planning target only; imported text and audio determine actual runtime.
    target_duration: int = Field(2400, ge=60, le=2700, description="Episode target: 1 to 45 minutes, in seconds")
    # Legacy configuration compatibility; no episode writing uses this field.
    segment_duration_seconds: int = Field(300, ge=60, le=900)
    custom_instructions: str = Field("", max_length=10000)
    intensity: Literal["low", "medium", "high"] = "medium"
    generation_mode: Literal["ai_generate", "script_feed", "hybrid"] = "script_feed"
    provided_script: Optional[List[dict]] = None
    expand_short_script: bool = False
    target_word_count: Optional[int] = None


class ScriptLine(BaseModel):
    speaker: Literal["phil", "jim", "bryan", "host", "guest", "narrator"] = "phil"
    text: str
    emotion: str = "neutral"
    pause_after: float = 0.5
    line_number: Optional[int] = None
