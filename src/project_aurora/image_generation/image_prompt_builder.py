"""Structured image prompt builder for Aurora production jobs."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from project_aurora.creative.product_creative_director import ProductionCreativeBrief
from project_aurora.research.seasonal_intelligence import SeasonalReview


FORBIDDEN_TEXT_PROMPT_TERMS = (
    "with text",
    "include text",
    "add text",
    "display the word",
    "title card",
    "collection cover",
    "digital product cover",
    "etsy thumbnail text",
    "clipart label",
    "illustration collection title",
    "product name inside the image",
    "typography that says",
    "words that say",
    "class of",
)


@dataclass(frozen=True, slots=True)
class BuiltImagePrompt:
    """One blueprint-specific image prompt."""

    image_number: int
    blueprint_role: str
    prompt: str
    negative_prompt: str
    consistency_key: str
    required_objects: tuple[str, ...]
    forbidden_objects: tuple[str, ...]
    text_policy: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "image_number": self.image_number,
            "blueprint_role": self.blueprint_role,
            "prompt": self.prompt,
            "negative_prompt": self.negative_prompt,
            "consistency_key": self.consistency_key,
            "required_objects": list(self.required_objects),
            "forbidden_objects": list(self.forbidden_objects),
            "text_policy": self.text_policy,
        }


class StructuredImagePromptBuilder:
    """Build prompts from creative brief fields instead of title keywords."""

    def build_prompts(
        self,
        brief: ProductionCreativeBrief,
        seasonal_review: SeasonalReview,
    ) -> tuple[BuiltImagePrompt, ...]:
        """Return four blueprint-role prompts."""
        prompts = tuple(
            self._build_one(brief, seasonal_review, blueprint)
            for blueprint in brief.image_blueprint
        )
        for prompt in prompts:
            validate_prompt_text_policy(prompt.prompt)
        return prompts

    def _build_one(
        self,
        brief: ProductionCreativeBrief,
        seasonal_review: SeasonalReview,
        blueprint: Any,
    ) -> BuiltImagePrompt:
        negative = ", ".join(brief.negative_prompt)
        prompt = (
            f"Product purpose: {brief.commercial_use_case}.\n"
            f"Exact subject: {brief.visual_story}.\n"
            f"Required objects: {', '.join(brief.required_objects)}.\n"
            f"Optional objects: {', '.join(brief.optional_objects)}.\n"
            f"Composition: {blueprint.composition}; {'; '.join(brief.composition_rules)}.\n"
            f"Style: {brief.style}.\n"
            f"Rendering family: {brief.rendering_family}.\n"
            f"Palette: {', '.join(brief.palette)}.\n"
            f"Background: {'; '.join(brief.background_rules)}.\n"
            f"Lighting: {'; '.join(brief.lighting_rules)}.\n"
            f"Texture: {'; '.join(brief.texture_rules)}.\n"
            f"Etsy commercial requirements: high-quality customer-download digital artwork, 300 DPI production intent, cohesive product set, no marketing cover layout.\n"
            f"Blueprint role: Image {blueprint.image_number} - {blueprint.role}; {blueprint.purpose}.\n"
            f"Must show: {', '.join(blueprint.must_show)}.\n"
            f"Must not imply: {', '.join(blueprint.must_not_imply)}.\n"
            f"Seasonal decision: {seasonal_review.production_decision}; {seasonal_review.reason}.\n"
            f"Text policy: {brief.text_policy}. Do not include visible text, words, letters, numbers, dates, years, logos, labels, captions, or signatures.\n"
            f"Consistency instructions: {'; '.join(brief.output_consistency_rules)}.\n"
            f"Consistency key: {brief.consistency_key}.\n"
            f"Negative instructions: {negative}."
        )
        return BuiltImagePrompt(
            image_number=int(blueprint.image_number),
            blueprint_role=str(blueprint.role),
            prompt=prompt,
            negative_prompt=negative,
            consistency_key=brief.consistency_key,
            required_objects=brief.required_objects,
            forbidden_objects=brief.forbidden_objects,
            text_policy=brief.text_policy,
        )


def validate_prompt_text_policy(prompt: str) -> None:
    """Reject prompts that intentionally request visible generated text."""
    lowered = prompt.casefold()
    for term in FORBIDDEN_TEXT_PROMPT_TERMS:
        if term in lowered:
            raise ValueError(f"Prompt violates no-text policy: {term}.")
    years = re.findall(r"\b(20\d{2}|19\d{2})\b", prompt)
    if years:
        raise ValueError(f"Prompt contains explicit year(s): {', '.join(years)}.")
