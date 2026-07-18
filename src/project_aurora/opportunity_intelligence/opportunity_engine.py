"""Weighted Opportunity Intelligence Engine."""

from __future__ import annotations

from datetime import datetime

from project_aurora.opportunity_intelligence.opportunity_score import (
    OpportunityScore,
    OpportunityScoreWeights,
)
from project_aurora.research.market_opportunity import MarketOpportunity


class OpportunityIntelligenceEngine:
    """Score researched candidates by expected merchant value."""

    def __init__(
        self,
        weights: OpportunityScoreWeights | None = None,
        current_date: datetime | None = None,
    ) -> None:
        self._weights = weights or OpportunityScoreWeights()
        self._current_date = current_date or datetime.now()

    def score(
        self,
        opportunity: MarketOpportunity,
        selected_today: tuple[MarketOpportunity, ...] = (),
        selection_outcome: str = "CANDIDATE",
    ) -> OpportunityScore:
        """Return an explainable 0-100 opportunity score."""
        factor_scores = {
            "demand": _clamp(opportunity.trend_score),
            "competition": _clamp(100 - opportunity.competition_score),
            "commercial_potential": _clamp(opportunity.commercial_potential),
            "seasonality": _seasonality_score(opportunity.season, self._current_date.month),
            "average_selling_price": _average_selling_price_score(opportunity.product_type),
            "profit_margin": _profit_margin_score(opportunity.product_type),
            "portfolio_diversity": _portfolio_diversity_score(opportunity, selected_today),
            "trend_velocity": _trend_velocity_score(opportunity),
        }
        contributions = {
            factor: round(score * self._weights.to_dict()[factor], 2)
            for factor, score in factor_scores.items()
        }
        total = round(sum(contributions.values()), 2)
        weakest_factor = min(factor_scores, key=lambda key: factor_scores[key])
        expected_price = _expected_price(opportunity.product_type)
        expected_margin = round(expected_price * (factor_scores["profit_margin"] / 100), 2)
        expected_conversion = round(
            (factor_scores["demand"] * 0.05 + factor_scores["commercial_potential"] * 0.04) / 100,
            3,
        )
        return OpportunityScore(
            opportunity_id=opportunity.id,
            product=opportunity.keyword.title(),
            opportunity_score=total,
            demand_score=round(factor_scores["demand"], 2),
            competition_score=round(factor_scores["competition"], 2),
            commercial_score=round(factor_scores["commercial_potential"], 2),
            seasonality_score=round(factor_scores["seasonality"], 2),
            average_selling_price_score=round(factor_scores["average_selling_price"], 2),
            margin_score=round(factor_scores["profit_margin"], 2),
            portfolio_diversity_score=round(factor_scores["portfolio_diversity"], 2),
            trend_velocity_score=round(factor_scores["trend_velocity"], 2),
            contributions=contributions,
            weakest_factor=weakest_factor.replace("_", " ").title(),
            suggested_improvement=_suggested_improvement(weakest_factor, opportunity),
            expected_revenue=round(expected_price * (0.5 + total / 30), 2),
            expected_conversion=expected_conversion,
            expected_margin=expected_margin,
            expected_risk=_risk_label(opportunity.competition_score, total),
            expected_time_to_first_sale=_time_to_first_sale(total),
            overall_business_score=total,
            selection_outcome=selection_outcome,
        )

    def rank(
        self,
        opportunities: tuple[MarketOpportunity, ...],
    ) -> tuple[tuple[MarketOpportunity, OpportunityScore], ...]:
        """Return candidates ranked deterministically by opportunity score."""
        scored = tuple((item, self.score(item)) for item in opportunities)
        return tuple(
            sorted(
                scored,
                key=lambda pair: (
                    -pair[1].opportunity_score,
                    pair[0].competition_score,
                    pair[0].keyword.casefold(),
                ),
            )
        )


