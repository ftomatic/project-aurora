"""Creative brief models for Aurora's Creative Director."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import uuid4


@dataclass(frozen=True, slots=True)
class ColorPalette:
    """Harmonious palette for one product or collection."""

    palette_id: str
    primary: str
    secondary: str
    accent: str
    neutral: str
    background: str
    seasonal_shift: str

    def to_dict(self) -> dict[str, str]:
        return {
            "palette_id": self.palette_id,
            "primary": self.primary,
            "secondary": self.secondary,
            "accent": self.accent,
            "neutral": self.neutral,
            "background": self.background,
            "seasonal_shift": self.seasonal_shift,
        }


@dataclass(frozen=True, slots=True)
class Moodboard:
    """Structured, non-image moodboard guidance."""

    moodboard_id: str
    mood_keywords: tuple[str, ...]
    visual_motifs: tuple[str, ...]
    materials: tuple[str, ...]
    textures: tuple[str, ...]
    lighting: tuple[str, ...]
    composition_examples: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "moodboard_id": self.moodboard_id,
            "mood_keywords": list(self.mood_keywords),
            "visual_motifs": list(self.visual_motifs),
            "materials": list(self.materials),
            "textures": list(self.textures),
            "lighting": list(self.lighting),
            "composition_examples": list(self.composition_examples),
        }


@dataclass(frozen=True, slots=True)
class CreativeScore:
    """Creative quality score dimensions."""

    originality: int
    commercial_appeal: int
    brand_consistency: int
    visual_harmony: int
    collection_fit: int

    @property
    def overall_creative_score(self) -> int:
        return round(
            (
                self.originality
                + self.commercial_appeal
                + self.brand_consistency
                + self.visual_harmony
                + self.collection_fit
            )
            / 5
        )

    def to_dict(self) -> dict[str, int]:
        return {
            "originality": self.originality,
            "commercial_appeal": self.commercial_appeal,
            "brand_consistency": self.brand_consistency,
            "visual_harmony": self.visual_harmony,
            "collection_fit": self.collection_fit,
            "overall_creative_score": self.overall_creative_score,
        }


@dataclass(frozen=True, slots=True)
class CreativeBrief:
    """Visual identity brief for an approved opportunity."""

    theme: str
    target_audience: str
    emotion: str
    color_palette: ColorPalette
    illustration_style: str
    composition_style: str
    lighting_style: str
    texture_style: str
    typography_style: str
    commercial_positioning: str
    style_id: str
    palette_id: str
    moodboard_id: str
    prompt_version: str
    creative_score: CreativeScore
    moodboard: Moodboard
    collection_name: str = ""
    product_name: str = ""
    brief_id: str = field(default_factory=lambda: str(uuid4()))
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "brief_id": self.brief_id,
            "theme": self.theme,
            "target_audience": self.target_audience,
            "emotion": self.emotion,
            "color_palette": self.color_palette.to_dict(),
            "illustration_style": self.illustration_style,
            "composition_style": self.composition_style,
            "lighting_style": self.lighting_style,
            "texture_style": self.texture_style,
            "typography_style": self.typography_style,
            "commercial_positioning": self.commercial_positioning,
            "style_id": self.style_id,
            "palette_id": self.palette_id,
            "moodboard_id": self.moodboard_id,
            "prompt_version": self.prompt_version,
            "creative_score": self.creative_score.to_dict(),
            "moodboard": self.moodboard.to_dict(),
            "collection_name": self.collection_name,
            "product_name": self.product_name,
            "created_at": self.created_at.isoformat(),
        }
