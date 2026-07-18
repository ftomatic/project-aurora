"""Creative Director color intelligence."""

from __future__ import annotations

from project_aurora.creative.creative_brief import ColorPalette
from project_aurora.creative.style_library import CreativeStyle


class PaletteIntelligence:
    """Generate harmonious palettes with seasonal shifts."""

    def generate(
        self,
        *,
        theme: str,
        season: str,
        style: CreativeStyle,
    ) -> ColorPalette:
        base = style.color_palettes[0]
        colors = _seasonal_shift(base, season, theme)
        return ColorPalette(
            palette_id=_palette_id(theme, style.style_id, season),
            primary=colors[0],
            secondary=colors[1],
            accent=colors[2],
            neutral=colors[3],
            background=colors[4],
            seasonal_shift=_shift_label(season, theme),
        )


def _seasonal_shift(base: tuple[str, ...], season: str, theme: str) -> tuple[str, str, str, str, str]:
    lowered = f"{theme} {season}".casefold()
    if "christmas" in lowered or "winter" in lowered:
        return ("pine green", "cranberry", "aged gold", "warm ivory", "soft snow")
    if "halloween" in lowered or "autumn" in lowered or "fall" in lowered:
        return ("pumpkin", "mushroom brown", "moss", "cream", "warm parchment")
    if "summer" in lowered or "strawberry" in lowered:
        return ("berry red", "blush pink", "leaf green", "cream", "white")
    if "wedding" in lowered:
        return ("ivory", "champagne", "dusty rose", "sage", "warm white")
    padded = (*base, "warm white", "cream")
    return (padded[0], padded[1], padded[2], padded[3], padded[4])


def _shift_label(season: str, theme: str) -> str:
    value = f"{theme} {season}".casefold()
    if "winter" in value or "christmas" in value:
        return "winter holiday warmth"
    if "fall" in value or "autumn" in value or "halloween" in value:
        return "autumn earth warmth"
    if "summer" in value:
        return "bright summer freshness"
    if "wedding" in value:
        return "romantic wedding softness"
    return "evergreen balanced palette"


def _palette_id(theme: str, style_id: str, season: str) -> str:
    return "_".join(
        part
        for part in f"{theme}_{style_id}_{season}".casefold().replace("-", "_").split()
    )
