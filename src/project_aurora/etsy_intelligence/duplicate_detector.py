"""Duplicate and cannibalization checks for Etsy intelligence."""

from __future__ import annotations

from project_aurora.etsy_intelligence.intelligence_models import (
    DuplicateAssessment,
    EvidenceRecord,
    ListingSnapshot,
)


class DuplicateDetector:
    """Compare a product concept against shop listings."""

    def assess(
        self,
        product_concept: str,
        listings: tuple[ListingSnapshot, ...],
    ) -> DuplicateAssessment:
        concept_tokens = _tokens(product_concept)
        scored = []
        for listing in listings:
            listing_tokens = _tokens(" ".join((listing.title, " ".join(listing.tags))))
            score = _similarity(concept_tokens, listing_tokens)
            if score:
                scored.append((score, listing))
        scored.sort(key=lambda item: item[0], reverse=True)
        best = scored[0][0] if scored else 0
        overlaps = tuple(item.listing_id for score, item in scored if score >= 60 and item.listing_id)
        if best >= 85:
            decision = "SKIP_DUPLICATE"
            risk = "High"
        elif best >= 60:
            decision = "CREATE_WITH_DIFFERENTIATION"
            risk = "Moderate"
        elif best >= 35:
            decision = "EXPAND_EXISTING_FAMILY"
            risk = "Low"
        else:
            decision = "CREATE"
            risk = "Low"
        evidence = (
            EvidenceRecord(
                source="AURORA_SHOP_LISTING_SNAPSHOT",
                observed_at=listings[0].observed_at if listings else "",
                summary=f"Compared concept against {len(listings)} listing snapshots.",
                sample_size=len(listings),
                confidence=80 if len(listings) >= 5 else 45,
            ),
        )
        return DuplicateAssessment(
            product_concept=product_concept,
            similarity_score=best,
            overlapping_listing_ids=overlaps,
            cannibalization_risk=risk,
            differentiation_suggestions=_suggestions(product_concept),
            decision=decision,
            evidence=evidence,
        )


def _tokens(text: str) -> set[str]:
    return {
        token
        for token in "".join(char if char.isalnum() else " " for char in text.casefold()).split()
        if len(token) > 2
    }


def _similarity(left: set[str], right: set[str]) -> int:
    if not left or not right:
        return 0
    overlap = len(left & right)
    return round((overlap / max(len(left), len(right))) * 100)


def _suggestions(product_concept: str) -> tuple[str, ...]:
    return (
        f"{product_concept} with a different color palette",
        f"{product_concept} in a different product format",
        f"{product_concept} targeted to a different buyer",
    )
