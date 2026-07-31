"""Approved live production scope for the July 17 clipart recovery."""

from __future__ import annotations

from dataclasses import dataclass


UNSUPPORTED_PRODUCT_TYPE = "UNSUPPORTED_PRODUCT_TYPE"

SUPPORTED_CANONICAL_TYPES = {
    "watercolor_clipart_bundle",
    "watercolor_animal_collection",
    "watercolor_botanical_collection",
    "watercolor_woodland_collection",
    "watercolor_seasonal_collection",
    "signature_storybook_animal_collection",
    "watercolor_sticker_illustration_set",
    "wedding_printable",
    "digital_print",
}

UNSUPPORTED_TERMS = (
    "planner",
    "calendar",
    "journal",
    "template",
    "editable",
    "invitation",
    "poster",
    "teacher",
    "classroom",
    "alphabet",
    "worksheet",
    "typography",
    "quote art",
    "wall art",
    "digital paper",
    "paper pack",
    "mockup",
    "cover",
    "svg",
    "pdf",
)

SUPPORTED_TERMS = (
    "clipart",
    "clip art",
    "sticker illustration set",
    "watercolor animal",
    "baby animal",
    "woodland",
    "nursery animal",
    "storybook animal",
    "botanical",
    "mushroom",
    "seasonal watercolor",
    "digital illustration collection",
    "illustration collection",
)


@dataclass(frozen=True, slots=True)
class WatercolorScopeDecision:
    """Decision for whether a product belongs in the live recovery path."""

    supported: bool
    canonical_product_type: str
    reason: str


def resolve_watercolor_scope(
    product_name: str,
    category: str,
    style: str = "",
) -> WatercolorScopeDecision:
    """Map compatible products into Aurora's narrowed live clipart scope."""
    raw_text = f"{product_name} {category} {style}".casefold()
    text = raw_text.replace("_", " ").replace("-", " ")
    category_key = category.casefold().strip().replace(" ", "_").replace("-", "_")
    if category_key == "wedding_printable":
        return WatercolorScopeDecision(
            True,
            "wedding_printable",
            "Compatible wedding printable four-image listing.",
        )
    if category_key == "digital_print":
        return WatercolorScopeDecision(
            True,
            "digital_print",
            "Compatible digital print four-image listing.",
        )
    unsupported = _first_matching(text, UNSUPPORTED_TERMS)
    if unsupported and not _is_supported_sticker_illustration(text):
        return WatercolorScopeDecision(
            supported=False,
            canonical_product_type="",
            reason=f"Unsupported recovery product type: {unsupported}.",
        )
    if category_key not in SUPPORTED_CANONICAL_TYPES and not any(
        term in text for term in SUPPORTED_TERMS
    ):
        return WatercolorScopeDecision(
            supported=False,
            canonical_product_type="",
            reason="Product is outside the approved watercolor clipart illustration scope.",
        )
    if _is_supported_sticker_illustration(text):
        return WatercolorScopeDecision(
            True,
            "watercolor_sticker_illustration_set",
            "Compatible watercolor sticker illustration set.",
        )
    if "storybook" in text and ("animal" in text or "woodland" in text):
        return WatercolorScopeDecision(
            True,
            "signature_storybook_animal_collection",
            "Compatible signature storybook animal collection.",
        )
    if "woodland" in text and ("animal" in text or "nursery" in text):
        return WatercolorScopeDecision(
            True,
            "watercolor_animal_collection",
            "Compatible woodland animal collection.",
        )
    if "animal" in text:
        return WatercolorScopeDecision(
            True,
            "watercolor_animal_collection",
            "Compatible watercolor animal collection.",
        )
    if any(term in text for term in ("botanical", "mushroom", "floral")):
        return WatercolorScopeDecision(
            True,
            "watercolor_botanical_collection",
            "Compatible botanical watercolor clipart.",
        )
    if "woodland" in text:
        return WatercolorScopeDecision(
            True,
            "watercolor_woodland_collection",
            "Compatible woodland watercolor clipart.",
        )
    if any(term in text for term in ("christmas", "autumn", "spring", "halloween", "winter")):
        return WatercolorScopeDecision(
            True,
            "watercolor_seasonal_collection",
            "Compatible seasonal watercolor clipart.",
        )
    return WatercolorScopeDecision(
        True,
        "watercolor_clipart_bundle",
        "Compatible watercolor clipart bundle.",
    )


def _first_matching(text: str, terms: tuple[str, ...]) -> str:
    return next((term for term in terms if term in text), "")


def _is_supported_sticker_illustration(text: str) -> bool:
    return "sticker illustration set" in text and not any(
        term in text for term in ("planner", "template", "layout", "sheet")
    )
