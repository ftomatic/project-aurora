"""Opportunity ranking for read-only Etsy intelligence."""

from __future__ import annotations

from project_aurora.etsy_intelligence.duplicate_detector import DuplicateDetector
from project_aurora.etsy_intelligence.intelligence_models import (
    EvidenceRecord,
    ListingSnapshot,
    OpportunityRecommendation,
)


DEFAULT_CONCEPTS = (
    "Woodland Nursery Clipart",
    "Botanical Digital Paper",
    "Teacher Classroom Printable",
    "Vintage Christmas Gift Tags",
    "Cottagecore Mushroom Clipart",
)


class OpportunityRanker:
    """Rank opportunities without creating products."""

    def __init__(self, duplicate_detector: DuplicateDetector | None = None) -> None:
        self._duplicate_detector = duplicate_detector or DuplicateDetector()

    def rank(
        self,
        listings: tuple[ListingSnapshot, ...],
        concepts: tuple[str, ...] = DEFAULT_CONCEPTS,
    ) -> tuple[OpportunityRecommendation, ...]:
        recommendations = []
        for concept in concepts:
            duplicate = self._duplicate_detector.assess(concept, listings)
            duplicate_penalty = 25 if duplicate.decision == "SKIP_DUPLICATE" else 10 if duplicate.decision == "CREATE_WITH_DIFFERENTIATION" else 0
            score = max(0, 82 - duplicate_penalty)
            confidence = 75 if len(listings) >= 5 else 45
            evidence = (
                EvidenceRecord(
                    source="AURORA_OPPORTUNITY_RANKER",
                    observed_at=listings[0].observed_at if listings else "",
                    summary=(
                        f"Ranked with duplicate decision {duplicate.decision}; "
                        f"similarity {duplicate.similarity_score}%."
                    ),
                    sample_size=len(listings),
                    confidence=confidence,
                ),
            )
            recommendations.append(
                OpportunityRecommendation(
                    product_concept=concept,
                    opportunity_score=score,
                    seasonal_timing="Investigate current seasonal timing",
                    keyword_opportunity="Review long-tail Etsy phrases before production",
                    duplicate_risk=duplicate.cannibalization_risk,
                    recommended_differentiation=duplicate.differentiation_suggestions[0],
                    risks=("Low sample size" if len(listings) < 5 else "None",),
                    confidence=confidence,
                    evidence=evidence,
                )
            )
        return tuple(sorted(recommendations, key=lambda item: item.opportunity_score, reverse=True))
