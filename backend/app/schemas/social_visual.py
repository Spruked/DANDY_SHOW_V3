# models/social_visual.py
from pydantic import BaseModel, Field, model_validator
from typing import List, Optional, Literal


class SlideStyle(BaseModel):
    fontSize: int = Field(48, ge=12, le=200)
    align: Literal["left", "center", "right"] = "center"
    color: str = Field("#ffffff", pattern=r"^#[0-9a-fA-F]{6}$")
    animation: Literal["none", "fade", "slide", "zoom"] = "fade"


class Slide(BaseModel):
    id: str
    title: str = ""
    subtitle: str = ""
    body: str = ""
    background: str = ""         # filename inside assets/ directory
    overlays: List[str] = Field(default_factory=list)
    start: float = Field(0, ge=0)
    end: float = Field(10, gt=0)
    style: SlideStyle = Field(default_factory=SlideStyle)

    @model_validator(mode="after")
    def timing(self):
        if self.end <= self.start:
            raise ValueError("Slide end must be after start")
        return self


class Slideshow(BaseModel):
    episode_id: str
    slides: List[Slide] = Field(default_factory=list)


class AdCard(BaseModel):
    id: str
    type: Literal[
        "sponsor", "cta", "product", "brought_by",
        "end_roll", "qr", "truemark", "goat", "orb",
    ] = "sponsor"
    sponsor: str = ""
    cta: str = ""
    url: str = ""
    offer_code: str = ""
    product_image: str = ""
    background: str = ""
    logo: str = ""


class AdCardCollection(BaseModel):
    episode_id: Optional[str] = None
    cards: List[AdCard] = Field(default_factory=list)


# ---------- request/response envelopes ----------

class SaveSlideshowRequest(BaseModel):
    episode_id: str
    slides: List[Slide]


class RenderSlideshowRequest(BaseModel):
    episode_id: str
    aspect: Literal["16:9", "1:1", "9:16"] = "16:9"
    format: Literal["mp4", "png_sequence"] = "mp4"


class SaveAdCardsRequest(BaseModel):
    episode_id: Optional[str] = None
    cards: List[AdCard]


class RenderAdCardRequest(BaseModel):
    card_id: str
    episode_id: Optional[str] = None
    aspect: Literal["1:1", "9:16", "16:9"] = "1:1"
    format: Literal["png", "mp4"] = "png"


class SocialExportRequest(BaseModel):
    episode_id: str = Field(min_length=1, pattern=r"^[A-Za-z0-9_.-]+$")
    export_type: Literal["audiogram", "thumbnail", "quote_card", "promo_clip", "show_notes"] = "audiogram"
    platform: str = Field("instagram", min_length=1, max_length=64)
    aspect_ratio: Literal["1:1", "16:9", "9:16", "4:5"] = "1:1"
    asset_slot: Literal["none", "thumbnail_base", "waveform_base", "alternate_cover", "character_logo", "segment_tech_talk", "logo", "pops_thumbnail_base", "pops_character_art", "pops_wordmark", "pops_logo_mark"] = "none"
    clip_start: float = Field(0, ge=0)
    clip_duration: float = Field(60, ge=5, le=300)
    quote_text: str = Field("", max_length=600)
    post_text: str = Field("", max_length=10000)
    show_waveform: bool = True
    visual_mode: Literal["plain", "waveform", "image", "slideshow", "video"] = "waveform"
    visual_asset_id: str = ""
    visual_asset_ids: List[str] = Field(default_factory=list, max_length=8)
    visual_clip_start: float = Field(0, ge=0)
