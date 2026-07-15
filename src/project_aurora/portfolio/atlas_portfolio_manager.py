"""Atlas portfolio manager for research-backed production decisions."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from difflib import SequenceMatcher
from typing import Any, Iterable

from project_aurora.planning.production_queue_manager import ProductionQueueManager
from project_aurora.research.market_opportunity import MarketOpportunity
from project_aurora.research.research_config import ResearchPlannerConfig
from project_aurora.storage.memory_manager import MemoryManager


_ABSOLUTE_MINIMUM_CONFIDENCE = 85


@dataclass(frozen=True, slots=True)
class RelaxationStage:
    """One controlled Atlas replacement-search stage."""

    relaxed_rules: frozenset[str]
    relaxed_label: str


@dataclass(frozen=True, slots=True)
class BusinessDecision:
    """Written business justification for one selected product."""

    product: str
    business_reason: str
    trend_summary: str
    target_customer: str
    competition: str
    demand: str
    commercial_opportunity: str
    expected_search_intent: str
    recommended_price: float
    recommended_bundle_opportunities: tuple[str, ...]
    suggested_boards: tuple[str, ...]
    suggested_instagram_theme: str
    confidence_score: float
    research_sources: tuple[str, ...]
    reason_selected: str

    def to_dict(self) -> dict[str, Any]:
        """Return JSON-safe decision data."""
        return {
            "product": self.product,
            "business_reason": self.business_reason,
            "trend_summary": self.trend_summary,
            "target_customer": self.target_customer,
            "competition": self.competition,
            "demand": self.demand,
            "commercial_opportunity": self.commercial_opportunity,
            "expected_search_intent": self.expected_search_intent,
            "recommended_price": self.recommended_price,
            "recommended_bundle_opportunities": list(
                self.recommended_bundle_opportunities
            ),
            "suggested_boards": list(self.suggested_boards),
            "suggested_instagram_theme": self.suggested_instagram_theme,
            "confidence_score": self.confidence_score,
            "research_sources": list(self.research_sources),
            "reason_selected": self.reason_selected,
        }


@dataclass(frozen=True, slots=True)
class AtlasPortfolioPlan:
    """Atlas daily portfolio output."""

    selected: tuple[MarketOpportunity, ...]
    rejected: tuple[tuple[MarketOpportunity, str], ...]
    decisions: tuple[BusinessDecision, ...]
    average_confidence: float
    quality_gate_passed: bool
    quality_gate: dict[str, Any]
    constraint_relaxations: tuple[dict[str, str], ...]
    selection_failure_reasons: tuple[str, ...]
    provider_status: tuple[dict[str, Any], ...]
    created_at: datetime = field(default_factory=datetime.now)

    def diversity(self) -> dict[str, dict[str, int]]:
        """Return portfolio diversity distributions."""
        return {
            "niche": _distribution(item.primary_niche for item in self.selected),
            "audience": _distribution(item.target_audience for item in self.selected),
            "style": _distribution(
                item.recommended_artistic_style for item in self.selected
            ),
            "season": _distribution(item.season for item in self.selected),
            "product_type": _distribution(item.product_type for item in self.selected),
        }

    def to_report(self) -> dict[str, Any]:
        """Return JSON-safe daily research report."""
        return {
            "todays_research": {
                "candidates": len(self.selected) + len(self.rejected),
                "created_at": self.created_at.isoformat(),
            },
            "top_trends": [item.keyword for item in self.selected],
            "emerging_niches": list(self.diversity()["niche"].keys()),
            "categories_rejected": sorted(
                {
                    opportunity.primary_niche
                    for opportunity, reason in self.rejected
                    if "limit" in reason.casefold()
                }
            ),
            "products_selected": [item.keyword for item in self.selected],
            "products_rejected": [
                {"product": opportunity.keyword, "reason": reason}
                for opportunity, reason in self.rejected
            ],
            "provider_status": list(self.provider_status),
            "portfolio_diversity": self.diversity(),
            "average_confidence": self.average_confidence,
            "quality_gate_passed": self.quality_gate_passed,
            "quality_gate": self.quality_gate,
            "constraint_relaxations": list(self.constraint_relaxations),
            "selection_failure_reasons": list(self.selection_failure_reasons),
            "business_decision_report": [
                decision.to_dict() for decision in self.decisions
            ],
        }


class AtlasPortfolioManager:
    """Build exactly five research-backed products with strict diversity."""

    def __init__(
        self,
        config: ResearchPlannerConfig | None = None,
        queue_manager: ProductionQueueManager | None = None,
        memory: MemoryManager | None = None,
    ) -> None:
        self._config = config or ResearchPlannerConfig()
        self._queue_manager = queue_manager or ProductionQueueManager()
        self._memory = memory or MemoryManager()

    def build_portfolio(
        self,
        opportunities: tuple[MarketOpportunity, ...],
        provider_status: tuple[dict[str, Any], ...] = (),
    ) -> AtlasPortfolioPlan:
        """Select today's five-product research-backed portfolio."""
        duplicates = self._duplicate_names()
        ranked = tuple(sorted(opportunities, key=_score_key))
        selected: list[MarketOpportunity] = []
        rejected: list[tuple[MarketOpportunity, str]] = []
        counts: dict[str, Counter[str]] = {
            "niche": Counter(),
            "style": Counter(),
            "audience": Counter(),
            "season": Counter(),
            "product_type": Counter(),
        }
        selected_ids: set[str] = set()
        relaxations: list[dict[str, str]] = []
        rejected_by_id: dict[str, tuple[MarketOpportunity, str]] = {}
        duplicate_failures: set[str] = set()
        confidence_failures: set[str] = set()

        for stage in _relaxation_stages():
            if stage.relaxed_label and _has_remaining_candidates(
                ranked,
                selected_ids,
                duplicates,
                self._config.duplicate_threshold,
            ):
                relaxations.append(
                    {
                        "constraint": stage.relaxed_label,
                        "reason": "Required to fill the configured 5-product portfolio.",
                    }
                )
            for opportunity in ranked:
                if len(selected) >= self._config.daily_products:
                    break
                if opportunity.id in selected_ids:
                    continue
                duplicate_risk = _max_similarity(opportunity.keyword, duplicates)
                if duplicate_risk >= self._config.duplicate_threshold:
                    duplicate_failures.add(opportunity.keyword)
                    rejected_by_id[opportunity.id] = (
                        opportunity,
                        "Duplicate historical product",
                    )
                    continue
                if opportunity.confidence < _ABSOLUTE_MINIMUM_CONFIDENCE:
                    confidence_failures.add(opportunity.keyword)
                    rejected_by_id[opportunity.id] = (
                        opportunity,
                        "Below strict 85% product confidence minimum",
                    )
                    continue
                limit_reason = self._limit_reason(
                    opportunity,
                    counts,
                    relaxed_rules=stage.relaxed_rules,
                )
                if limit_reason:
                    rejected_by_id[opportunity.id] = (opportunity, limit_reason)
                    continue
                selected.append(opportunity)
                selected_ids.add(opportunity.id)
                _increment_counts(counts, opportunity)
            if len(selected) >= self._config.daily_products:
                break

        average = _average(item.confidence for item in selected)
        quality_gate = _quality_gate(
            selected=tuple(selected),
            required_products=self._config.daily_products,
            minimum_confidence=self._config.minimum_confidence,
            duplicate_failures=(),
        )
        quality_gate_passed = bool(quality_gate["status"] == "READY_FOR_APPROVAL")
        decisions = tuple(_decision(item) for item in selected)
        rejected = tuple(rejected_by_id.values())
        failure_reasons = _selection_failure_reasons(
            selected_count=len(selected),
            required_count=self._config.daily_products,
            rejected=rejected,
            duplicate_failures=tuple(duplicate_failures),
            confidence_failures=tuple(confidence_failures),
        )
        return AtlasPortfolioPlan(
            selected=tuple(selected),
            rejected=rejected,
            decisions=decisions,
            average_confidence=round(average, 2),
            quality_gate_passed=quality_gate_passed,
            quality_gate=quality_gate,
            constraint_relaxations=tuple(relaxations),
            selection_failure_reasons=failure_reasons,
            provider_status=provider_status,
        )

    def save_report(self, plan: AtlasPortfolioPlan) -> str:
        """Save the Atlas report to runtime memory."""
        return self._memory.save_record(
            "daily_research_reports",
            "latest",
            plan.to_report(),
        )

    def _limit_reason(
        self,
        opportunity: MarketOpportunity,
        counts: dict[str, Counter[str]],
        relaxed_rules: frozenset[str] = frozenset(),
    ) -> str:
        if counts["niche"][opportunity.primary_niche] >= self._config.max_per_category:
            return "Niche limit reached"
        if (
            counts["style"][opportunity.recommended_artistic_style]
            >= self._config.max_per_style
            and "style" not in relaxed_rules
        ):
            return "Artistic style limit reached"
        if (
            counts["audience"][opportunity.target_audience] >= self._config.max_per_audience
            and "audience" not in relaxed_rules
        ):
            return "Audience limit reached"
        if (
            counts["season"][opportunity.season] >= self._config.max_per_season
            and "season" not in relaxed_rules
        ):
            return "Season limit reached"
        if (
            counts["product_type"][opportunity.product_type]
            >= self._config.max_per_product_type
            and "product_type" not in relaxed_rules
        ):
            return "Product type limit reached"
        return ""

    def _duplicate_names(self) -> tuple[str, ...]:
        queue_names = tuple(job.product_name for job in self._queue_manager.list_jobs())
        memory_names: list[str] = []
        for collection in (
            "daily_research_reports",
            "etsy_drafts",
            "etsy_complete_drafts",
            "production_reports",
        ):
            try:
                keys = self._memory.list_records(collection)
            except (FileNotFoundError, ValueError):
                keys = ()
            for key in keys:
                try:
                    record = self._memory.load_record(collection, key)
                except (FileNotFoundError, ValueError):
                    continue
                memory_names.extend(_extract_names(record))
        return tuple(dict.fromkeys((*queue_names, *memory_names)))


