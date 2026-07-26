"""Keyword intelligence helpers."""

from __future__ import annotations

from collections import Counter

from project_aurora.etsy_intelligence.intelligence_models import EvidenceRecord, ListingSnapshot


class KeywordAnalyzer:
    """Find recurring shop keywords without changing SEO."""

    def analyze(self, listings: tuple[ListingSnapshot, ...]) -> tuple[EvidenceRecord, ...]:
        tags = Counter(tag for listing in listings for tag in listing.tags)
        if not tags:
            return (
                EvidenceRecord(
                    source="ETSY_TAGS",
                    observed_at=listings[0].observed_at if listings else "",
                    summary="No tag data available for keyword analysis.",
                    sample_size=0,
                    confidence=0,
                ),
            )
        top = ", ".join(tag for tag, _count in tags.most_common(8))
        return (
            EvidenceRecord(
                source="ETSY_TAGS",
                observed_at=listings[0].observed_at,
                summary=f"Recurring shop tag opportunities: {top}.",
                sample_size=sum(tags.values()),
                confidence=70 if sum(tags.values()) >= 20 else 40,
            ),
        )
