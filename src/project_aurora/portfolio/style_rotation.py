"""Portfolio style library and rotation helpers."""

from __future__ import annotations

from project_aurora.style_intelligence.style_library_builder import StyleLibraryBuilder


FALLBACK_STYLES: tuple[str, ...] = (
    "Watercolor",
    "Hand Painted",
    "Vintage",
    "Botanical",
    "Minimalist",
    "Scandinavian",
    "French Country",
    "Whimsical",
    "Cute",
    "Kawaii",
    "Retro",
    "Mid Century",
    "Boho",
    "Cottagecore",
    "Dark Academia",
    "Victorian",
    "Storybook",
    "Children's Book",
    "Ink Illustration",
    "Realistic",
    "Soft Pastel",
    "Bold Modern",
    "Folk Art",
    "Gouache",
    "Pencil Sketch",
    "Oil Painting",
    "Flat Design",
)


class PortfolioStyleLibrary:
    """Maintain broad production style families for portfolio planning."""

    def __init__(self, styles: tuple[str, ...] | None = None) -> None:
        seed_styles = tuple(
            profile.style_name
            for profile in StyleLibraryBuilder().build_seed_library()
        )
        combined = styles or (*seed_styles, *FALLBACK_STYLES)
        self._styles = tuple(dict.fromkeys(combined))

    @property
    def styles(self) -> tuple[str, ...]:
        """Return available style names."""
        return self._styles

    def rotate(self, preferred_style: str, used_styles: tuple[str, ...]) -> str:
        """Return the preferred style unless it has been overused in context."""
        normalized_used = {style.casefold() for style in used_styles}
        if preferred_style.casefold() not in normalized_used:
            return preferred_style
        for style in self._styles:
            if style.casefold() not in normalized_used:
                return style
        return preferred_style
