"""Request/Response models for recommendation reason API."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


class RecentMeal(BaseModel):
    category: str
    menu: str
    days_ago: int


class Weather(BaseModel):
    """날씨 (선택). 추천 사유에 반영할 수 있음."""
    condition: str  # e.g. clear, rain, snow, cloudy
    temp_c: float
    feels_like_c: Optional[float] = None


class Context(BaseModel):
    meal_slot: Literal["아침", "점심", "저녁", "야식"]
    hunger_level: int = Field(ge=1, le=5)
    mood: str
    company: str
    effort_level: Literal["간단히", "보통", "제대로"]
    budget_range: str
    recent_meals: list[RecentMeal] = Field(default_factory=list)
    weather: Optional[Weather] = None


class Candidate(BaseModel):
    menu_id: int
    menu_name: str
    category: str
    tags: list[str]
    price_est: int
    prep_time_est: int


class ReasonResponse(BaseModel):
    selected_menu_id: int
    reason_one_liner: str
    reason_tags: list[str]
    top_k_used: Optional[list[int]] = None


class RecommendRequest(BaseModel):
    context: Context
    candidates: list[Candidate]
    k: int = Field(default=5, ge=1, le=20)


class TopKResponse(BaseModel):
    top_k: list[int]
