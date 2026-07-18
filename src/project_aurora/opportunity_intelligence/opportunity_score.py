"""Opportunity scoring data models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class OpportunityScoreWeights:
    """Weighted business factors for opportunity scoring."""

    demand: float = 0.25
    competition: float = 0.20
    commercial_potential: float = 0.15
    seasonality: float = 0.10
    average_selling_price: float = 0.10
    profit_margin: float = 0.10
    portfolio_diversity: float = 0.05
    trend_velocity: float = 0.05

    def to_dict(self) -> dict[str, float]:
        return {
            "demand": self.demand,
            "competition": self.competition,
            "commercial_potential": self.commercial_potential,
            "seasonality": self.seasonality,
            "average_selling_price": self.average_selling_price,
            "profit_margin": self.profit_margin,
            "portfolio_diversity": self.portfolio_diversity,
            "trend_velocity": self.trend_velocity,
        }


@dataclass(frozen=True, slots=True)
class OpportunityScore:
    """Explainable weighted score for one candidate product."""

    opportunity_id: str
    product: str
    opportunity_score: float
    demand_score: float
    competition_score: float
    commercial_score: float
    seasonality_score: float
    average_selling_price_score: float
    margin_score: float
    portfolio_diversity_score: float
    trend_velocity_score: float
    contributions: dict[str, float]
    weakest_factor: str
    suggested_improvement: str
    expected_revenue: float
    expected_conversion: float
    expected_margin: float
    expected_risk: str
    expected_time_to_first_sale: str
    overall_business_score: float
    selection_outcome: str = "CANDIDATE"
    views: int | None = None
    favorites: int | None = None
    sales: int | None = None
    revenue: float | None = None
    conversion_rate: float | None = None
    profit: float | None = None
    selection_date: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "opportunity_id": self.opportunity_id,
            "product": self.product,
            "opportunity_score": self.opportunity_score,
            "demand_score": self.demand_score,
            "competition_score": self.competition_score,
            "commercial_score": self.commercial_score,
            "seasonality_score": self.seasonality_score,
            "average_selling_price_score": self.average_selling_price_score,
            "margin_score": self.margin_score,
            "portfolio_diversity_score": self.portfolio_diversity_score,
            "trend_velocity_score": self.trend_velocity_score,
            "contributions": dict(self.contributions),
            "weakest_factor": self.weakest_factor,
            "suggested_improvement": self.suggested_improvement,
            "expected_revenue": self.expected_revenue,
            "expected_conversion": self.expected_conversion,
            "expected_margin": self.expected_margin,
            "expected_risk": self.expected_risk,
            "expected_time_to_first_sale": self.expected_time_to_first_sale,
            "overall_business_score": self.overall_business_score,
            "selection_outcome": self.selection_outcome,
            "selection_date": self.selection_date.isoformat(),
            "future_learning": {
                "views": self.views,
                "favorites": self.favorites,
                "sales": self.sales,
                "revenue": self.revenue,
                "conversion_rate": self.conversion_rate,
                "profit": self.profit,
            },
        }
