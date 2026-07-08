"""Reusable visual style profile model."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class StyleProfile:
    """A broad, original visual style-family definition."""

    style_id: str
    style_name: str
    description: str
    visual_characteristics: tuple[str, ...]
    color_palette: tuple[str, ...]
    brush_style: str
    line_style: str
    lighting: str
    composition: str
    texture: str
    recommended_products: tuple[str, ...]
    recommended_seasons: tuple[str, ...]
    recommended_audiences: tuple[str, ...]
    confidence: float

    def __post_init__(self) -> None:
        required_values = {
            "style_id": self.style_id,
            "style_name": self.style_name,
            "description": self.description,
            "brush_style": self.brush_style,
            "line_style": self.line_style,
            "lighting": self.lighting,
            "composition": self.composition,
            "texture": self.texture,
        }
        for field_name, value in required_values.items():
            if not value.strip():
                raise ValueError(f"{field_name} cannot be empty.")
        if not 0 <= self.confidence <= 1:
            raise ValueError("confidence must be between 0 and 1.")

        object.__setattr__(
            self,
            "visual_characteristics",
            tuple(self.visual_characteristics),
        )
        object.__setattr__(self, "color_palette", tuple(self.color_palette))
        object.__setattr__(
            self,
            "recommended_products",
            tuple(self.recommended_products),
        )
        object.__setattr__(
            self,
            "recommended_seasons",
            tuple(self.recommended_seasons),
        )
        object.__setattr__(
            self,
            "recommended_audiences",
            tuple(self.recommended_audiences),
        )
