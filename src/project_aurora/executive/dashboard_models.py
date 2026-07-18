"""Executive dashboard data models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class ExecutiveSummary:
    """Top-line operational summary."""

    products_generated_today: int
    products_published: int
    drafts_pending_review: int
    collections_active: int
    collections_in_progress: int
    products_waiting: int
    average_opportunity_score: float
    average_creative_score: float
    average_thumbnail_score: float
    average_merchant_qa_score: float
    estimated_monthly_revenue: float

    def to_dict(self) -> dict[str, Any]:
        return _to_dict(self)


@dataclass(frozen=True, slots=True)
class PipelineSummary:
    """Counts and bottlenecks for Aurora's production pipeline."""

    research: int
    opportunity: int
    creative: int
    production: int
    qa: int
    etsy_draft: int
    published: int
    bottlenecks: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        data = _to_dict(self)
        data["bottlenecks"] = list(self.bottlenecks)
        return data


@dataclass(frozen=True, slots=True)
class ShopHealthMetrics:
    """Portfolio-level shop health metrics."""

    products_per_category: dict[str, int]
    products_per_collection: dict[str, int]
    seasonal_vs_evergreen: dict[str, int]
    average_listing_price: float
    average_bundle_size: float
    portfolio_diversity: str

    def to_dict(self) -> dict[str, Any]:
        return _to_dict(self)


@dataclass(frozen=True, slots=True)
class QualityMetrics:
    """Quality metrics across the production system."""

    creative_score: float
    merchant_qa: float
    thumbnail_score: float
    seo_score: float
    blueprint_compliance: float
    reject_rate: float

    def to_dict(self) -> dict[str, Any]:
        return _to_dict(self)


@dataclass(frozen=True, slots=True)
class BusinessMetrics:
    """Estimated business performance metrics."""

    potential_revenue: float
    expected_monthly_revenue: float
    expected_annual_revenue: float
    expected_margin: float
    average_product_value: float
    average_collection_value: float

    def to_dict(self) -> dict[str, Any]:
        return _to_dict(self)


@dataclass(frozen=True, slots=True)
class TopOpportunity:
    """One ranked opportunity for executive display."""

    rank: int
    product: str
    score: float
    estimated_revenue: float
    collection: str
    status: str

    def to_dict(self) -> dict[str, Any]:
        return _to_dict(self)


@dataclass(frozen=True, slots=True)
class CollectionHealthItem:
    """Health row for one collection."""

    collection_name: str
    completion_percent: float
    products: int
    revenue_estimate: float
    cross_sell_score: float
    brand_consistency: float

    def to_dict(self) -> dict[str, Any]:
        return _to_dict(self)


@dataclass(frozen=True, slots=True)
class ExecutiveAlert:
    """One executive alert."""

    alert_type: str
    severity: str
    message: str
    recommended_action: str

    def to_dict(self) -> dict[str, Any]:
        return _to_dict(self)


@dataclass(frozen=True, slots=True)
class ExecutiveDashboard:
    """Complete executive dashboard snapshot."""

    executive_summary: ExecutiveSummary
    production_pipeline: PipelineSummary
    shop_health: ShopHealthMetrics
    quality_metrics: QualityMetrics
    business_metrics: BusinessMetrics
    top_opportunities: tuple[TopOpportunity, ...]
    collection_health: tuple[CollectionHealthItem, ...]
    alerts: tuple[ExecutiveAlert, ...]
    daily_report: str
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "executive_summary": self.executive_summary.to_dict(),
            "production_pipeline": self.production_pipeline.to_dict(),
            "shop_health": self.shop_health.to_dict(),
            "quality_metrics": self.quality_metrics.to_dict(),
            "business_metrics": self.business_metrics.to_dict(),
            "top_opportunities": [item.to_dict() for item in self.top_opportunities],
            "collection_health": [item.to_dict() for item in self.collection_health],
            "alerts": [item.to_dict() for item in self.alerts],
            "daily_report": self.daily_report,
            "created_at": self.created_at.isoformat(),
        }


def _to_dict(instance: Any) -> dict[str, Any]:
    return {
        field: getattr(instance, field)
        for field in getattr(instance, "__dataclass_fields__", {})
    }
