"""Business rules for selecting Aurora Etsy listing image families."""

from __future__ import annotations

from dataclasses import dataclass, field


LISTING_FAMILY_AUTO = "AUTO"
LISTING_FAMILY_CLIPART = "CLIPART"
LISTING_FAMILY_STORYBOOK = "STORYBOOK"
SUPPORTED_LISTING_FAMILIES = {
    LISTING_FAMILY_AUTO,
    LISTING_FAMILY_CLIPART,
    LISTING_FAMILY_STORYBOOK,
}

STORYBOOK_TERMS = (
    "nursery",
    "woodland",
    "cottagecore",
    "baby animals",
    "forest animals",
    "storybook",
    "fairytale",
    "whimsical",
    "children's decor",
    "childrens decor",
    "baby shower",
    "nursery decor",
    "cozy home",
    "animal families",
    "tea party",
    "gardening animals",
    "baking animals",
    "seasonal children's collections",
    "seasonal childrens collections",
)

CLIPART_TERMS = (
    "wedding",
    "bridal",
    "back to school",
    "school supplies",
    "classroom elements",
    "digital paper",
    "floral elements",
    "botanical elements",
    "frames",
    "borders",
    "wreaths",
    "clipart bundles",
    "clipart bundle",
    "icons",
    "stickers",
    "planner elements",
    "scrapbook assets",
    "printable elements",
    "commercial-use asset packs",
    "commercial use asset packs",
    "isolated objects",
)


@dataclass(frozen=True, slots=True)
class ListingFamilyDecision:
    """Resolved listing family and the business reason for the decision."""

    requested_family: str
    selected_family: str
    reason: str
    matched_terms: tuple[str, ...] = field(default_factory=tuple)
    scene_available: bool = False


@dataclass(frozen=True, slots=True)
class ListingFamilyDecisionEngine:
    """Select listing image family from product business context."""

    storybook_terms: tuple[str, ...] = STORYBOOK_TERMS
    clipart_terms: tuple[str, ...] = CLIPART_TERMS

    def decide(
        self,
        *,
        listing_family: str = LISTING_FAMILY_AUTO,
        product_category: str = "",
        niche_theme: str = "",
        intended_customer: str = "",
        artwork_composition: str = "",
        scene_available: bool = False,
    ) -> ListingFamilyDecision:
        """Return the resolved listing family for one product."""
        requested = _normalize_listing_family(listing_family)
        if requested in {LISTING_FAMILY_CLIPART, LISTING_FAMILY_STORYBOOK}:
            return self._with_scene_fallback(
                requested_family=requested,
                selected_family=requested,
                scene_available=scene_available,
                reason="Explicit per-product listing family override.",
                matched_terms=(),
            )

        context = _context_text(
            product_category,
            niche_theme,
            intended_customer,
            artwork_composition,
        )
        clipart_matches = _matched_terms(context, self.clipart_terms)
        if clipart_matches:
            return ListingFamilyDecision(
                requested_family=requested,
                selected_family=LISTING_FAMILY_CLIPART,
                reason="Clipart-family category/theme heuristic matched.",
                matched_terms=clipart_matches,
                scene_available=scene_available,
            )

        storybook_matches = _matched_terms(context, self.storybook_terms)
        if storybook_matches:
            return self._with_scene_fallback(
                requested_family=requested,
                selected_family=LISTING_FAMILY_STORYBOOK,
                scene_available=scene_available,
                reason="Storybook-family category/theme heuristic matched.",
                matched_terms=storybook_matches,
            )

        return ListingFamilyDecision(
            requested_family=requested,
            selected_family=LISTING_FAMILY_STORYBOOK if scene_available else LISTING_FAMILY_CLIPART,
            reason=(
                "AUTO selected STORYBOOK because a completed storybook scene exists."
                if scene_available
                else "AUTO selected CLIPART because no completed storybook scene exists."
            ),
            scene_available=scene_available,
        )

    @staticmethod
    def _with_scene_fallback(
        *,
        requested_family: str,
        selected_family: str,
        scene_available: bool,
        reason: str,
        matched_terms: tuple[str, ...],
    ) -> ListingFamilyDecision:
        if selected_family == LISTING_FAMILY_STORYBOOK and not scene_available:
            return ListingFamilyDecision(
                requested_family=requested_family,
                selected_family=LISTING_FAMILY_CLIPART,
                reason=f"{reason} Fell back to CLIPART because no completed storybook scene exists.",
                matched_terms=matched_terms,
                scene_available=False,
            )
        return ListingFamilyDecision(
            requested_family=requested_family,
            selected_family=selected_family,
            reason=reason,
            matched_terms=matched_terms,
            scene_available=scene_available,
        )


def _normalize_listing_family(value: str) -> str:
    family = (value or LISTING_FAMILY_AUTO).strip().upper()
    if family not in SUPPORTED_LISTING_FAMILIES:
        raise ValueError(f"Unsupported listing family: {value}.")
    return family


def _context_text(*values: str) -> str:
    return " ".join(value.casefold().replace("_", " ") for value in values if value)


def _matched_terms(context: str, terms: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(term for term in terms if term.casefold() in context)