def _decision(opportunity: MarketOpportunity) -> BusinessDecision:
    demand = _demand_label(opportunity.trend_score)
    competition = _competition_label(opportunity.competition_score)
    return BusinessDecision(
        product=opportunity.keyword.title(),
        business_reason=(
            f"{opportunity.keyword.title()} is supported by "
            f"{', '.join(opportunity.research_sources)} and fits the "
            f"{opportunity.primary_niche} niche for {opportunity.target_audience}."
        ),
        trend_summary=(
            f"Trend score {opportunity.trend_score:.0f}/100 with "
            f"{opportunity.season} timing."
        ),
        target_customer=opportunity.target_audience,
        competition=competition,
        demand=demand,
        commercial_opportunity=(
            f"{opportunity.commercial_potential:.0f}/100 commercial potential "
            f"for {opportunity.product_type}."
        ),
        expected_search_intent=(
            f"Buyers searching for {opportunity.keyword} as an Etsy digital download."
        ),
        recommended_price=1.99,
        recommended_bundle_opportunities=_bundle_opportunities(opportunity),
        suggested_boards=(
            f"{opportunity.primary_niche} Printables",
            f"{opportunity.season} Digital Downloads",
        ),
        suggested_instagram_theme=(
            f"{opportunity.recommended_artistic_style} {opportunity.primary_niche}"
        ),
        confidence_score=opportunity.confidence,
        research_sources=opportunity.research_sources,
        reason_selected=(
            f"{demand} demand. {competition} competition. "
            "Complements existing shop. Different audience or niche than "
            "today's other products. Strong seasonal timing."
        ),
    )


