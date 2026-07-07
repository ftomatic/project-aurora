"""Reusable Prompt Factory composition library."""

from __future__ import annotations

from project_aurora.prompt_factory.prompt_components import PromptComponent


COMPOSITION_LIBRARY: dict[str, PromptComponent] = {
    "Centered": PromptComponent(
        name="Centered",
        phrases=(
            "centered composition",
            "single clear focal point",
            "balanced spacing",
        ),
    ),
    "Border": PromptComponent(
        name="Border",
        phrases=("decorative border layout", "even edge spacing"),
    ),
    "Corner Cluster": PromptComponent(
        name="Corner Cluster",
        phrases=("corner cluster arrangement", "open center area"),
    ),
    "Pattern": PromptComponent(
        name="Pattern",
        phrases=("repeat pattern layout", "balanced motif distribution"),
    ),
    "Seamless": PromptComponent(
        name="Seamless",
        phrases=("seamless repeat", "tileable edges", "continuous pattern"),
    ),
    "Frame Layout": PromptComponent(
        name="Frame Layout",
        phrases=("framed composition", "central blank space", "ornamental frame"),
    ),
}


def get_composition(name: str) -> PromptComponent:
    """Return a composition component by name."""
    try:
        return COMPOSITION_LIBRARY[name]
    except KeyError as error:
        raise ValueError(f"Unknown composition: {name}.") from error
