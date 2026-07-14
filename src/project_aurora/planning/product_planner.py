"""Dynamic product planner for Aurora production jobs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from project_aurora.planning.production_queue_manager import (
    READY,
    ProductionJob,
    ProductionQueueManager,
)
from project_aurora.style_intelligence.style_profile import StyleProfile


@dataclass(frozen=True, slots=True)
class PlanningCandidate:
    """Normalized product opportunity used by the planner."""

    product_name: str
    category: str
    theme: str
    season: str
    demand_score: int
    competition_level: str
    revenue_potential: str
    raw_score: int
    keywords: tuple[str, ...]


class ProductPlanner:
    """Create ranked production jobs from research and style intelligence."""

    def __init__(self, queue_manager: ProductionQueueManager) -> None:
        self._queue_manager = queue_manager

    def plan(
        self,
        research_output: Any,
        style_output: Any,
        top_n: int = 5,
    ) -> tuple[ProductionJob, ...]:
        """Generate and persist the top production jobs."""
        if top_n <= 0:
            return ()

        candidates = self._extract_candidates(research_output)
        if not candidates:
            return ()

        styles = self._extract_styles(style_output)
        existing = self._queue_manager.product_names()
        planned_jobs: list[ProductionJob] = []

        for candidate in self._rank_candidates(candidates, styles):
            if len(planned_jobs) >= top_n:
                break
            if _normalize(candidate.product_name) in existing:
                continue

            style = self._select_style(candidate, styles)
            job = self._queue_manager.add_job(
                priority=self._priority(candidate),
                product_name=candidate.product_name,
                category=candidate.category,
                style=style.style_name if style else "Storybook Watercolor",
                seasonal_theme=candidate.season,
                keywords=candidate.keywords,
                confidence_score=self._confidence_score(candidate, style),
                estimated_competition=candidate.competition_level.title(),
                estimated_demand=self._demand_label(candidate.demand_score),
                estimated_revenue=self._estimated_revenue(candidate),
                status=READY,
            )
            existing.add(_normalize(candidate.product_name))
            planned_jobs.append(job)

        return tuple(planned_jobs)

    def _rank_candidates(
        self,
        candidates: tuple[PlanningCandidate, ...],
        styles: tuple[StyleProfile, ...],
    ) -> tuple[PlanningCandidate, ...]:
        return tuple(
            sorted(
                candidates,
                key=lambda candidate: (
                    -self._confidence_score(
                        candidate,
                        self._select_style(candidate, styles),
                    ),
                    -self._estimated_revenue(candidate),
                    candidate.product_name.casefold(),
                ),
            )
        )

    def _extract_candidates(self, research_output: Any) -> tuple[PlanningCandidate, ...]:
        recommendations = _get_value(research_output, "recommendations", ())
        if not recommendations:
            return ()
        return tuple(
            self._candidate_from_recommendation(recommendation)
            for recommendation in recommendations
        )

    def _candidate_from_recommendation(self, recommendation: Any) -> PlanningCandidate:
        name = _get_str(recommendation, "name")
        category = _get_str(recommendation, "category")
        theme = _get_str(recommendation, "theme", default=name)
        season = _get_str(recommendation, "season", default="Evergreen")
        score = _get_int(recommendation, "score", default=0)
        competition = _get_str(
            recommendation,
            "competition_level",
            default="medium",
        )
        revenue = _get_str(
            recommendation,
            "revenue_potential",
            default="medium",
        )
        demand = _get_int(
            recommendation,
            "demand_score",
            default=_demand_score_from_raw_score(score),
        )
        keywords = _keywords_from(
            name=name,
            category=category,
            theme=theme,
            season=season,
        )
        return PlanningCandidate(
            product_name=name,
            category=category,
            theme=theme,
            season=season,
            demand_score=demand,
            competition_level=competition,
            revenue_potential=revenue,
            raw_score=score,
            keywords=keywords,
        )

    def _extract_styles(self, style_output: Any) -> tuple[StyleProfile, ...]:
        if isinstance(style_output, tuple):
            return tuple(
                style for style in style_output if isinstance(style, StyleProfile)
            )
        styles = _get_value(style_output, "style_profiles", None)
        if styles is None:
            styles = _get_value(style_output, "styles", ())
        return tuple(style for style in styles if isinstance(style, StyleProfile))

    def _select_style(
        self,
        candidate: PlanningCandidate,
        styles: tuple[StyleProfile, ...],
    ) -> StyleProfile | None:
        if not styles:
            return None
        return max(
            styles,
            key=lambda style: (
                self._style_fit(candidate, style),
                style.confidence,
                style.style_name,
            ),
        )

    def _style_fit(
        self,
        candidate: PlanningCandidate,
        style: StyleProfile,
    ) -> float:
        fit = style.confidence * 20
        category = candidate.category.casefold()
        theme = candidate.theme.casefold()
        season = candidate.season.casefold()
        if any(
            category in product.casefold() or product.casefold() in category
            for product in style.recommended_products
        ):
            fit += 24
        if any(season == item.casefold() for item in style.recommended_seasons):
            fit += 18
        style_words = " ".join(
            (
                style.style_name,
                style.description,
                " ".join(style.visual_characteristics),
                " ".join(style.color_palette),
            )
        ).casefold()
        fit += sum(3 for word in theme.split() if word in style_words)
        return fit

    def _confidence_score(
        self,
        candidate: PlanningCandidate,
        style: StyleProfile | None,
    ) -> float:
        demand = min(candidate.demand_score, 10) / 10
        competition = {
            "low": 1.0,
            "medium": 0.74,
            "high": 0.48,
        }.get(candidate.competition_level.casefold(), 0.65)
        revenue = {
            "high": 1.0,
            "medium": 0.75,
            "low": 0.45,
        }.get(candidate.revenue_potential.casefold(), 0.65)
        research_score = min(candidate.raw_score, 120) / 120 if candidate.raw_score else demand
        style_score = style.confidence if style else 0.82
        confidence = (
            demand * 0.28
            + competition * 0.2
            + revenue * 0.18
            + research_score * 0.22
            + style_score * 0.12
        )
        return round(min(confidence, 0.99), 2)

    @staticmethod
    def _estimated_revenue(candidate: PlanningCandidate) -> float:
        base = {"high": 120.0, "medium": 75.0, "low": 35.0}.get(
            candidate.revenue_potential.casefold(),
            60.0,
        )
        demand_bonus = max(candidate.demand_score - 6, 0) * 8
        competition_bonus = {
            "low": 20.0,
            "medium": 8.0,
            "high": -8.0,
        }.get(candidate.competition_level.casefold(), 0.0)
        return round(max(base + demand_bonus + competition_bonus, 0), 2)

    @staticmethod
    def _priority(candidate: PlanningCandidate) -> str:
        if candidate.demand_score >= 8 and candidate.competition_level.casefold() == "low":
            return "High"
        if candidate.demand_score >= 7:
            return "Medium"
        return "Low"

    @staticmethod
    def _demand_label(demand_score: int) -> str:
        if demand_score >= 8:
            return "High"
        if demand_score >= 6:
            return "Medium"
        return "Low"


def _get_value(source: Any, field_name: str, default: Any = None) -> Any:
    if isinstance(source, Mapping):
        return source.get(field_name, default)
    return getattr(source, field_name, default)


def _get_str(source: Any, field_name: str, default: str | None = None) -> str:
    value = _get_value(source, field_name, default)
    if value is None or not str(value).strip():
        raise ValueError(f"Research field is required: {field_name}.")
    return str(value)


def _get_int(source: Any, field_name: str, default: int = 0) -> int:
    value = _get_value(source, field_name, default)
    return int(value)


def _demand_score_from_raw_score(score: int) -> int:
    if score >= 100:
        return 9
    if score >= 85:
        return 8
    if score >= 70:
        return 7
    if score >= 55:
        return 6
    return 5


def _keywords_from(
    name: str,
    category: str,
    theme: str,
    season: str,
) -> tuple[str, ...]:
    words: list[str] = []
    for value in (name, category, theme, season):
        for word in value.replace("-", " ").split():
            cleaned = word.strip(" ,").casefold()
            if len(cleaned) >= 3 and cleaned not in words:
                words.append(cleaned)
    return tuple(words[:10])


def _normalize(value: str) -> str:
    return " ".join(value.casefold().strip().split())
