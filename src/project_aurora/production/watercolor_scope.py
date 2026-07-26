"""Approved simplified production scope for RainbowMilkStudio recovery."""

from __future__ import annotations

from dataclasses import dataclass


UNSUPPORTED_PRODUCT_TYPE = "UNSUPPORTED_PRODUCT_TYPE"

SUPPORTED_CANONICAL_TYPES = {
    "watercolor_clipart_bundle",
    "watercolor_sticker_set",
    "watercolor_animal_collection",
    "watercolor_botanical_collection",
    "watercolor_woodland_collection",
    "signature_storybook_animal_collection",
}

UNSUPPORTED_TERMS = (
    "planner",
    "calendar",
    "journal",
    "template",
    "editable",
    "invitation",
    "party printable",
    "teacher resource",
    "classroom",
    "alphabet poster",
    "alphabet posters",
    "worksheet",
    "typography",
    "quote art",
    "wall art",
    "digital paper",
    "cover",
    "mockup",
    "svg",
    "pdf",
    "poster",
    "printable wall art",
)

SUPPORTED_TERMS = (
    "clipart",
    "clip art",
    "sticker illustration set",
    "watercolor animals",
    "storybook animal",
    "storybook animals",
    "animal collection",
    "botanical watercolor",
    "botanical clipart",
    "woodland watercolor",
    "woodland clipart",
    "seasonal watercolor",
    "digital illustration collection",
    "illustration collection",
)


@dataclass(frozen=True, slots=True)
class WatercolorScopeDecision:
    """Production scope decision."""

    supported: bool
    canonical_product_type: str
    reason: str


def resolve_watercolor_scope(product_name: str, category: str, style: str = "") -> WatercolorScopeDecision:
    """Map compatible products into the reduced watercolor production scope."""
    text = f"{product_name} {category} {style}".casefold()
    unsupported = _first_matching(text, UNSUPPORTED_TERMS)
    if unsupported and not _is_compatible_sticker(text):
        return WatercolorScopeDecision(
            supported=False,
            canonical_product_type="",
            reason=f"Unsupported recovery product type: {unsupported}.",
        )
    if not any(term in text for term in SUPPORTED_TERMS):
        return WatercolorScopeDecision(
            supported=False,
            canonical_product_type="",
            reason="Product is outside the approved watercolor clipart illustration scope.",
        )
    if "sticker illustration set" in text or ("sticker" in text and "illustration" in text):
        return WatercolorScopeDecision(True, "watercolor_sticker_set", "Compatible watercolor sticker illustration set.")
    if "storybook" in text and "animal" in text:
        return WatercolorScopeDecision(True, "signature_storybook_animal_collection", "Compatible signature storybook animal collection.")
    if "woodland" in text and "animal" in text:
        return WatercolorScopeDecision(True, "watercolor_animal_collection", "Compatible woodland animal collection.")
    if "animal" in text:
        return WatercolorScopeDecision(True, "watercolor_animal_collection", "Compatible watercolor animal collection.")
    if "botanical" in text or "mushroom" in text or "floral" in text:
        return WatercolorScopeDecision(True, "watercolor_botanical_collection", "Compatible botanical watercolor clipart.")
    if "woodland" in text:
        return WatercolorScopeDecision(True, "watercolor_woodland_collection", "Compatible woodland watercolor clipart.")
    return WatercolorScopeDecision(True, "watercolor_clipart_bundle", "Compatible watercolor clipart bundle.")


def is_supported_watercolor_product(product_name: str, category: str, style: str = "") -> bool:
    return resolve_watercolor_scope(product_name, category, style).supported


def _first_matching(text: str, terms: tuple[str, ...]) -> str:
    return next((term for term in terms if term in text), "")


def _is_compatible_sticker(text: str) -> bool:
    return "sticker illustration set" in text and not any(
        term in text for term in ("planner", "template", "layout", "sheet")
    )
