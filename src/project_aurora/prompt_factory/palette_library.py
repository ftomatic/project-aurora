"""Reusable Prompt Factory color palette library."""

from __future__ import annotations

from project_aurora.prompt_factory.prompt_components import PromptComponent


PALETTE_LIBRARY: dict[str, PromptComponent] = {
    "Strawberry Summer": PromptComponent(
        name="Strawberry Summer",
        phrases=(
            "cream",
            "sage",
            "blush pink",
            "warm yellow",
            "berry red",
        ),
    ),
    "Cream": PromptComponent(
        name="Cream",
        phrases=("cream", "ivory", "warm white"),
    ),
    "Sage": PromptComponent(
        name="Sage",
        phrases=("sage green", "soft leaf green", "muted herb green"),
    ),
    "Blush Pink": PromptComponent(
        name="Blush Pink",
        phrases=("blush pink", "soft rose", "pale petal pink"),
    ),
    "Warm Yellow": PromptComponent(
        name="Warm Yellow",
        phrases=("warm yellow", "butter yellow", "soft sunshine"),
    ),
    "Berry Red": PromptComponent(
        name="Berry Red",
        phrases=("berry red", "strawberry red", "deep fruit red"),
    ),
}


def get_palette(name: str) -> PromptComponent:
    """Return a palette component by name."""
    try:
        return PALETTE_LIBRARY[name]
    except KeyError as error:
        raise ValueError(f"Unknown palette: {name}.") from error
