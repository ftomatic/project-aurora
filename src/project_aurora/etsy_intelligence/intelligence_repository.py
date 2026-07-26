"""Persistence helpers for Etsy intelligence snapshots."""

from __future__ import annotations

from datetime import datetime

from project_aurora.etsy_intelligence.intelligence_models import (
    EtsyIntelligenceReport,
    EvidenceRecord,
    ListingSnapshot,
    OpportunityRecommendation,
    ShopSnapshot,
)
from project_aurora.storage.memory_manager import MemoryManager


class EtsyIntelligenceRepository:
    """Append-only-ish intelligence repository over Aurora Memory."""

    SHOP_SNAPSHOT_COLLECTION = "etsy_shop_snapshots"
    LISTING_SNAPSHOT_COLLECTION = "etsy_listing_snapshots"
    RECOMMENDATION_COLLECTION = "etsy_intelligence_recommendations"
    REPORT_COLLECTION = "etsy_intelligence_reports"
    EVIDENCE_COLLECTION = "etsy_intelligence_evidence"

    def __init__(self, memory: MemoryManager) -> None:
        self._memory = memory

    def save_report(self, report: EtsyIntelligenceReport) -> str:
        """Save a report and all child snapshots without destructive overwrite."""
        key = _timestamp_key("report")
        self._memory.save_record(self.REPORT_COLLECTION, key, report.to_dict())
        self._memory.save_record(self.REPORT_COLLECTION, "latest", report.to_dict())
        self._memory.save_record(
            self.SHOP_SNAPSHOT_COLLECTION,
            _timestamp_key("shop"),
            report.shop_snapshot.to_dict(),
        )
        for listing in report.listing_snapshots:
            self.save_listing_snapshot(listing)
        for recommendation in report.top_opportunities:
            self.save_recommendation(recommendation)
        for evidence in report.shop_learnings:
            self.save_evidence(evidence)
        return key

    def save_listing_snapshot(self, snapshot: ListingSnapshot) -> str:
        key = _timestamp_key(f"listing_{snapshot.listing_id}")
        self._memory.save_record(self.LISTING_SNAPSHOT_COLLECTION, key, snapshot.to_dict())
        return key

    def save_recommendation(self, recommendation: OpportunityRecommendation) -> str:
        key = _timestamp_key(recommendation.product_concept)
        self._memory.save_record(self.RECOMMENDATION_COLLECTION, key, recommendation.to_dict())
        return key

    def save_evidence(self, evidence: EvidenceRecord) -> str:
        key = _timestamp_key(evidence.source)
        self._memory.save_record(self.EVIDENCE_COLLECTION, key, evidence.to_dict())
        return key

    def list_reports(self) -> tuple[str, ...]:
        return self._memory.list_records(self.REPORT_COLLECTION)


def _timestamp_key(prefix: str) -> str:
    safe = "".join(char if char.isalnum() else "_" for char in prefix.casefold()).strip("_")
    return f"{safe}_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
