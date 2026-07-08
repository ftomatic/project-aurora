"""Select the best style profile for a collection."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from project_aurora.config.project_profile import ProjectProfile
from project_aurora.creative.collection_plan import CollectionPlan
from project_aurora.style_intelligence.style_profile import StyleProfile


@dataclass(frozen=True, slots=True)
class StyleSelection:
    """Style selection result."""

    style_profile: StyleProfile
    reason: str
    confidence: float


class StyleSelector:
    """Score and select broad visual style profiles."""

    def select(
        self,
        project_profile: ProjectProfile,
        trend_research: dict[str, Any],
        collection_plan: CollectionPlan,
        style_profiles: tuple[StyleProfile, ...],
    ) -> StyleSelection:
        """Return the best style profile for the collection context."""
        if not style_profiles:
            raise ValueError("At least one style profile is required.")

        scored = tuple(
            (
                self._score(
                    profile=profile,
                    project_profile=project_profile,
                    trend_research=trend_research,
                    collection_plan=collection_plan,
                ),
                profile,
            )
            for profile in style_profiles
        )
        score, best_profile = max(
            scored,
            key=lambda item: (item[0], item[1].confidence),
        )
        confidence = best_profile.confidence
        return StyleSelection(
            style_profile=best_profile,
            reason=(
                f"Highest fit for {collection_plan.collection_name} Collection"
            ),
            confidence=round(confidence, 2),
        )

    @staticmethod
    def _score(
        profile: StyleProfile,
        project_profile: ProjectProfile,
        trend_research: dict[str, Any],
        collection_plan: CollectionPlan,
    ) -> int:
        context = " ".join(
            (
                project_profile.brand_style,
                project_profile.target_customer,
                collection_plan.collection_name,
                collection_plan.theme,
                collection_plan.season,
                collection_plan.art_style,
                " ".join(collection_plan.recommended_products),
                " ".join(str(value) for value in trend_research.values()),
            )
        ).casefold()

        score = int(profile.confidence * 60)
        for term in profile.style_name.casefold().split():
            if term in context:
                score += 8
        for characteristic in profile.visual_characteristics:
            if any(part in context for part in characteristic.casefold().split()):
                score += 3
        for product in profile.recommended_products:
            if product.casefold() in context:
                score += 6
        for season in profile.recommended_seasons:
            if season.casefold() in context:
                score += 5
        for audience in profile.recommended_audiences:
            if audience.casefold() in context:
                score += 4
        if profile.style_name == collection_plan.theme:
            score += 20
        if profile.style_name in collection_plan.art_style:
            score += 14
        return score
