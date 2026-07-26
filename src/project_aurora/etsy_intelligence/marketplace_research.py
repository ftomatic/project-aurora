"""Marketplace research placeholder for permitted future Etsy signals."""

from __future__ import annotations

from project_aurora.etsy_intelligence.intelligence_models import EvidenceRecord


class MarketplaceResearch:
    """Record unavailable marketplace research without fabricating data."""

    def collect(self) -> tuple[EvidenceRecord, ...]:
        return (
            EvidenceRecord(
                source="ETSY_MARKETPLACE_RESEARCH",
                observed_at="",
                summary="Marketplace research provider not configured; no competitor data copied.",
                sample_size=0,
                confidence=0,
            ),
        )
