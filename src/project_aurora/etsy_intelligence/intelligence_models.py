"""Dataclasses for read-only Etsy intelligence."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


READ_ONLY = "READ_ONLY"
RECOMMENDATION_ONLY = "RECOMMENDATION_ONLY"
APPROVED_WRITE = "APPROVED_WRITE"
UNAVAILABLE = "UNAVAILABLE"
SCHEMA_VERSION = "2026-07-sprint-35-36"


@dataclass(frozen=True, slots=True)
class DataAvailability:
    """Whether an Etsy metric is available from current inputs."""

    field_name: str
    status: str
    reason: str

    def to_dict(self) -> dict[str, str]:
        return {
            "field_name": self.field_name,
            "status": self.status,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class EvidenceRecord:
    """Evidence supporting a derived Etsy intelligence conclusion."""

    source: str
    observed_at: str
    summary: str
    sample_size: int
    confidence: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "observed_at": self.observed_at,
            "summary": self.summary,
            "sample_size": self.sample_size,
            "confidence": self.confidence,
        }


@dataclass(frozen=True, slots=True)
class ListingSnapshot:
    """Normalized Etsy listing snapshot."""

    listing_id: str
    title: str
    state: str
    price: float | None
    tags: tuple[str, ...]
    taxonomy_id: str
    is_digital: bool | str
    image_count: int | str
    views: int | str = UNAVAILABLE
    favorites: int | str = UNAVAILABLE
    orders: int | str = UNAVAILABLE
    revenue: float | str = UNAVAILABLE
    observed_at: str = field(default_factory=lambda: datetime.now().isoformat())
    source: str = "ETSY_OPEN_API"
    schema_version: str = SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "listing_id": self.listing_id,
            "title": self.title,
            "state": self.state,
            "price": self.price,
            "tags": list(self.tags),
            "taxonomy_id": self.taxonomy_id,
            "is_digital": self.is_digital,
            "image_count": self.image_count,
            "views": self.views,
            "favorites": self.favorites,
            "orders": self.orders,
            "revenue": self.revenue,
            "observed_at": self.observed_at,
            "source": self.source,
            "schema_version": self.schema_version,
        }


@dataclass(frozen=True, slots=True)
class ShopSnapshot:
    """Shop-level intelligence snapshot."""

    active_listings: int
    draft_listings: int
    expired_listings: int | str
    sold_out_listings: int | str
    categories: tuple[str, ...]
    data_availability: tuple[DataAvailability, ...]
    observed_at: str = field(default_factory=lambda: datetime.now().isoformat())
    source: str = "AURORA_READ_ONLY"
    schema_version: str = SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "active_listings": self.active_listings,
            "draft_listings": self.draft_listings,
            "expired_listings": self.expired_listings,
            "sold_out_listings": self.sold_out_listings,
            "categories": list(self.categories),
            "data_availability": [item.to_dict() for item in self.data_availability],
            "observed_at": self.observed_at,
            "source": self.source,
            "schema_version": self.schema_version,
        }


@dataclass(frozen=True, slots=True)
class DuplicateAssessment:
    """Overlap/cannibalization decision for a proposed concept."""

    product_concept: str
    similarity_score: int
    overlapping_listing_ids: tuple[str, ...]
    cannibalization_risk: str
    differentiation_suggestions: tuple[str, ...]
    decision: str
    evidence: tuple[EvidenceRecord, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "product_concept": self.product_concept,
            "similarity_score": self.similarity_score,
            "overlapping_listing_ids": list(self.overlapping_listing_ids),
            "cannibalization_risk": self.cannibalization_risk,
            "differentiation_suggestions": list(self.differentiation_suggestions),
            "decision": self.decision,
            "evidence": [item.to_dict() for item in self.evidence],
        }


@dataclass(frozen=True, slots=True)
class OpportunityRecommendation:
    """Read-only product opportunity recommendation."""

    product_concept: str
    opportunity_score: int
    seasonal_timing: str
    keyword_opportunity: str
    duplicate_risk: str
    recommended_differentiation: str
    risks: tuple[str, ...]
    confidence: int
    evidence: tuple[EvidenceRecord, ...]
    recommendation_status: str = "RECOMMENDATION_ONLY"

    def to_dict(self) -> dict[str, Any]:
        return {
            "product_concept": self.product_concept,
            "opportunity_score": self.opportunity_score,
            "seasonal_timing": self.seasonal_timing,
            "keyword_opportunity": self.keyword_opportunity,
            "duplicate_risk": self.duplicate_risk,
            "recommended_differentiation": self.recommended_differentiation,
            "risks": list(self.risks),
            "confidence": self.confidence,
            "evidence": [item.to_dict() for item in self.evidence],
            "recommendation_status": self.recommendation_status,
        }


@dataclass(frozen=True, slots=True)
class EtsyIntelligenceReport:
    """Daily Etsy intelligence report."""

    mode: str
    shop_snapshot: ShopSnapshot
    listing_snapshots: tuple[ListingSnapshot, ...]
    top_opportunities: tuple[OpportunityRecommendation, ...]
    shop_learnings: tuple[EvidenceRecord, ...]
    recommended_actions: tuple[str, ...]
    warnings: tuple[str, ...]
    writes_performed: bool
    observed_at: str = field(default_factory=lambda: datetime.now().isoformat())
    schema_version: str = SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "shop_snapshot": self.shop_snapshot.to_dict(),
            "listing_snapshots": [item.to_dict() for item in self.listing_snapshots],
            "top_opportunities": [item.to_dict() for item in self.top_opportunities],
            "shop_learnings": [item.to_dict() for item in self.shop_learnings],
            "recommended_actions": list(self.recommended_actions),
            "warnings": list(self.warnings),
            "writes_performed": self.writes_performed,
            "observed_at": self.observed_at,
            "schema_version": self.schema_version,
        }
