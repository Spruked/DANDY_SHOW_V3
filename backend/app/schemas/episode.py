from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class EpisodeCreateRequest(BaseModel):
    episode_id: str = Field(..., min_length=1)
    title: str = ""
    topic: str = Field(..., min_length=1)
    description: str = ""
    key_points: List[str] = Field(default_factory=list)
    # Target duration in seconds; default to 40 minutes as the optimal show length.
    target_duration: int = 2400
    intensity: Literal["low", "medium", "high"] = "medium"
    generation_mode: Literal["ai_generate", "script_feed", "hybrid"] = "ai_generate"
    provided_script: Optional[List[dict]] = None
    expand_short_script: bool = False
    target_word_count: Optional[int] = None


class ScriptLine(BaseModel):
    speaker: Literal["phil", "jim", "host", "guest", "narrator"] = "phil"
    text: str
    emotion: str = "neutral"
    pause_after: float = 0.5
    line_number: Optional[int] = None
