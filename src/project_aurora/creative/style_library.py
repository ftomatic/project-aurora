"""Reusable Creative Director style library."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class CreativeStyle:
    """Reusable visual style definition."""

    style_id: str
    name: str
    color_palettes: tuple[tuple[str, ...], ...]
    line_quality: str
    texture: str
    rendering_approach: str
    background_treatment: str
    visual_mood: tuple[str, ...]
    target_categories: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "style_id": self.style_id,
            "name": self.name,
            "color_palettes": [list(palette) for palette in self.color_palettes],
            "line_quality": self.line_quality,
            "texture": self.texture,
            "rendering_approach": self.rendering_approach,
            "background_treatment": self.background_treatment,
            "visual_mood": list(self.visual_mood),
            "target_categories": list(self.target_categories),
        }


class CreativeStyleLibrary:
    """Load and choose Creative Director styles."""

    def __init__(self, styles: tuple[CreativeStyle, ...] | None = None) -> None:
        self._styles = styles or _default_styles()

    @property
    def styles(self) -> tuple[CreativeStyle, ...]:
        return self._styles

    def get(self, style_id_or_name: str) -> CreativeStyle:
        normalized = _normalize(style_id_or_name)
        for style in self._styles:
            if normalized in {_normalize(style.style_id), _normalize(style.name)}:
                return style
        raise ValueError(f"Unknown creative style: {style_id_or_name}")

    def select(self, *, theme: str, product_type: str = "", audience: str = "") -> CreativeStyle:
        haystack = _normalize(f"{theme} {product_type} {audience}")
        scored = sorted(
            self._styles,
            key=lambda style: (
                -_style_score(style, haystack),
                style.name,
            ),
        )
        return scored[0]


def _style_score(style: CreativeStyle, haystack: str) -> int:
    score = 40
    score += sum(18 for category in style.target_categories if _normalize(category) in haystack)
    score += sum(4 for mood in style.visual_mood if _normalize(mood) in haystack)
    return score


def _style(
    style_id: str,
    name: str,
    palettes: tuple[tuple[str, ...], ...],
    line_quality: str,
    texture: str,
    rendering: str,
    background: str,
    mood: tuple[str, ...],
    categories: tuple[str, ...],
) -> CreativeStyle:
    return CreativeStyle(
        style_id=style_id,
        name=name,
        color_palettes=palettes,
        line_quality=line_quality,
        texture=texture,
        rendering_approach=rendering,
        background_treatment=background,
        visual_mood=mood,
        target_categories=categories,
    )


def _default_styles() -> tuple[CreativeStyle, ...]:
    return (
        _style("watercolor", "Watercolor", (("sage", "blush", "cream", "berry"),), "soft organic edges", "paper grain", "layered watercolor wash", "clean white or transparent", ("soft", "handmade"), ("nursery", "floral", "party", "clipart")),
        _style("vintage_botanical", "Vintage Botanical", (("olive", "cream", "sepia", "dusty rose"),), "delicate botanical line", "aged paper texture", "botanical wash and ink", "warm cream", ("organic", "nostalgic"), ("kitchen", "botanical", "wedding", "wall art")),
        _style("scandinavian", "Scandinavian", (("warm gray", "ivory", "sage", "terracotta"),), "simple geometric line", "matte paper", "minimal flat rendering", "airy neutral", ("calm", "modern"), ("nursery", "wall art", "digital paper")),
        _style("cottagecore", "Cottagecore", (("moss", "cream", "wildflower", "berry"),), "whimsical hand line", "soft paper texture", "storybook watercolor details", "light woodland", ("cozy", "romantic"), ("mushroom", "strawberry", "woodland", "birthday")),
        _style("boho", "Boho", (("terracotta", "mustard", "cream", "clay"),), "rounded friendly line", "matte poster texture", "warm flat illustration", "neutral cream", ("warm", "friendly"), ("teacher", "bridal", "nursery")),
        _style("mid_century", "Mid-Century Modern", (("teal", "mustard", "coral", "charcoal"),), "confident clean shape", "subtle print grain", "bold retro shapes", "flat color field", ("playful", "retro"), ("wall art", "kitchen", "stickers")),
        _style("minimalist", "Minimalist", (("black", "ivory", "warm gray", "taupe"),), "fine restrained line", "smooth matte", "minimal line art", "open white space", ("quiet", "premium"), ("wedding", "wall art", "teacher")),
        _style("french_country", "French Country", (("cream", "olive", "terracotta", "linen"),), "rustic elegant line", "linen paper", "vintage painted botanical", "warm neutral", ("warm", "organic"), ("kitchen", "botanical", "farmhouse")),
        _style("whimsical_storybook", "Whimsical Storybook", (("sky blue", "blush", "leaf green", "butter yellow"),), "storybook character line", "soft paper grain", "children's book illustration", "bright clean", ("sweet", "imaginative"), ("nursery", "birthday", "clipart", "children")),
        _style("dark_academia", "Dark Academia", (("ink", "burgundy", "aged gold", "espresso"),), "antique engraved line", "aged paper and oil texture", "moody literary illustration", "dark warm background", ("scholarly", "moody"), ("dark academia", "library", "wall art")),
        _style("coastal", "Coastal", (("sea glass", "sand", "navy", "shell"),), "loose coastal line", "salt-washed paper", "breezy watercolor", "light airy", ("breezy", "relaxed"), ("coastal", "summer", "digital paper")),
        _style("farmhouse", "Farmhouse", (("white", "black", "sage", "wood"),), "rustic clean line", "painted sign texture", "simple rustic illustration", "whitewashed", ("homey", "rustic"), ("farmhouse", "kitchen", "wall art")),
    )


def _normalize(value: str) -> str:
    return " ".join(value.casefold().replace("-", " ").replace("_", " ").split())
