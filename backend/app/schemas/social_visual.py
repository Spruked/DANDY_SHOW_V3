# models/social_visual.py
from pydantic import BaseModel, Field
from typing import List, Optional, Literal


class SlideStyle(BaseModel):
    fontSize: int = 48
    align: Literal["left", "center", "right"] = "center"
    color: str = "#ffffff"
    animation: Literal["none", "fade", "slide", "zoom"] = "fade"


class Slide(BaseModel):
    id: str
    title: str = ""
    subtitle: str = ""
    body: str = ""
    background: str = ""         # filename inside assets/ directory
    overlays: List[str] = Field(default_factory=list)
    start: float = 0.0
    end: float = 10.0
    style: SlideStyle = Field(default_factory=SlideStyle)


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
    aspect: Literal["1:1", "9:16", "16:9"] = "1:1"
    format: Literal["png", "mp4"] = "png"
