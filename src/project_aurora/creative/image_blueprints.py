"""Customer-facing image blueprints for coherent Etsy product sets."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ImageBlueprint:
    """One image role in a product presentation strategy."""

    image_number: int
    role: str
    purpose: str
    composition: str
    must_show: tuple[str, ...]
    must_not_imply: tuple[str, ...]


def blueprints_for_product(product_type: str) -> tuple[ImageBlueprint, ...]:
    """Return four blueprint roles for a product type."""
    lowered = product_type.casefold()
    if "clipart" in lowered:
        return _clipart()
    if "digital paper" in lowered:
        return _digital_paper()
    if "wall art" in lowered:
        return _wall_art()
    if "planner" in lowered or "sticker" in lowered:
        return _planner_stickers()
    if "journal" in lowered:
        return _journal_elements()
    if "card" in lowered:
        return _greeting_card()
    if "party" in lowered or "invitation" in lowered or "classroom" in lowered:
        return _printable()
    return _digital_illustration_collection()


def _digital_illustration_collection() -> tuple[ImageBlueprint, ...]:
    return (
        ImageBlueprint(1, "HERO COVER", "Strong Etsy thumbnail for the collection.", "coordinated cover-style grouped preview", ("all four illustrations", "clear visual hierarchy"), ("extra files", "text labels")),
        ImageBlueprint(2, "COLLECTION OVERVIEW", "Explain what the buyer receives.", "four illustrations arranged with consistent scale", ("complete four-image set",), ("large pack", "paper stack")),
        ImageBlueprint(3, "DETAIL PREVIEW", "Show texture and commercial detail.", "close-up crop of several key motifs with breathing room", ("edges", "texture", "print detail"), ("random alternate theme",)),
        ImageBlueprint(4, "USE CASE MOCKUP", "Show a truthful use case.", "simple application preview using the same illustrations", ("cards, journals, crafts, or decor use",), ("formats not included", "template pages")),
    )


def _clipart() -> tuple[ImageBlueprint, ...]:
    return (
        ImageBlueprint(1, "CUSTOMER_ASSET", "Generate buyer-download artwork, not a cover.", "multiple isolated subject elements, separate non-overlapping clipart, transparent or clean removable background", ("main product subject", "isolated elements"), ("text", "title card", "product cover", "mockup framing", "black background")),
        ImageBlueprint(2, "CUSTOMER_ASSET", "Generate coordinated supporting download artwork.", "isolated subject clusters and small accents, separate non-overlapping clipart elements", ("supporting subject elements",), ("labels", "packaging", "poster layout", "cover design")),
        ImageBlueprint(3, "CUSTOMER_ASSET", "Generate small coordinating accent artwork.", "individual accents with clean edges and generous spacing", ("accent elements",), ("typography", "signs", "cards", "panels")),
        ImageBlueprint(4, "CUSTOMER_ASSET", "Generate additional buyer-download artwork.", "cohesive isolated customer assets, no promotional layout", ("additional coordinated elements",), ("Etsy thumbnail text", "collection title", "digital product cover")),
    )


def _digital_paper() -> tuple[ImageBlueprint, ...]:
    return (
        ImageBlueprint(1, "HERO COVER", "Show pattern style clearly.", "single full-bleed pattern preview", ("one seamless pattern",), ("collage", "text")),
        ImageBlueprint(2, "COLLECTION OVERVIEW", "Show coordinated pattern variety.", "clean four-swatch overview", ("coordinated patterns",), ("12-pack claim",)),
        ImageBlueprint(3, "DETAIL PREVIEW", "Show print texture and repeat quality.", "close detail of motif spacing", ("repeatable motifs",), ("mockup-only view",)),
        ImageBlueprint(4, "USE CASE MOCKUP", "Truthful scrapbook/craft use.", "simple craft context with pattern visible", ("scrapbook or card use",), ("physical product",)),
    )


def _wall_art() -> tuple[ImageBlueprint, ...]:
    return (
        ImageBlueprint(1, "HERO COVER", "Finished art thumbnail.", "full artwork centered with generous margins", ("complete artwork",), ("cropped frame", "text")),
        ImageBlueprint(2, "COLLECTION OVERVIEW", "Show all included ratios or pieces.", "clean gallery overview", ("included art",), ("extra prints",)),
        ImageBlueprint(3, "DETAIL PREVIEW", "Show texture/detail.", "close-up of artwork detail", ("brushwork", "edges"), ("blurry preview",)),
        ImageBlueprint(4, "USE CASE MOCKUP", "Truthful wall display.", "simple wall-display context", ("same artwork",), ("unrelated decor set",)),
    )


def _planner_stickers() -> tuple[ImageBlueprint, ...]:
    return (
        ImageBlueprint(1, "HERO COVER", "Clear planner icon collection thumbnail.", "grouped individual icons, no sheet template", ("icons",), ("text", "layout template")),
        ImageBlueprint(2, "COLLECTION OVERVIEW", "Show included icons.", "four groups of individual elements", ("all elements",), ("editable planner",)),
        ImageBlueprint(3, "DETAIL PREVIEW", "Show cuttable edges.", "close view with clean outlines", ("clean edges",), ("random words",)),
        ImageBlueprint(4, "USE CASE MOCKUP", "Planner use without implying templates.", "icons placed near blank planner context", ("decorative use",), ("included planner pages",)),
    )


def _journal_elements() -> tuple[ImageBlueprint, ...]:
    return _digital_illustration_collection()


def _greeting_card() -> tuple[ImageBlueprint, ...]:
    return _printable()


def _printable() -> tuple[ImageBlueprint, ...]:
    return _digital_illustration_collection()
