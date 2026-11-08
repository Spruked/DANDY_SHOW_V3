from typing import Optional, Literal, List

from pydantic import BaseModel, Field, model_validator


class AdCreateRequest(BaseModel):
    sponsor: str = Field(..., min_length=1, description="Sponsor or brand name")
    product: str = Field("", description="Product or offer label")
    offer: str = Field("", description="Offer hook, e.g., '20% off first order'")
    cta: str = Field("Visit the link in the show notes.", description="Call to action text")
    duration_seconds: int = Field(30, ge=5, le=120, description="Target spot length in seconds")
    tone: str = Field("confident", description="Optional tone guidance")
    line_index: Optional[int] = Field(None, ge=0, description="Insert before this 0-based line index")
    insert_into_script: bool = Field(False, description="If true, insert ad lines into the episode script")
    episode_id: Optional[str] = None
    label: str = Field("", description="Optional label for later reference")
    announcer_key: Optional[str] = Field(None, min_length=1, description="Registered speaker identity; never remapped to a fallback")
    ad_type: str = Field("custom", max_length=64)
    custom_script: str = Field("", max_length=10000)


class AdInsertRequest(BaseModel):
    line_index: Optional[int] = Field(None, ge=0, description="Insert before this 0-based line index; null appends")


Motion = Literal["none", "fade", "slide", "zoom", "reveal", "pulse"]


class TimedLayer(BaseModel):
    id: str = Field(min_length=1, max_length=100)
    start: float = Field(0, ge=0, le=120)
    end: float = Field(30, gt=0, le=120)
    animation_in: Motion = "fade"
    animation_out: Motion = "fade"
    animation_duration: float = Field(.5, ge=.05, le=5)
    easing: Literal["linear", "ease_in_out"] = "ease_in_out"

    @model_validator(mode="after")
    def timing(self):
        if self.end <= self.start:
            raise ValueError("Layer end must be after start")
        return self


class AdTextLayer(TimedLayer):
    content: str = Field("", max_length=2000)
    role: Literal["headline", "subtitle", "cta", "offer_code", "url", "custom"] = "headline"
    x: float = Field(.5, ge=0, le=1)
    y: float = Field(.45, ge=0, le=1)
    font: Literal["Arial", "Arial Bold", "Georgia", "Consolas"] = "Arial Bold"
    size: int = Field(64, ge=12, le=200)
    align: Literal["left", "center", "right"] = "center"
    color: str = Field("#ffffff", pattern=r"^#[0-9a-fA-F]{6}$")


class AdVisualLayer(TimedLayer):
    asset_id: str = Field(min_length=1)
    role: Literal["background", "logo", "product", "overlay"] = "background"
    x: float = Field(.5, ge=0, le=1)
    y: float = Field(.5, ge=0, le=1)
    width: float = Field(1, gt=0, le=1)
    opacity: float = Field(1, ge=0, le=1)


class AdSfxTrack(BaseModel):
    id: str = Field(min_length=1, max_length=100)
    asset_id: str = Field(min_length=1)
    start: float = Field(0, ge=0, le=120)
    volume_db: float = Field(-12, ge=-60, le=12)
    fade_in: float = Field(.05, ge=0, le=10)
    fade_out: float = Field(.1, ge=0, le=10)


class AdComposition(BaseModel):
    version: Literal[1] = 1
    aspect: Literal["16:9", "1:1", "9:16", "4:5"] = "16:9"
    background_color: str = Field("#0e1116", pattern=r"^#[0-9a-fA-F]{6}$")
    text_layers: List[AdTextLayer] = Field(default_factory=list, max_length=16)
    visuals: List[AdVisualLayer] = Field(default_factory=list, max_length=8)
    sfx_tracks: List[AdSfxTrack] = Field(default_factory=list, max_length=12)

    @model_validator(mode="after")
    def unique_ids(self):
        ids = [layer.id for layer in self.text_layers + self.visuals + self.sfx_tracks]
        if len(ids) != len(set(ids)):
            raise ValueError("Track IDs must be unique")
        return self
