"""Reusable prompt templates for Aurora's Prompt Factory."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PromptTemplate:
    """Creative style template for deterministic prompt building."""

    name: str
    descriptors: tuple[str, ...]
    lighting: str
    atmosphere: str
    finish: str


PROMPT_TEMPLATES: dict[str, PromptTemplate] = {
    "Storybook": PromptTemplate(
        name="Storybook",
        descriptors=("storybook illustration", "children's book style"),
        lighting="warm lighting",
        atmosphere="gentle whimsical atmosphere",
        finish="commercial clipart, isolated elements, white background",
    ),
    "Watercolor": PromptTemplate(
        name="Watercolor",
        descriptors=("soft watercolor", "delicate painted texture"),
        lighting="soft natural lighting",
        atmosphere="light airy handmade feel",
        finish="printable artwork, white background",
    ),
    "Oil Painting": PromptTemplate(
        name="Oil Painting",
        descriptors=("oil painting", "rich brush texture"),
        lighting="dramatic studio lighting",
        atmosphere="classic painterly atmosphere",
        finish="highly detailed wall-art composition",
    ),
    "Vintage": PromptTemplate(
        name="Vintage",
        descriptors=("vintage illustration", "nostalgic color palette"),
        lighting="muted golden lighting",
        atmosphere="retro heirloom atmosphere",
        finish="aged paper inspired printable design",
    ),
    "Cottagecore": PromptTemplate(
        name="Cottagecore",
        descriptors=("cottagecore illustration", "sweet pastoral details"),
        lighting="warm dappled lighting",
        atmosphere="cozy garden atmosphere",
        finish="commercial clipart, isolated elements, white background",
    ),
    "Boho": PromptTemplate(
        name="Boho",
        descriptors=("boho design", "organic decorative shapes"),
        lighting="sun-washed lighting",
        atmosphere="relaxed artisan atmosphere",
        finish="neutral printable design with handmade charm",
    ),
    "Minimalist": PromptTemplate(
        name="Minimalist",
        descriptors=("minimalist design", "clean simple composition"),
        lighting="bright even lighting",
        atmosphere="calm modern atmosphere",
        finish="crisp printable layout with generous negative space",
    ),
    "Fantasy": PromptTemplate(
        name="Fantasy",
        descriptors=("fantasy illustration", "magical story details"),
        lighting="glowing enchanted lighting",
        atmosphere="dreamy magical atmosphere",
        finish="highly detailed commercial illustration",
    ),
    "Nursery": PromptTemplate(
        name="Nursery",
        descriptors=("nursery illustration", "soft baby-friendly details"),
        lighting="gentle pastel lighting",
        atmosphere="sweet calming nursery atmosphere",
        finish="printable nursery artwork, white background",
    ),
    "Seasonal": PromptTemplate(
        name="Seasonal",
        descriptors=("seasonal printable design", "festive details"),
        lighting="bright celebratory lighting",
        atmosphere="fresh seasonal atmosphere",
        finish="polished commercial printable asset",
    ),
}

NEGATIVE_PROMPT_LINES: tuple[str, ...] = (
    "No text",
    "No watermark",
    "No logo",
    "No border",
    "No cropped objects",
    "No duplicate subjects",
    "No blurry details",
)


def select_template_names(
    product_name: str,
    product_category: str,
    content_type: str,
) -> tuple[str, ...]:
    """Choose prompt template names from queue item context."""
    haystack = f"{product_name} {product_category} {content_type}".casefold()

    if any(term in haystack for term in ("birthday", "party", "strawberry")):
        return ("Storybook", "Watercolor")
    if any(term in haystack for term in ("mushroom", "fairy", "dragon")):
        return ("Fantasy", "Storybook")
    if any(term in haystack for term in ("nursery", "baby", "rainbow")):
        return ("Nursery", "Watercolor")
    if any(term in haystack for term in ("boho", "desert", "sun")):
        return ("Boho", "Minimalist")
    if any(term in haystack for term in ("vintage", "retro")):
        return ("Vintage",)
    if any(term in haystack for term in ("christmas", "halloween", "winter")):
        return ("Seasonal", "Watercolor")
    if "wall art" in haystack:
        return ("Oil Painting",)
    if any(term in haystack for term in ("cottage", "garden", "flower")):
        return ("Cottagecore", "Watercolor")
    return ("Minimalist",)


def get_templates(template_names: tuple[str, ...]) -> tuple[PromptTemplate, ...]:
    """Return templates for selected names."""
    return tuple(PROMPT_TEMPLATES[name] for name in template_names)
