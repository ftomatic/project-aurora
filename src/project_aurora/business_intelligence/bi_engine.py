"""Business Intelligence and Learning Engine."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any, Iterable

from project_aurora.business_intelligence.bi_models import (
    ABTestExperiment,
    BusinessRecommendation,
    CollectionAnalytics,
    ExecutiveInsights,
    LearningProposal,
    ListingPerformanceRecord,
    ListingRecord,
    PatternObservation,
    PerformanceMetrics,
    ProductScoreEvolution,
)
from project_aurora.storage.memory_manager import MemoryManager


LISTINGS = "business_listings"
PERFORMANCE = "business_performance"
PERFORMANCE_HISTORY = "business_performance_history"
SCORE_EVOLUTION = "business_score_evolution"
PATTERNS = "business_patterns"
EXPERIMENTS = "business_experiments"
RECOMMENDATIONS = "business_recommendations"
COLLECTION_ANALYTICS = "business_collection_analytics"
EXECUTIVE_INSIGHTS = "business_executive_insights"
LEARNING_PROPOSALS = "business_learning_proposals"


class BusinessIntelligenceEngine:
    """Collect performance data and produce merchandising learning."""

    def __init__(
        self,
        memory: MemoryManager | None = None,
        minimum_confidence: float = 80,
        minimum_sample_size: int = 5,
    ) -> None:
        self._memory = memory or MemoryManager()
        self._minimum_confidence = minimum_confidence
        self._minimum_sample_size = minimum_sample_size

    def record_listing(self, listing: ListingRecord) -> str:
        """Persist listing metadata."""
        self._memory.save_record(LISTINGS, listing.listing_id, listing.to_dict())
        return listing.listing_id

    def record_performance(
        self,
        listing_id: str,
        metrics: PerformanceMetrics,
        *,
        research_score: float = 0.0,
        creative_score: float = 0.0,
        thumbnail_score: float = 0.0,
        seo_score: float = 0.0,
        merchant_qa: float = 0.0,
    ) -> ListingPerformanceRecord:
        """Persist performance metrics and score evolution."""
        listing = ListingRecord.from_dict(self._memory.load_record(LISTINGS, listing_id))
        evolution = ProductScoreEvolution(
            listing_id=listing_id,
            research_score=research_score,
            creative_score=creative_score,
            thumbnail_score=thumbnail_score,
            seo_score=seo_score,
            merchant_qa=merchant_qa,
            performance_score=_performance_score(metrics),
        )
        record = ListingPerformanceRecord(
            listing=listing,
            metrics=metrics,
            score_evolution=evolution,
        )
        timestamp_key = f"{listing_id}_{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
        self._memory.save_record(PERFORMANCE, listing_id, record.to_dict())
        self._memory.save_record(PERFORMANCE_HISTORY, timestamp_key, record.to_dict())
        self._memory.save_record(SCORE_EVOLUTION, listing_id, evolution.to_dict())
        return record

    def performance_records(self) -> tuple[ListingPerformanceRecord, ...]:
        """Load latest performance records."""
        records: list[ListingPerformanceRecord] = []
        for data in _records(self._memory, PERFORMANCE):
            try:
                records.append(_performance_record_from_dict(data))
            except (KeyError, TypeError, ValueError):
                continue
        return tuple(records)

    def discover_patterns(self) -> tuple[PatternObservation, ...]:
        """Discover evidence-backed performance patterns."""
        records = self.performance_records()
        observations: list[PatternObservation] = []
        observations.extend(_group_pattern(records, "style", "conversion_rate", "style"))
        observations.extend(_group_pattern(records, "category", "revenue", "category"))
        observations.extend(_bundle_pattern(records))
        observations.extend(_group_pattern(records, "thumbnail_layout", "favorites", "thumbnail layout"))
        for index, observation in enumerate(observations, start=1):
            self._memory.save_record(PATTERNS, f"pattern_{index}", observation.to_dict())
        return tuple(observations)

    def create_experiment(self, experiment: ABTestExperiment) -> ABTestExperiment:
        """Save an A/B test experiment."""
        self._memory.save_record(EXPERIMENTS, experiment.experiment_id, experiment.to_dict())
        return experiment

    def evaluate_experiment(self, experiment_id: str) -> ABTestExperiment:
        """Evaluate and persist an experiment outcome."""
        experiment = _experiment_from_dict(self._memory.load_record(EXPERIMENTS, experiment_id))
        evaluated = experiment.evaluate()
        self._memory.save_record(EXPERIMENTS, experiment_id, evaluated.to_dict())
        return evaluated

    def generate_recommendations(self) -> tuple[BusinessRecommendation, ...]:
        """Generate weekly merchandising recommendations."""
        records = self.performance_records()
        patterns = self.discover_patterns()
        recommendations: list[BusinessRecommendation] = []
        best_style = _best_group(records, "style", "conversion_rate")
        if best_style:
            recommendations.append(
                _recommendation(
                    f"Increase {best_style[0]} products.",
                    best_style,
                    "creative_style",
                    f"{best_style[0]} has the strongest conversion evidence.",
                )
            )
        weak_category = _weak_group(records, "category", "conversion_rate")
        if weak_category:
            recommendations.append(
                _recommendation(
                    f"Reduce generic {weak_category[0]} products.",
                    weak_category,
                    "publishing_priority",
                    f"{weak_category[0]} underperforms on conversion.",
                )
            )
        best_collection = _best_group(records, "collection_id", "revenue")
        if best_collection:
            recommendations.append(
                _recommendation(
                    f"Create more {best_collection[0]} collection extensions.",
                    best_collection,
                    "opportunity_weights",
                    f"{best_collection[0]} has the strongest revenue evidence.",
                )
            )
        if patterns:
            strongest = max(patterns, key=lambda item: item.confidence)
            recommendations.append(
                BusinessRecommendation(
                    recommendation=strongest.observation,
                    confidence=strongest.confidence,
                    sample_size=strongest.sample_size,
                    supporting_evidence=strongest.supporting_evidence,
                    reasoning=strongest.comparison,
                    action_type="pricing_suggestions",
                )
            )
        for index, recommendation in enumerate(recommendations, start=1):
            self._memory.save_record(RECOMMENDATIONS, f"recommendation_{index}", recommendation.to_dict())
        return tuple(recommendations)

    def collection_analytics(self) -> tuple[CollectionAnalytics, ...]:
        """Return analytics by collection."""
        records = self.performance_records()
        grouped = _group_records(records, "collection_id")
        analytics: list[CollectionAnalytics] = []
        for collection_id, items in grouped.items():
            revenue = round(sum(item.metrics.revenue for item in items), 2)
            analytics.append(
                CollectionAnalytics(
                    collection_id=collection_id,
                    revenue=revenue,
                    conversion=_avg(item.metrics.conversion_rate for item in items),
                    average_order_value=_avg(item.metrics.average_order_value for item in items),
                    cross_sells=sum(1 for item in items if item.metrics.orders > 1),
                    completion=100.0 if all(item.listing.status == "PUBLISHED" for item in items) else 50.0,
                    growth_trend="Growing" if revenue > 0 and len(items) >= 2 else "Early",
                )
            )
        for item in analytics:
            self._memory.save_record(COLLECTION_ANALYTICS, item.collection_id, item.to_dict())
        return tuple(sorted(analytics, key=lambda item: (-item.revenue, item.collection_id)))

    def executive_insights(self) -> ExecutiveInsights:
        """Return high-level BI insights."""
        records = self.performance_records()
        insights = ExecutiveInsights(
            top_performing_style=_best_name(records, "style", "conversion_rate"),
            fastest_growing_category=_best_name(records, "category", "orders"),
            highest_revenue_collection=_best_name(records, "collection_id", "revenue"),
            most_profitable_blueprint=_best_name(records, "blueprint", "revenue"),
            most_effective_thumbnail_layout=_best_name(records, "thumbnail_layout", "favorites"),
        )
        self._memory.save_record(EXECUTIVE_INSIGHTS, "latest", insights.to_dict())
        return insights

    def propose_strategy_adjustments(self) -> tuple[LearningProposal, ...]:
        """Return safe strategy-adjustment proposals when evidence is sufficient."""
        recommendations = self.generate_recommendations()
        proposals: list[LearningProposal] = []
        for recommendation in recommendations:
            approved = (
                recommendation.confidence >= self._minimum_confidence
                and recommendation.sample_size >= self._minimum_sample_size
            )
            proposal = LearningProposal(
                adjustment_type=recommendation.action_type,
                proposed_change=recommendation.recommendation,
                confidence=recommendation.confidence,
                sample_size=recommendation.sample_size,
                supporting_evidence=recommendation.supporting_evidence,
                approved_for_application=approved,
            )
            proposals.append(proposal)
            self._memory.save_record(LEARNING_PROPOSALS, f"proposal_{len(proposals)}", proposal.to_dict())
        return tuple(proposals)


def _records(memory: MemoryManager, collection: str) -> tuple[dict[str, Any], ...]:
    try:
        keys = memory.list_records(collection)
    except (FileNotFoundError, ValueError):
        return ()
    loaded: list[dict[str, Any]] = []
    for key in keys:
        try:
            loaded.append(memory.load_record(collection, key))
        except (FileNotFoundError, ValueError):
            continue
    return tuple(loaded)


def _performance_record_from_dict(data: dict[str, Any]) -> ListingPerformanceRecord:
    listing = ListingRecord.from_dict(data["listing"])
    metrics_data = data["metrics"]
    metrics = PerformanceMetrics(
        views=int(metrics_data.get("views") or 0),
        favorites=int(metrics_data.get("favorites") or 0),
        orders=int(metrics_data.get("orders") or 0),
        revenue=float(metrics_data.get("revenue") or 0),
        refunds=int(metrics_data.get("refunds") or 0),
        downloads=int(metrics_data.get("downloads") or 0),
        traffic_source=str(metrics_data.get("traffic_source") or ""),
    )
    score_data = data["score_evolution"]
    evolution = ProductScoreEvolution(
        listing_id=str(score_data["listing_id"]),
        research_score=float(score_data.get("research_score") or 0),
        creative_score=float(score_data.get("creative_score") or 0),
        thumbnail_score=float(score_data.get("thumbnail_score") or 0),
        seo_score=float(score_data.get("seo_score") or 0),
        merchant_qa=float(score_data.get("merchant_qa") or 0),
        performance_score=float(score_data.get("performance_score") or 0),
    )
    return ListingPerformanceRecord(listing=listing, metrics=metrics, score_evolution=evolution)


def _performance_score(metrics: PerformanceMetrics) -> float:
    return round(
        min(100.0, metrics.conversion_rate * 8 + metrics.favorites * 0.4 + metrics.orders * 6 - metrics.refunds * 10),
        2,
    )


def _group_pattern(
    records: tuple[ListingPerformanceRecord, ...],
    field_name: str,
    metric_name: str,
    label: str,
) -> tuple[PatternObservation, ...]:
    grouped = _group_records(records, field_name)
    if len(grouped) < 2:
        return ()
    ranked = sorted(
        ((_group_metric(items, metric_name), name, items) for name, items in grouped.items() if name),
        reverse=True,
    )
    if len(ranked) < 2:
        return ()
    best_value, best_name, best_items = ranked[0]
    second_value, second_name, second_items = ranked[1]
    if best_value <= 0 or best_value <= second_value:
        return ()
    lift = round(best_value / second_value, 2) if second_value else round(best_value, 2)
    sample = len(best_items) + len(second_items)
    confidence = _confidence(lift, sample)
    return (
        PatternObservation(
            observation=f"{best_name} {label} outperforms {second_name}.",
            metric=metric_name,
            comparison=f"{best_name} is {lift}x stronger than {second_name} on {metric_name}.",
            confidence=confidence,
            sample_size=sample,
            supporting_evidence=(
                f"{best_name}: {best_value:.2f}",
                f"{second_name}: {second_value:.2f}",
            ),
        ),
    )


def _bundle_pattern(records: tuple[ListingPerformanceRecord, ...]) -> tuple[PatternObservation, ...]:
    small = tuple(item for item in records if 0 < item.listing.bundle_size <= 12)
    large = tuple(item for item in records if item.listing.bundle_size >= 24)
    if not small or not large:
        return ()
    small_value = _avg(item.metrics.conversion_rate for item in small)
    large_value = _avg(item.metrics.conversion_rate for item in large)
    if large_value <= small_value:
        return ()
    lift = round(large_value / small_value, 2) if small_value else round(large_value, 2)
    return (
        PatternObservation(
            observation="Larger bundles outperform smaller bundles.",
            metric="conversion_rate",
            comparison=f"24+ asset bundles convert {lift}x better than 12-or-fewer asset bundles.",
            confidence=_confidence(lift, len(small) + len(large)),
            sample_size=len(small) + len(large),
            supporting_evidence=(f"24+ assets: {large_value:.2f}", f"12 or fewer: {small_value:.2f}"),
        ),
    )


def _group_records(records: tuple[ListingPerformanceRecord, ...], field_name: str) -> dict[str, tuple[ListingPerformanceRecord, ...]]:
    grouped: dict[str, list[ListingPerformanceRecord]] = defaultdict(list)
    for record in records:
        value = getattr(record.listing, field_name)
        grouped[str(value or "Unknown")].append(record)
    return {key: tuple(value) for key, value in grouped.items()}


def _group_metric(records: tuple[ListingPerformanceRecord, ...], metric_name: str) -> float:
    return _avg(_metric(record, metric_name) for record in records)


def _metric(record: ListingPerformanceRecord, metric_name: str) -> float:
    if metric_name == "conversion_rate":
        return record.metrics.conversion_rate
    if metric_name == "revenue":
        return record.metrics.revenue
    if metric_name == "favorites":
        return float(record.metrics.favorites)
    if metric_name == "orders":
        return float(record.metrics.orders)
    return 0.0


def _best_group(records: tuple[ListingPerformanceRecord, ...], field_name: str, metric_name: str) -> tuple[str, float, int] | None:
    grouped = _group_records(records, field_name)
    if not grouped:
        return None
    name, items = max(grouped.items(), key=lambda pair: (_group_metric(pair[1], metric_name), pair[0]))
    return (name, _group_metric(items, metric_name), len(items))


def _weak_group(records: tuple[ListingPerformanceRecord, ...], field_name: str, metric_name: str) -> tuple[str, float, int] | None:
    grouped = _group_records(records, field_name)
    if not grouped:
        return None
    name, items = min(grouped.items(), key=lambda pair: (_group_metric(pair[1], metric_name), pair[0]))
    return (name, _group_metric(items, metric_name), len(items))


def _best_name(records: tuple[ListingPerformanceRecord, ...], field_name: str, metric_name: str) -> str:
    result = _best_group(records, field_name, metric_name)
    return result[0] if result else "No Data"


def _recommendation(
    text: str,
    group: tuple[str, float, int],
    action_type: str,
    reasoning: str,
) -> BusinessRecommendation:
    name, value, sample = group
    confidence = min(99.0, round(58 + sample * 5 + value * 1.2, 2))
    return BusinessRecommendation(
        recommendation=text,
        confidence=confidence,
        sample_size=sample,
        supporting_evidence=(f"{name}: {value:.2f}",),
        reasoning=reasoning,
        action_type=action_type,
    )


def _confidence(lift: float, sample_size: int) -> float:
    return min(99.0, round(55 + lift * 10 + sample_size * 3, 2))


def _avg(values: Iterable[float]) -> float:
    items = [float(value) for value in values]
    if not items:
        return 0.0
    return round(sum(items) / len(items), 4)


def _experiment_from_dict(data: dict[str, Any]) -> ABTestExperiment:
    return ABTestExperiment(
        experiment_id=str(data["experiment_id"]),
        listing_id=str(data["listing_id"]),
        hypothesis=str(data["hypothesis"]),
        variant_a=str(data["variant_a"]),
        variant_b=str(data["variant_b"]),
        metric=str(data["metric"]),
        variant_a_value=float(data.get("variant_a_value") or 0),
        variant_b_value=float(data.get("variant_b_value") or 0),
        winner=str(data.get("winner") or "PENDING"),
        confidence=float(data.get("confidence") or 0),
        sample_size=int(data.get("sample_size") or 0),
        status=str(data.get("status") or "RUNNING"),
    )
