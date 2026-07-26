"""Pricing intelligence in analysis-only mode."""

from __future__ import annotations

from statistics import median

from project_aurora.etsy_intelligence.intelligence_models import EvidenceRecord, ListingSnapshot
from project_aurora.merchandising.pricing_engine import DEFAULT_LISTING_PRICE


class PricingAnalyzer:
    """Analyze price observations without overriding production pricing."""

    def analyze(self, listings: tuple[ListingSnapshot, ...]) -> EvidenceRecord:
        prices = sorted(item.price for item in listings if isinstance(item.price, int | float))
        if not prices:
            summary = (
                f"Current production price remains fixed at ${DEFAULT_LISTING_PRICE:.2f}; "
                "no Etsy prices were available for analysis."
            )
            return EvidenceRecord("PRICING_ANALYSIS_ONLY", "", summary, 0, 0)
        summary = (
            f"Current production price remains fixed at ${DEFAULT_LISTING_PRICE:.2f}. "
            f"Observed shop price range ${prices[0]:.2f}-${prices[-1]:.2f}; "
            f"median ${median(prices):.2f}. Recommendation status: ANALYSIS_ONLY."
        )
        return EvidenceRecord(
            source="ETSY_LISTING_PRICES",
            observed_at=listings[0].observed_at,
            summary=summary,
            sample_size=len(prices),
            confidence=70 if len(prices) >= 5 else 35,
        )
