"""Muse style profile model."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class MuseStyleProfile:
    """Production-ready style metadata used by Muse."""

    name: str
    description: str
    typical_color_palette: tuple[str, ...]
    rendering_method: str
    target_audience: tuple[str, ...]
    products_it_fits: tuple[str, ...]
    avoid_using_with: tuple[str, ...]
    commercial_appeal: int
    difficulty: int
    trend_score: int
    seasonality: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("Style name cannot be empty.")
        if not self.description.strip():
            raise ValueError("Style description cannot be empty.")
        if not self.rendering_method.strip():
            raise ValueError("Rendering method cannot be empty.")
        for field_name in ("commercial_appeal", "difficulty", "trend_score"):
            value = getattr(self, field_name)
            if not 0 <= value <= 100:
                raise ValueError(f"{field_name} must be between 0 and 100.")
        object.__setattr__(self, "typical_color_palette", tuple(self.typical_color_palette))
        object.__setattr__(self, "target_audience", tuple(self.target_audience))
        object.__setattr__(self, "products_it_fits", tuple(self.products_it_fits))
        object.__setattr__(self, "avoid_using_with", tuple(self.avoid_using_with))
        object.__setattr__(self, "seasonality", tuple(self.seasonality))