def _bundle_opportunities(opportunity: MarketOpportunity) -> tuple[str, ...]:
    product_type = opportunity.product_type.casefold()
    if "party" in product_type:
        return ("invitations", "cupcake toppers", "favor tags", "thank-you cards")
    if "clipart" in product_type:
        return ("individual PNGs", "commercial clipart set", "matching digital paper")
    if "digital paper" in product_type:
        return ("12 seamless papers", "matching clipart", "scrapbook bundle")
    if "wall art" in product_type:
        return ("single print", "gallery wall trio", "matching greeting card")
    if "sticker" in product_type:
        return ("planner stickers", "icon sheet", "seasonal label set")
    return ("core product", "matching add-on", "seasonal expansion")


def _relaxation_stages() -> tuple[RelaxationStage, ...]:
    """Return controlled relaxation order after strict replacement search."""
    return (
        RelaxationStage(frozenset(), ""),
        RelaxationStage(frozenset({"product_type"}), "Allow second product type"),
        RelaxationStage(
            frozenset({"product_type", "season"}),
            "Allow second season",
        ),
        RelaxationStage(
            frozenset({"product_type", "season", "audience"}),
            "Allow second audience",
        ),
        RelaxationStage(
            frozenset({"product_type", "season", "audience", "style"}),
            "Allow second artistic style",
        ),
    )


def _increment_counts(
    counts: dict[str, Counter[str]],
    opportunity: MarketOpportunity,
) -> None:
    counts["niche"][opportunity.primary_niche] += 1
    counts["style"][opportunity.recommended_artistic_style] += 1
    counts["audience"][opportunity.target_audience] += 1
    counts["season"][opportunity.season] += 1
    counts["product_type"][opportunity.product_type] += 1


