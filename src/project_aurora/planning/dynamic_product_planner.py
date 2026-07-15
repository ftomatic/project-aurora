"""Daily dynamic product planner for Aurora."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from difflib import SequenceMatcher

from project_aurora.config.project_profile import ProjectProfile
from project_aurora.planning.production_queue_manager import (
    READY,
    ProductionJob,
    ProductionQueueManager,
)
from project_aurora.research.dynamic_market_research import DynamicResearchReport, MarketSignal


@dataclass(frozen=True, slots=True)
class ProductCandidate:
    """Rankable daily product opportunity."""

    product_name: str
    product_type: str
    target_customer: str
    style: str
    season: str
    keywords: tuple[str, ...]
    demand_score: float
    competition_score: float
    confidence_score: float
    source_evidence: tuple[str, ...]
    duplicate_risk: float = 0.0
    created_at: datetime = field(default_factory=datetime.now)


@dataclass(frozen=True, slots=True)
class DailyPlanningResult:
    """Daily planner output."""

    candidates: tuple[ProductCandidate, ...]
    selected: tuple[ProductCandidate, ...]
    duplicates_rejected: tuple[str, ...]


class DynamicProductPlanner:
    """Generate and persist daily non-duplicate production jobs."""

    def __init__(
        self,
        queue_manager: ProductionQueueManager,
        project_profile: ProjectProfile,
        duplicate_threshold: float = 0.80,
        id_factory: callable | None = None,
    ) -> None:
        self._queue_manager = queue_manager
        self._project_profile = project_profile
        self._duplicate_threshold = duplicate_threshold
        self._id_factory = id_factory

    def plan(
        self,
        research: DynamicResearchReport,
        count: int,
    ) -> DailyPlanningResult:
        """Generate candidates and add exactly count READY jobs when possible."""
        candidates = self.generate_candidates(research)
        existing_names = self._existing_names()
        selected: list[ProductCandidate] = []
        rejected: list[str] = []
        for candidate in self.rank_candidates(candidates):
            if len(selected) >= count:
                break
            duplicate_risk = self._max_similarity(
                candidate.product_name,
                tuple(existing_names) + tuple(item.product_name for item in selected),
            )
            if duplicate_risk >= self._duplicate_threshold:
                rejected.append(candidate.product_name)
                continue
            selected.append(candidate)

        for candidate in selected:
            self._queue_manager.add_job(
                priority="High" if candidate.confidence_score >= 0.86 else "Medium",
                product_name=candidate.product_name,
                category=candidate.product_type,
                style=candidate.style,
                seasonal_theme=candidate.season,
                keywords=candidate.keywords,
                confidence_score=round(candidate.confidence_score, 2),
                estimated_competition=_competition_label(candidate.competition_score),
                estimated_demand=_demand_label(candidate.demand_score),
                estimated_revenue=round(80 + candidate.confidence_score * 90, 2),
                status=READY,
                target_customer=candidate.target_customer,
                demand_score=candidate.demand_score,
                competition_score=candidate.competition_score,
                source_evidence=candidate.source_evidence,
            )
        return DailyPlanningResult(
            candidates=candidates,
            selected=tuple(selected),
            duplicates_rejected=tuple(rejected),
        )

    def generate_candidates(
        self,
        research: DynamicResearchReport,
        minimum: int = 30,
    ) -> tuple[ProductCandidate, ...]:
        """Generate at least minimum candidates from research signals."""
        variants = (
            "Clipart Bundle",
            "Digital Paper Pack",
            "Party Printable Set",
            "Sticker Sheet",
            "Wall Art Print",
            "Junk Journal Kit",
        )
        candidates: list[ProductCandidate] = []
        for signal in research.signals:
            for variant in variants:
                product_type = _allowed_product_type(variant, self._project_profile)
                if product_type is None:
                    continue
                phrase = signal.trend_phrase.title()
                name = f"{phrase} {variant}"
                confidence = _confidence(signal, product_type)
                candidates.append(
                    ProductCandidate(
                        product_name=name,
                        product_type=product_type,
                        target_customer=signal.target_customer,
                        style=signal.recommended_style,
                        season=signal.seasonal_timing,
                        keywords=_keywords(signal, variant),
                        demand_score=signal.estimated_demand,
                        competition_score=signal.estimated_competition,
                        confidence_score=confidence,
                        source_evidence=(f"{signal.source}: {signal.trend_phrase}",),
                    )
                )
        while candidates and len(candidates) < minimum:
            base = candidates[len(candidates) % len(candidates)]
            index = len(candidates) + 1
            candidates.append(
                ProductCandidate(
                    product_name=f"{base.product_name} Vol {index}",
                    product_type=base.product_type,
                    target_customer=base.target_customer,
                    style=base.style,
                    season=base.season,
                    keywords=base.keywords + (f"vol {index}",),
                    demand_score=max(base.demand_score - 0.02, 0),
                    competition_score=base.competition_score,
                    confidence_score=max(base.confidence_score - 0.01, 0),
                    source_evidence=base.source_evidence,
                )
            )
        return tuple(candidates)

    def rank_candidates(
        self,
        candidates: tuple[ProductCandidate, ...],
    ) -> tuple[ProductCandidate, ...]:
        """Rank candidates by commercial usefulness and originality."""
        return tuple(
            sorted(
                candidates,
                key=lambda candidate: (
                    -candidate.confidence_score,
                    candidate.competition_score,
                    candidate.product_name.casefold(),
                ),
            )
        )

    def _existing_names(self) -> set[str]:
        return {job.product_name for job in self._queue_manager.list_jobs()}

    def _max_similarity(self, product_name: str, existing_names: tuple[str, ...]) -> float:
        if not existing_names:
            return 0.0
        normalized = _normalize(product_name)
        return max(
            _similarity(normalized, _normalize(existing))
            for existing in existing_names
        )


def _allowed_product_type(variant: str, profile: ProjectProfile) -> str | None:
    lowered = variant.casefold()
    for allowed in profile.allowed_product_types:
        if allowed in lowered:
            return allowed
    if "party" in lowered and "party printable" in profile.allowed_product_types:
        return "party printable"
    return None


def _confidence(signal: MarketSignal, product_type: str) -> float:
    type_bonus = 0.05 if product_type in {"clipart", "party printable"} else 0.0
    score = (
        signal.estimated_demand * 0.36
        + (1 - signal.estimated_competition) * 0.24
        + signal.confidence_score * 0.3
        + type_bonus
    )
    return round(min(score, 0.99), 3)


def _keywords(signal: MarketSignal, variant: str) -> tuple[str, ...]:
    words = tuple(
        item
        for item in (*signal.keywords, *variant.casefold().split())
        if item
    )
    return tuple(dict.fromkeys(words))[:13]


def _normalize(value: str) -> str:
    return " ".join(value.casefold().replace("-", " ").split())


def _similarity(left: str, right: str) -> float:
    if left == right:
        return 1.0
    left_tokens = set(left.split())
    right_tokens = set(right.split())
    if not left_tokens or not right_tokens:
        return 0.0
    jaccard = len(left_tokens & right_tokens) / len(left_tokens | right_tokens)
    sequence = SequenceMatcher(None, left, right).ratio()
    return round(jaccard * sequence, 3)


def _competition_label(score: float) -> str:
    if score < 0.4:
        return "Low"
    if score < 0.7:
        return "Medium"
    return "High"


def _demand_label(score: float) -> str:
    if score >= 0.75:
        return "High"
    if score >= 0.5:
        return "Medium"
    return "Low"