def _clamp(value: float) -> float:
    return min(100.0, max(0.0, float(value)))


def _seasonality_score(season: str, month: int) -> float:
    value = season.casefold()
    if "back to school" in value:
        return 96 if month in {6, 7, 8} else 72
    if "summer" in value:
        return 94 if month in {4, 5, 6, 7} else 70
    if "fall" in value or "autumn" in value or "halloween" in value:
        return 92 if month in {7, 8, 9, 10} else 74
    if "winter" in value or "christmas" in value:
        return 92 if month in {9, 10, 11, 12} else 76
    if "spring" in value:
        return 88 if month in {1, 2, 3, 4} else 68
    if "wedding" in value:
        return 88 if month in {1, 2, 3, 4, 5, 6, 7} else 78
    if "baby" in value or "nursery" in value or "evergreen" in value:
        return 84
    return 80


def _average_selling_price_score(product_type: str) -> float:
    lowered = product_type.casefold()
    if "clipart" in lowered:
        return 92
    if "digital paper" in lowered:
        return 82
    if "party" in lowered or "invitation" in lowered:
        return 88
    if "wall art" in lowered:
        return 76
    if "sticker" in lowered:
        return 72
    return 70


def _profit_margin_score(product_type: str) -> float:
    lowered = product_type.casefold()
    if "digital paper" in lowered or "clipart" in lowered:
        return 94
    if "sticker" in lowered:
        return 90
    if "wall art" in lowered:
        return 88
    if "party" in lowered or "invitation" in lowered:
        return 84
    return 80


def _portfolio_diversity_score(
    opportunity: MarketOpportunity,
    selected_today: tuple[MarketOpportunity, ...],
) -> float:
    if not selected_today:
        return 100
    conflicts = 0
    for selected in selected_today:
        conflicts += int(selected.primary_niche == opportunity.primary_niche)
        conflicts += int(selected.product_type == opportunity.product_type)
        conflicts += int(selected.recommended_artistic_style == opportunity.recommended_artistic_style)
        conflicts += int(selected.target_audience == opportunity.target_audience)
        conflicts += int(selected.season == opportunity.season)
    return max(20.0, 100.0 - conflicts * 16)


def _trend_velocity_score(opportunity: MarketOpportunity) -> float:
    source_bonus = min(8, max(0, len(opportunity.research_sources) - 1) * 2)
    return _clamp(opportunity.trend_score * 0.85 + opportunity.confidence * 0.10 + source_bonus)


def _expected_price(product_type: str) -> float:
    lowered = product_type.casefold()
    if "clipart" in lowered:
        return 6.99
    if "digital paper" in lowered:
        return 4.99
    if "party" in lowered or "invitation" in lowered:
        return 5.49
    if "wall art" in lowered:
        return 3.99
    if "sticker" in lowered:
        return 3.49
    return 3.99


def _suggested_improvement(factor: str, opportunity: MarketOpportunity) -> str:
    if factor == "competition":
        return f"Differentiate into a more specific {opportunity.primary_niche} bundle."
    if factor == "seasonality":
        return f"Reframe for the next buying window instead of {opportunity.season}."
    if factor == "average_selling_price":
        return "Increase perceived value with a larger bundle or premium preview."
    if factor == "portfolio_diversity":
        return "Choose a different style, audience, or category for today's batch."
    if factor == "profit_margin":
        return "Reduce production complexity or package as a higher-margin bundle."
    return "Strengthen keyword evidence and buyer intent before production."


def _risk_label(competition_score: float, opportunity_score: float) -> str:
    if competition_score >= 65 or opportunity_score < 70:
        return "High"
    if competition_score >= 45 or opportunity_score < 82:
        return "Moderate"
    return "Low"


def _time_to_first_sale(opportunity_score: float) -> str:
    if opportunity_score >= 88:
        return "1-2 weeks"
    if opportunity_score >= 78:
        return "2-4 weeks"
    return "4+ weeks"
