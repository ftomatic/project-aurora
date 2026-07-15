"""AI Portfolio Manager for diversified Aurora Etsy planning."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Iterable

from project_aurora.planning.dynamic_product_planner import ProductCandidate
from project_aurora.portfolio.market_segments import (
    classify_market_category,
    normalize_audience,
)
from project_aurora.portfolio.portfolio_memory import PortfolioMemory
from project_aurora.portfolio.style_rotation import PortfolioStyleLibrary
from project_aurora.research.dynamic_market_research import DynamicResearchReport


@dataclass(frozen=True, slots=True)
class PortfolioRules:
    """Diversification and duplicate rules for daily portfolio planning."""

    daily_count: int = 10
    max_per_category: int = 2
    max_per_style: int = 2
    max_per_audience: int = 2
    max_per_season: int = 2
    max_per_product_type: int = 2
    duplicate_threshold: float = 0.80


@dataclass(frozen=True, slots=True)
class ScoredPortfolioCandidate:
    """A product candidate enriched with portfolio intelligence."""

    candidate: ProductCandidate
    market_category: str
    audience: str
    art_style: str
    product_type: str
    season: str
    score: float
    score_breakdown: dict[str, float]
    duplicate_risk: float
    rejected_reason: str = ""

    @property
    def product_name(self) -> str:
        """Return product name."""
        return self.candidate.product_name


@dataclass(frozen=True, slots=True)
class PortfolioPlan:
    """Daily diversified portfolio plan."""

    candidates: tuple[ScoredPortfolioCandidate, ...]
    selected: tuple[ScoredPortfolioCandidate, ...]
    rejected_duplicates: tuple[ScoredPortfolioCandidate, ...]
    wildcard: ScoredPortfolioCandidate | None
    trend_sources_used: tuple[str, ...]
    created_at: datetime = field(default_factory=datetime.now)

    def category_distribution(self) -> dict[str, int]:
        """Return selected category counts."""
        return _distribution(item.market_category for item in self.selected)

    def audience_distribution(self) -> dict[str, int]:
        """Return selected audience counts."""
        return _distribution(item.audience for item in self.selected)

    def style_distribution(self) -> dict[str, int]:
        """Return selected style counts."""
        return _distribution(item.art_style for item in self.selected)

    def product_type_distribution(self) -> dict[str, int]:
        """Return selected product type counts."""
        return _distribution(item.product_type for item in self.selected)

    def to_report(self) -> dict[str, Any]:
        """Return JSON-safe daily portfolio report."""
        demand = _average(item.candidate.demand_score for item in self.selected)
        competition = _average(
            item.candidate.competition_score for item in self.selected
        )
        revenue = sum(
            round(80 + item.candidate.confidence_score * 90, 2)
            for item in self.selected
        )
        return {
            "today_portfolio": [item.product_name for item in self.selected],
            "category_distribution": self.category_distribution(),
            "audience_distribution": self.audience_distribution(),
            "style_distribution": self.style_distribution(),
            "product_type_distribution": self.product_type_distribution(),
            "demand_score": round(demand, 3),
            "competition_score": round(competition, 3),
            "trend_sources_used": list(self.trend_sources_used),
            "rejected_duplicates": [item.product_name for item in self.rejected_duplicates],
            "wildcard_selection": self.wildcard.product_name if self.wildcard else "",
            "estimated_revenue_opportunity": round(revenue, 2),
        }


class AIPortfolioManager:
    """Select a balanced high-opportunity product portfolio."""

    def __init__(
        self,
        rules: PortfolioRules | None = None,
        style_library: PortfolioStyleLibrary | None = None,
    ) -> None:
        self._rules = rules or PortfolioRules()
        self._style_library = style_library or PortfolioStyleLibrary()

    def plan(
        self,
        *,
        candidates: tuple[ProductCandidate, ...],
        research: DynamicResearchReport,
        memory: PortfolioMemory,
        count: int | None = None,
    ) -> PortfolioPlan:
        """Score, de-duplicate, and diversify candidates."""
        limit = count if count is not None else self._rules.daily_count
        scored = tuple(
            sorted(
                (
                    self._score_candidate(candidate, memory)
                    for candidate in candidates
                ),
                key=lambda item: (
                    -item.score,
                    item.duplicate_risk,
                    item.product_name.casefold(),
                ),
            )
        )
        rejected_duplicates = tuple(
            item
            for item in scored
            if item.duplicate_risk >= self._rules.duplicate_threshold
        )
        selected = self._select_balanced(scored, limit)
        wildcard = self._select_wildcard(scored, selected)
        if wildcard and wildcard not in selected and len(selected) < limit:
            selected = (*selected, wildcard)
        return PortfolioPlan(
            candidates=scored,
            selected=selected[:limit],
            rejected_duplicates=rejected_duplicates,
            wildcard=wildcard,
            trend_sources_used=research.providers_used,
        )

    def _score_candidate(
        self,
        candidate: ProductCandidate,
        memory: PortfolioMemory,
    ) -> ScoredPortfolioCandidate:
        category = classify_market_category(
            candidate.product_name,
            candidate.product_type,
            candidate.keywords,
        )
        audience = normalize_audience(candidate.target_customer)
        rotated_style = self._style_library.rotate(
            candidate.style,
            memory.styles_for_category(category),
        )
        duplicate_risk = memory.max_similarity(candidate.product_name)
        competition_opportunity = 1 - candidate.competition_score
        historical_similarity_penalty = duplicate_risk * 0.12
        style_rotation_bonus = 0.05 if rotated_style != candidate.style else 0.0
        breakdown = {
            "demand": candidate.demand_score * 0.18,
            "competition": competition_opportunity * 0.14,
            "trend_velocity": candidate.confidence_score * 0.12,
            "originality": (1 - duplicate_risk) * 0.12,
            "season_timing": _season_score(candidate.season) * 0.08,
            "commercial_potential": candidate.confidence_score * 0.12,
            "keyword_opportunity": _keyword_score(candidate.keywords) * 0.08,
            "portfolio_diversity": _diversity_score(candidate, memory) * 0.08,
            "historical_performance": _historical_performance(category, memory) * 0.04,
            "expected_profitability": _profitability(candidate) * 0.04,
            "style_rotation": style_rotation_bonus,
            "historical_similarity_penalty": -historical_similarity_penalty,
        }
        score = round(max(sum(breakdown.values()), 0.0), 4)
        return ScoredPortfolioCandidate(
            candidate=candidate,
            market_category=category,
            audience=audience,
            art_style=rotated_style,
            product_type=candidate.product_type,
            season=candidate.season,
            score=score,
            score_breakdown=breakdown,
            duplicate_risk=duplicate_risk,
        )

    def _select_balanced(
        self,
        scored: tuple[ScoredPortfolioCandidate, ...],
        limit: int,
    ) -> tuple[ScoredPortfolioCandidate, ...]:
        selected: list[ScoredPortfolioCandidate] = []
        counts: dict[str, Counter[str]] = {
            "category": Counter(),
            "style": Counter(),
            "audience": Counter(),
            "season": Counter(),
            "product_type": Counter(),
        }
        for item in scored:
            if len(selected) >= limit:
                break
            if item.duplicate_risk >= self._rules.duplicate_threshold:
                continue
            if self._would_exceed_limits(item, counts):
                continue
            selected.append(item)
            counts["category"][item.market_category] += 1
            counts["style"][item.art_style] += 1
            counts["audience"][item.audience] += 1
            counts["season"][item.season] += 1
            counts["product_type"][item.product_type] += 1
        if len(selected) >= limit:
            return tuple(selected)
        selected_names = {item.product_name for item in selected}
        for item in scored:
            if len(selected) >= limit:
                break
            if item.product_name in selected_names:
                continue
            if item.duplicate_risk >= self._rules.duplicate_threshold:
                continue
            selected.append(item)
            selected_names.add(item.product_name)
        return tuple(selected)

    def _would_exceed_limits(
        self,
        item: ScoredPortfolioCandidate,
        counts: dict[str, Counter[str]],
    ) -> bool:
        return (
            counts["category"][item.market_category] >= self._rules.max_per_category
            or counts["style"][item.art_style] >= self._rules.max_per_style
            or counts["audience"][item.audience] >= self._rules.max_per_audience
            or counts["season"][item.season] >= self._rules.max_per_season
            or counts["product_type"][item.product_type]
            >= self._rules.max_per_product_type
        )

    def _select_wildcard(
        self,
        scored: tuple[ScoredPortfolioCandidate, ...],
        selected: tuple[ScoredPortfolioCandidate, ...],
    ) -> ScoredPortfolioCandidate | None:
        available = tuple(
            item
            for item in scored
            if item.duplicate_risk < self._rules.duplicate_threshold
        )
        if not available:
            return None
        return max(
            available,
            key=lambda item: (
                item.candidate.confidence_score,
                item.candidate.demand_score,
                -item.candidate.competition_score,
                item.score,
            ),
        )


def _season_score(season: str) -> float:
    lowered = season.casefold()
    if "30" in lowered:
        return 1.0
    if "60" in lowered:
        return 0.86
    if "90" in lowered:
        return 0.75
    if "evergreen" in lowered:
        return 0.7
    return 0.62


def _keyword_score(keywords: tuple[str, ...]) -> float:
    if not keywords:
        return 0.0
    unique = len(tuple(dict.fromkeys(keyword.casefold() for keyword in keywords)))
    return min(unique / 13, 1.0)


def _diversity_score(candidate: ProductCandidate, memory: PortfolioMemory) -> float:
    category = classify_market_category(
        candidate.product_name,
        candidate.product_type,
        candidate.keywords,
    )
    category_count = memory.count_for_dimension("market_category", category)
    style_count = memory.count_for_dimension("art_style", candidate.style)
    return max(1 - ((category_count + style_count) * 0.15), 0.2)


def _historical_performance(category: str, memory: PortfolioMemory) -> float:
    matching = tuple(
        record for record in memory.records if record.market_category == category
    )
    if not matching:
        return 0.65
    sales = sum(record.sales for record in matching)
    published = sum(1 for record in matching if record.published)
    return min(0.55 + published * 0.08 + sales * 0.01, 1.0)


def _profitability(candidate: ProductCandidate) -> float:
    return min(candidate.confidence_score * candidate.demand_score * 1.1, 1.0)


def _distribution(values: Iterable[str]) -> dict[str, int]:
    return dict(sorted(Counter(values).items()))


def _average(values: Iterable[float]) -> float:
    items = tuple(float(value) for value in values)
    if not items:
        return 0.0
    return sum(items) / len(items)