def _has_remaining_candidates(
    ranked: tuple[MarketOpportunity, ...],
    selected_ids: set[str],
    duplicates: tuple[str, ...],
    duplicate_threshold: float,
) -> bool:
    return any(
        item.id not in selected_ids
        and item.confidence >= _ABSOLUTE_MINIMUM_CONFIDENCE
        and _max_similarity(item.keyword, duplicates) < duplicate_threshold
        for item in ranked
    )


def _quality_gate(
    *,
    selected: tuple[MarketOpportunity, ...],
    required_products: int,
    minimum_confidence: float,
    duplicate_failures: tuple[str, ...],
) -> dict[str, Any]:
    average = round(_average(item.confidence for item in selected), 2)
    portfolio_size_pass = len(selected) == required_products
    product_confidence_pass = all(
        item.confidence >= _ABSOLUTE_MINIMUM_CONFIDENCE for item in selected
    )
    average_confidence_pass = average >= minimum_confidence
    duplicate_check_pass = not duplicate_failures
    confidence_pass = product_confidence_pass and average_confidence_pass
    status = "READY_FOR_APPROVAL"
    if not (
        portfolio_size_pass
        and confidence_pass
        and duplicate_check_pass
    ):
        status = "QUALITY_GATE_BLOCKED"
    return {
        "required_products": required_products,
        "selected_products": len(selected),
        "portfolio_size": "PASS" if portfolio_size_pass else "FAIL",
        "minimum_confidence": minimum_confidence,
        "average_confidence": average,
        "confidence": "PASS" if confidence_pass else "FAIL",
        "product_confidence": "PASS" if product_confidence_pass else "FAIL",
        "duplicate_check": "PASS" if duplicate_check_pass else "FAIL",
        "status": status,
    }


def _selection_failure_reasons(
    *,
    selected_count: int,
    required_count: int,
    rejected: tuple[tuple[MarketOpportunity, str], ...],
    duplicate_failures: tuple[str, ...],
    confidence_failures: tuple[str, ...],
) -> tuple[str, ...]:
    reasons: list[str] = []
    if selected_count < required_count:
        reasons.append(
            f"Only {selected_count} of {required_count} required products could be selected."
        )
    if duplicate_failures:
        reasons.append(
            "Duplicate prevention blocked: " + ", ".join(sorted(duplicate_failures))
        )
    if confidence_failures:
        reasons.append(
            "Below 85% confidence blocked: " + ", ".join(sorted(confidence_failures))
        )
    blocked_constraints = sorted({reason for _, reason in rejected if "limit" in reason.casefold()})
    for reason in blocked_constraints:
        reasons.append(f"Constraint prevented selection: {reason}.")
    return tuple(reasons)


def _score_key(item: MarketOpportunity) -> tuple[float, float, float, str]:
    score = (
        item.trend_score * 0.28
        + (100 - item.competition_score) * 0.18
        + item.commercial_potential * 0.26
        + item.confidence * 0.28
    )
    return (-score, item.competition_score, item.keyword.casefold())


def _demand_label(score: float) -> str:
    if score >= 88:
        return "High"
    if score >= 75:
        return "Moderate"
    return "Low"


def _competition_label(score: float) -> str:
    if score < 38:
        return "Low"
    if score < 55:
        return "Moderate"
    return "High"


def _distribution(values: Iterable[str]) -> dict[str, int]:
    return dict(sorted(Counter(values).items()))


def _average(values: Iterable[float]) -> float:
    items = tuple(values)
    if not items:
        return 0.0
    return sum(items) / len(items)


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


def _max_similarity(product_name: str, existing_names: tuple[str, ...]) -> float:
    if not existing_names:
        return 0.0
    normalized = _normalize(product_name)
    return max(_similarity(normalized, _normalize(name)) for name in existing_names)


def _extract_names(value: Any) -> list[str]:
    names: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {"products_rejected", "top_trends", "opportunities", "provider_status"}:
                continue
            if key == "products_selected" and isinstance(item, list):
                names.extend(str(name) for name in item if isinstance(name, str))
                continue
            if key in {"product", "product_name", "listing"} and isinstance(item, str):
                names.append(item)
            else:
                names.extend(_extract_names(item))
    elif isinstance(value, list):
        for item in value:
            names.extend(_extract_names(item))
    return names
