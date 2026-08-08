from typing import Optional

from pydantic import BaseModel, Field


class AdCreateRequest(BaseModel):
    sponsor: str = Field(..., min_length=1, description="Sponsor or brand name")
    product: str = Field("", description="Product or offer label")
    offer: str = Field("", description="Offer hook, e.g., '20% off first order'")
    cta: str = Field("Visit the link in the show notes.", description="Call to action text")
    duration_seconds: int = Field(30, description="Desired spot length in seconds (15, 20, 30)")
    tone: str = Field("confident", description="Optional tone guidance")
    line_index: Optional[int] = Field(None, description="Insert before this 0-based line index")
    insert_into_script: bool = Field(False, description="If true, insert ad lines into the episode script")
    episode_id: Optional[str] = None
    label: str = Field("", description="Optional label for later reference")
    announcer_key: Optional[str] = Field(None, description="Override speaker key (announcer_male / announcer_female)")
