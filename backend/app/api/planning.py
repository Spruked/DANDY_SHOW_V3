from typing import Any
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from ..services.planning import registry, scheduler

router = APIRouter(prefix="/planning", tags=["planning"])

class BusinessRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    brief: str = Field(default="", max_length=20000)
    tone: str = Field(default="", max_length=1000)

class ProductRequest(BusinessRequest):
    business_slug: str = Field(min_length=1, max_length=100)
    claims: list[str] = Field(default_factory=list, max_length=100)
    offer: dict[str, Any] = Field(default_factory=dict)
    links: list[str] = Field(default_factory=list, max_length=100)

class PlanRequest(BaseModel):
    episode_number: int = Field(ge=1)
    featured_product: str = Field(min_length=1, max_length=120)
    release_date: str
    business_slug: str = Field(min_length=1, max_length=100)
    ad_assignments: list[str] = Field(default_factory=list, max_length=20)

class CalendarRequest(BaseModel):
    start_date: str
    weeks: int = Field(default=4, ge=1, le=8)

@router.get("/businesses")
def businesses(): return registry.list_businesses()

@router.post("/businesses")
def add_business(payload: BusinessRequest):
    try: return registry.create_business(payload.name, payload.brief, payload.tone)
    except (ValueError, FileExistsError) as exc: raise HTTPException(409, str(exc)) from exc

@router.get("/businesses/{business_slug}/products")
def products(business_slug: str): return registry.list_products(business_slug)

@router.post("/products")
def add_product(payload: ProductRequest):
    try: return registry.create_product(payload.business_slug, payload.name, payload.brief, payload.claims, payload.offer, payload.links, payload.tone)
    except (ValueError, FileExistsError) as exc: raise HTTPException(409, str(exc)) from exc

@router.get("/products/{business_slug}/{product_slug}")
def product(business_slug: str, product_slug: str):
    try: return registry.get_product(business_slug, product_slug)
    except ValueError as exc: raise HTTPException(404, str(exc)) from exc

@router.get("/plans")
def plans(): return scheduler.list_plans()

@router.post("/plans")
def add_plan(payload: PlanRequest):
    try: return scheduler.create_plan(**payload.model_dump())
    except ValueError as exc: raise HTTPException(422, str(exc)) from exc

@router.post("/calendar")
def calendar(payload: CalendarRequest):
    try: return {"plans": scheduler.generate_calendar(payload.start_date, payload.weeks)}
    except ValueError as exc: raise HTTPException(422, str(exc)) from exc
