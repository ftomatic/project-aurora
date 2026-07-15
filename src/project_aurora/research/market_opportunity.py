"""Research-backed product opportunity model."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import uuid4


@dataclass(frozen=True, slots=True)
class MarketOpportunity:
    """One researched commercial opportunity for Aurora."""

    keyword: str
    primary_niche: str
    subcategory: str
    target_audience: str
    season: str
    product_type: str
    recommended_artistic_style: str
    trend_score: float
    competition_score: float
    commercial_potential: float
    confidence: float
    research_sources: tuple[str, ...]
    id: str = field(default_factory=lambda: str(uuid4()))
    created_at: datetime = field(default_factory=datetime.now)

    def __post_init__(self) -> None:
        for field_name in (
            "id",
            "keyword",
            "primary_niche",
            "subcategory",
            "target_audience",
            "season",
            "product_type",
            "recommended_artistic_style",
        ):
            value = str(getattr(self, field_name))
            if not value.strip():
                raise ValueError(f"{field_name} cannot be empty.")
        for field_name in (
            "trend_score",
            "competition_score",
            "commercial_potential",
            "confidence",
        ):
            value = float(getattr(self, field_name))
            if not 0 <= value <= 100:
                raise ValueError(f"{field_name} must be between 0 and 100.")
        if not self.research_sources:
            raise ValueError("research_sources cannot be empty.")
        object.__setattr__(self, "research_sources", tuple(self.research_sources))

    def to_dict(self) -> dict[str, Any]:
        """Return JSON-safe opportunity data."""
        return {
            "id": self.id,
            "keyword": self.keyword,
            "primary_niche": self.primary_niche,
            "subcategory": self.subcategory,
            "target_audience": self.target_audience,
            "season": self.season,
            "product_type": self.product_type,
            "recommended_artistic_style": self.recommended_artistic_style,
            "trend_score": self.trend_score,
            "competition_score": self.competition_score,
            "commercial_potential": self.commercial_potential,
            "confidence": self.confidence,
            "research_sources": list(self.research_sources),
            "created_at": self.created_at.isoformat(),
        }
