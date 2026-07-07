"""Reusable Prompt Factory style library."""

from __future__ import annotations

from project_aurora.prompt_factory.prompt_components import PromptComponent


STYLE_LIBRARY: dict[str, PromptComponent] = {
    "Storybook Watercolor": PromptComponent(
        name="Storybook Watercolor",
        phrases=(
            "storybook watercolor illustration",
            "soft whimsical details",
            "children's book charm",
            "gentle hand-painted texture",
        ),
    ),
    "Vintage Botanical": PromptComponent(
        name="Vintage Botanical",
        phrases=(
            "vintage botanical illustration",
            "delicate engraved details",
            "aged paper elegance",
        ),
    ),
    "Soft Cottagecore": PromptComponent(
        name="Soft Cottagecore",
        phrases=(
            "soft cottagecore illustration",
            "garden-inspired handmade charm",
            "sweet pastoral details",
        ),
    ),
    "Pastel Nursery": PromptComponent(
        name="Pastel Nursery",
        phrases=(
            "pastel nursery illustration",
            "soft baby-friendly shapes",
            "calming gentle mood",
        ),
    ),
    "Vintage Christmas": PromptComponent(
        name="Vintage Christmas",
        phrases=(
            "vintage Christmas illustration",
            "nostalgic holiday warmth",
            "classic festive details",
        ),
    ),
    "Cute Halloween": PromptComponent(
        name="Cute Halloween",
        phrases=(
            "cute Halloween illustration",
            "friendly spooky details",
            "playful seasonal charm",
        ),
    ),
    "Minimal Modern": PromptComponent(
        name="Minimal Modern",
        phrases=(
            "minimal modern design",
            "clean simplified shapes",
            "refined negative space",
        ),
    ),
}


def get_style(name: str) -> PromptComponent:
    """Return a style component by name."""
    try:
        return STYLE_LIBRARY[name]
    except KeyError as error:
        raise ValueError(f"Unknown style: {name}.") from error
