"""Reusable prompt-block builder for Creative Director outputs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from project_aurora.creative.creative_brief import CreativeBrief


PROMPT_VERSION = "creative-director-v1"


@dataclass(frozen=True, slots=True)
class CreativePrompt:
    """Prompt composed from reusable blocks."""

    subject: str
    style: str
    composition: str
    color: str
    texture: str
    quality: str
    commercial_requirements: str
    negative_prompt: str
    final_prompt: str
    prompt_version: str = PROMPT_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "subject": self.subject,
            "style": self.style,
            "composition": self.composition,
            "color": self.color,
            "texture": self.texture,
            "quality": self.quality,
            "commercial_requirements": self.commercial_requirements,
            "negative_prompt": self.negative_prompt,
            "final_prompt": self.final_prompt,
            "prompt_version": self.prompt_version,
        }


class CreativePromptBuilder:
    """Compose production prompts from brief blocks."""

    def compose(self, brief: CreativeBrief, product_name: str = "") -> CreativePrompt:
        subject = f"Subject: {product_name or brief.product_name or brief.theme}"
        style = (
            f"Style: {brief.illustration_style}; "
            f"lighting: {brief.lighting_style}; mood: {brief.emotion}"
        )
        composition = f"Composition: {brief.composition_style}"
        color = (
            "Color: "
            f"primary {brief.color_palette.primary}, secondary {brief.color_palette.secondary}, "
            f"accent {brief.color_palette.accent}, neutral {brief.color_palette.neutral}, "
            f"background {brief.color_palette.background}"
        )
        texture = f"Texture: {brief.texture_style}"
        quality = "Quality: cohesive collection artwork, high-detail, Etsy-ready commercial finish"
        commercial = f"Commercial requirements: {brief.commercial_positioning}"
        negative = "No watermark, No logo, No copyrighted characters, No inconsistent style, No muddy palette"
        final_prompt = "\n".join(
            (
                subject,
                style,
                composition,
                color,
                texture,
                quality,
                commercial,
            )
        )
        return CreativePrompt(
            subject=subject,
            style=style,
            composition=composition,
            color=color,
            texture=texture,
            quality=quality,
            commercial_requirements=commercial,
            negative_prompt=negative,
            final_prompt=final_prompt,
        )
