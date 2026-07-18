"""Business Intelligence data models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class ListingRecord:
    """One marketplace listing tracked by Aurora BI."""

    listing_id: str
    product_name: str
    collection_id: str
    blueprint: str
    creation_date: datetime
    publish_date: datetime | None
    price: float
    discounts: tuple[str, ...]
    marketplace: str
    status: str
    category: str = ""
    style: str = ""
    bundle_size: int = 0
    thumbnail_layout: str = ""

    def __post_init__(self) -> None:
        for field_name in ("listing_id", "product_name", "collection_id", "blueprint", "marketplace", "status"):
            if not str(getattr(self, field_name)).strip():
                raise ValueError(f"{field_name} cannot be empty.")
        if self.price < 0:
            raise ValueError("price cannot be negative.")
        if self.bundle_size < 0:
            raise ValueError("bundle_size cannot be negative.")
        object.__setattr__(self, "discounts", tuple(self.discounts))

    def to_dict(self) -> dict[str, Any]:
        return {
            "listing_id": self.listing_id,
            "product_name": self.product_name,
            "collection_id": self.collection_id,
            "blueprint": self.blueprint,
            "creation_date": self.creation_date.isoformat(),
            "publish_date": self.publish_date.isoformat() if self.publish_date else None,
            "price": self.price,
            "discounts": list(self.discounts),
            "marketplace": self.marketplace,
            "status": self.status,
            "category": self.category,
            "style": self.style,
            "bundle_size": self.bundle_size,
            "thumbnail_layout": self.thumbnail_layout,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ListingRecord":
        publish_date = data.get("publish_date")
        return cls(
            listing_id=str(data["listing_id"]),
            product_name=str(data["product_name"]),
            collection_id=str(data["collection_id"]),
            blueprint=str(data["blueprint"]),
            creation_date=_datetime(data.get("creation_date")),
            publish_date=_datetime(publish_date) if publish_date else None,
            price=float(data.get("price") or 0),
            discounts=tuple(str(item) for item in data.get("discounts", ())),
            marketplace=str(data["marketplace"]),
            status=str(data["status"]),
            category=str(data.get("category", "")),
            style=str(data.get("style", "")),
            bundle_size=int(data.get("bundle_size") or 0),
            thumbnail_layout=str(data.get("thumbnail_layout", "")),
        )


@dataclass(frozen=True, slots=True)
class PerformanceMetrics:
    """Performance metrics collected from marketplace activity."""

    views: int
    favorites: int
    orders: int
    revenue: float
    refunds: int
    downloads: int
    traffic_source: str
    average_order_value: float = 0.0
    conversion_rate: float = 0.0

    def __post_init__(self) -> None:
        for field_name in ("views", "favorites", "orders", "refunds", "downloads"):
            if int(getattr(self, field_name)) < 0:
                raise ValueError(f"{field_name} cannot be negative.")
        if self.revenue < 0:
            raise ValueError("revenue cannot be negative.")
        conversion = round((self.orders / self.views) * 100, 4) if self.views else 0.0
        aov = round(self.revenue / self.orders, 2) if self.orders else 0.0
        object.__setattr__(self, "conversion_rate", conversion)
        object.__setattr__(self, "average_order_value", aov)

    def to_dict(self) -> dict[str, Any]:
        return {
            "views": self.views,
            "favorites": self.favorites,
            "orders": self.orders,
            "revenue": self.revenue,
            "conversion_rate": self.conversion_rate,
            "average_order_value": self.average_order_value,
            "refunds": self.refunds,
            "downloads": self.downloads,
            "traffic_source": self.traffic_source,
        }


@dataclass(frozen=True, slots=True)
class ProductScoreEvolution:
    """Score evolution from research quality to real performance."""

    listing_id: str
    research_score: float
    creative_score: float
    thumbnail_score: float
    seo_score: float
    merchant_qa: float
    performance_score: float

    @property
    def total_score(self) -> float:
        return round(
            (
                self.research_score
                + self.creative_score
                + self.thumbnail_score
                + self.seo_score
                + self.merchant_qa
                + self.performance_score
            )
            / 6,
            2,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "listing_id": self.listing_id,
            "research_score": self.research_score,
            "creative_score": self.creative_score,
            "thumbnail_score": self.thumbnail_score,
            "seo_score": self.seo_score,
            "merchant_qa": self.merchant_qa,
            "performance_score": self.performance_score,
            "total_score": self.total_score,
        }


@dataclass(frozen=True, slots=True)
class ListingPerformanceRecord:
    """Joined listing and performance snapshot."""

    listing: ListingRecord
    metrics: PerformanceMetrics
    score_evolution: ProductScoreEvolution
    recorded_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "listing": self.listing.to_dict(),
            "metrics": self.metrics.to_dict(),
            "score_evolution": self.score_evolution.to_dict(),
            "recorded_at": self.recorded_at.isoformat(),
        }


@dataclass(frozen=True, slots=True)
class PatternObservation:
    """Evidence-backed discovered business pattern."""

    observation: str
    metric: str
    comparison: str
    confidence: float
    sample_size: int
    supporting_evidence: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "observation": self.observation,
            "metric": self.metric,
            "comparison": self.comparison,
            "confidence": self.confidence,
            "sample_size": self.sample_size,
            "supporting_evidence": list(self.supporting_evidence),
        }


@dataclass(frozen=True, slots=True)
class ABTestExperiment:
    """A/B experiment definition and outcome."""

    experiment_id: str
    listing_id: str
    hypothesis: str
    variant_a: str
    variant_b: str
    metric: str
    variant_a_value: float = 0.0
    variant_b_value: float = 0.0
    winner: str = "PENDING"
    confidence: float = 0.0
    sample_size: int = 0
    status: str = "RUNNING"

    def evaluate(self) -> "ABTestExperiment":
        winner = "A" if self.variant_a_value > self.variant_b_value else "B"
        spread = abs(self.variant_a_value - self.variant_b_value)
        confidence = min(99.0, round(55 + spread * 10 + self.sample_size * 0.8, 2))
        return ABTestExperiment(
            experiment_id=self.experiment_id,
            listing_id=self.listing_id,
            hypothesis=self.hypothesis,
            variant_a=self.variant_a,
            variant_b=self.variant_b,
            metric=self.metric,
            variant_a_value=self.variant_a_value,
            variant_b_value=self.variant_b_value,
            winner=winner,
            confidence=confidence,
            sample_size=self.sample_size,
            status="COMPLETE" if self.sample_size >= 20 else "NEEDS_MORE_DATA",
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "experiment_id": self.experiment_id,
            "listing_id": self.listing_id,
            "hypothesis": self.hypothesis,
            "variant_a": self.variant_a,
            "variant_b": self.variant_b,
            "metric": self.metric,
            "variant_a_value": self.variant_a_value,
            "variant_b_value": self.variant_b_value,
            "winner": self.winner,
            "confidence": self.confidence,
            "sample_size": self.sample_size,
            "status": self.status,
        }


@dataclass(frozen=True, slots=True)
class BusinessRecommendation:
    """Evidence-backed weekly recommendation."""

    recommendation: str
    confidence: float
    sample_size: int
    supporting_evidence: tuple[str, ...]
    reasoning: str
    action_type: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "recommendation": self.recommendation,
            "confidence": self.confidence,
            "sample_size": self.sample_size,
            "supporting_evidence": list(self.supporting_evidence),
            "reasoning": self.reasoning,
            "action_type": self.action_type,
        }


@dataclass(frozen=True, slots=True)
class CollectionAnalytics:
    """Performance analytics for one collection."""

    collection_id: str
    revenue: float
    conversion: float
    average_order_value: float
    cross_sells: int
    completion: float
    growth_trend: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "collection_id": self.collection_id,
            "revenue": self.revenue,
            "conversion": self.conversion,
            "average_order_value": self.average_order_value,
            "cross_sells": self.cross_sells,
            "completion": self.completion,
            "growth_trend": self.growth_trend,
        }


@dataclass(frozen=True, slots=True)
class ExecutiveInsights:
    """High-level merchandising insights."""

    top_performing_style: str
    fastest_growing_category: str
    highest_revenue_collection: str
    most_profitable_blueprint: str
    most_effective_thumbnail_layout: str

    def to_dict(self) -> dict[str, str]:
        return {
            "top_performing_style": self.top_performing_style,
            "fastest_growing_category": self.fastest_growing_category,
            "highest_revenue_collection": self.highest_revenue_collection,
            "most_profitable_blueprint": self.most_profitable_blueprint,
            "most_effective_thumbnail_layout": self.most_effective_thumbnail_layout,
        }


@dataclass(frozen=True, slots=True)
class LearningProposal:
    """Safe proposed strategy adjustment."""

    adjustment_type: str
    proposed_change: str
    confidence: float
    sample_size: int
    supporting_evidence: tuple[str, ...]
    approved_for_application: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "adjustment_type": self.adjustment_type,
            "proposed_change": self.proposed_change,
            "confidence": self.confidence,
            "sample_size": self.sample_size,
            "supporting_evidence": list(self.supporting_evidence),
            "approved_for_application": self.approved_for_application,
        }


def _datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value:
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return datetime.now()
    return datetime.now()
