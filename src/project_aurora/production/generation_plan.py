"""Authoritative per-product image generation planning."""

from __future__ import annotations

from dataclasses import dataclass, field

from project_aurora.image_generation.listing_family_decision import (
    CLIPART_TERMS,
    LISTING_FAMILY_AUTO,
    STORYBOOK_TERMS,
    _matched_terms,
)
from project_aurora.production.generation_strategy import (
    GENERATION_MODE_AUTO,
    GENERATION_MODE_BOTANICAL,
    GENERATION_MODE_CHARACTERS,
    GENERATION_MODE_CLIPART,
    GENERATION_MODE_DIGITAL_PAPER,
    GENERATION_MODE_ORIGINAL,
    GENERATION_MODE_STORYBOOK,
    GENERATION_MODE_WEDDING,
    SUPPORTED_GENERATION_STRATEGIES,
    normalize_generation_mode,
)


SUPPORTED_GENERATION_MODES = SUPPORTED_GENERATION_STRATEGIES


@dataclass(frozen=True, slots=True)
class GenerationPlan:
    """Resolved image-generation plan for one Product Factory job."""

    resolved_mode: str
    decision_reason: str
    customer_png_count: int = 4
    scene_required: bool = False
    matched_terms: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, object]:
        """Return JSON-safe generation-plan data."""
        return {
            "resolved_mode": self.resolved_mode,
            "decision_reason": self.decision_reason,
            "customer_png_count": self.customer_png_count,
            "scene_required": self.scene_required,
            "matched_terms": list(self.matched_terms),
        }


class GenerationPlanResolver:
    """Resolve CLIPART vs STORYBOOK before any image files exist."""

    def __init__(
        self,
        storybook_terms: tuple[str, ...] = STORYBOOK_TERMS,
        clipart_terms: tuple[str, ...] = CLIPART_TERMS,
    ) -> None:
        self._storybook_terms = storybook_terms
        self._clipart_terms = clipart_terms

    def resolve(
        self,
        *,
        product_name: str,
        product_category: str = "",
        niche_theme: str = "",
        intended_customer: str = "",
        artwork_composition: str = "",
        listing_family: str = LISTING_FAMILY_AUTO,
    ) -> GenerationPlan:
        """Resolve one generation plan from product business context."""
        requested = _normalize_mode(listing_family)
        if requested in {GENERATION_MODE_STORYBOOK, GENERATION_MODE_ORIGINAL}:
            return GenerationPlan(
                resolved_mode=requested,
                decision_reason="Explicit per-product generation mode override.",
                scene_required=True,
            )
        if requested in {
            GENERATION_MODE_CLIPART,
            GENERATION_MODE_CHARACTERS,
            GENERATION_MODE_BOTANICAL,
            GENERATION_MODE_DIGITAL_PAPER,
            GENERATION_MODE_WEDDING,
        }:
            return GenerationPlan(
                resolved_mode=requested,
                decision_reason="Explicit per-product generation mode override.",
                scene_required=False,
            )

        context = _context_text(
            product_name,
            product_category,
            niche_theme,
            intended_customer,
            artwork_composition,
        )
        clipart_matches = _matched_terms(context, self._clipart_terms)
        if clipart_matches:
            return GenerationPlan(
                resolved_mode=GENERATION_MODE_CLIPART,
                decision_reason="CLIPART mode selected from category/theme heuristics.",
                scene_required=False,
                matched_terms=clipart_matches,
            )
        storybook_matches = _matched_terms(context, self._storybook_terms)
        if storybook_matches:
            return GenerationPlan(
                resolved_mode=GENERATION_MODE_STORYBOOK,
                decision_reason="STORYBOOK mode selected from category/theme heuristics.",
                scene_required=True,
                matched_terms=storybook_matches,
            )
        return GenerationPlan(
            resolved_mode=GENERATION_MODE_CLIPART,
            decision_reason="AUTO defaulted to CLIPART for commercial asset production.",
            scene_required=False,
        )


def _normalize_mode(value: str) -> str:
    return normalize_generation_mode(value or GENERATION_MODE_AUTO or LISTING_FAMILY_AUTO)


def _context_text(*values: str) -> str:
    return " ".join(
        value.casefold().replace("_", " ").replace("-", " ")
        for value in values
        if value
    )
