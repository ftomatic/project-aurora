"""Performance conclusions from available Etsy/Aurora data."""

from __future__ import annotations

from collections import Counter

from project_aurora.etsy_intelligence.intelligence_models import (
    EvidenceRecord,
    ListingSnapshot,
    UNAVAILABLE,
)


class PerformanceAnalyzer:
    """Generate low-risk evidence-backed shop learnings."""

    def analyze(self, listings: tuple[ListingSnapshot, ...]) -> tuple[EvidenceRecord, ...]:
        if not listings:
            return (
                EvidenceRecord(
                    source="AURORA_INTELLIGENCE",
                    observed_at="",
                    summary="No Etsy listing snapshots available yet.",
                    sample_size=0,
                    confidence=0,
                ),
            )
        token_counts = Counter(
            token
            for listing in listings
            for token in _title_tokens(listing.title)
        )
        common = ", ".join(token for token, _count in token_counts.most_common(5)) or UNAVAILABLE
        return (
            EvidenceRecord(
                source="ETSY_LISTING_TITLES",
                observed_at=listings[0].observed_at,
                summary=f"Common title terms in available listings: {common}.",
                sample_size=len(listings),
                confidence=70 if len(listings) >= 5 else 35,
            ),
        )


def _title_tokens(title: str) -> tuple[str, ...]:
    ignored = {"and", "the", "for", "with", "digital", "printable"}
    return tuple(
        token
        for token in "".join(char if char.isalnum() else " " for char in title.casefold()).split()
        if len(token) > 3 and token not in ignored
    )
