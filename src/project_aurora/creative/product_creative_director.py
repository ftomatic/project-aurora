"""Production Creative Director for one product job."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from hashlib import sha1
from typing import Any

from project_aurora.creative.image_blueprints import ImageBlueprint, blueprints_for_product
from project_aurora.planning.production_queue_manager import ProductionJob


TEXT_POLICY_FORBIDDEN = "FORBIDDEN"
DEFAULT_FORBIDDEN_TEXT = (
    "years",
    "dates",
    "random words",
    "logos",
    "watermarks",
    "signatures",
    "fake typography",
    "gibberish text",
    "malformed letters",
    "brand names",
    "copyrighted characters",
    "unrelated objects",
)


@dataclass(frozen=True, slots=True)
class ProductionCreativeBrief:
    """Concrete commercially usable art direction before image generation."""

    product_name: str
    product_type: str
    target_customer: str
    commercial_use_case: str
    theme: str
    visual_story: str
    style: str
    rendering_family: str
    palette: tuple[str, ...]
    mood: str
    subject_list: tuple[str, ...]
    required_objects: tuple[str, ...]
    optional_objects: tuple[str, ...]
    forbidden_objects: tuple[str, ...]
    composition_rules: tuple[str, ...]
    background_rules: tuple[str, ...]
    texture_rules: tuple[str, ...]
    lighting_rules: tuple[str, ...]
    negative_prompt: tuple[str, ...]
    text_policy: str
    output_consistency_rules: tuple[str, ...]
    image_blueprint: tuple[ImageBlueprint, ...]
    consistency_key: str
    confidence: int
    reasoning: str
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "product_name": self.product_name,
            "product_type": self.product_type,
            "target_customer": self.target_customer,
            "commercial_use_case": self.commercial_use_case,
            "theme": self.theme,
            "visual_story": self.visual_story,
            "style": self.style,
            "rendering_family": self.rendering_family,
            "palette": list(self.palette),
            "mood": self.mood,
            "subject_list": list(self.subject_list),
            "required_objects": list(self.required_objects),
            "optional_objects": list(self.optional_objects),
            "forbidden_objects": list(self.forbidden_objects),
            "composition_rules": list(self.composition_rules),
            "background_rules": list(self.background_rules),
            "texture_rules": list(self.texture_rules),
            "lighting_rules": list(self.lighting_rules),
            "negative_prompt": list(self.negative_prompt),
            "text_policy": self.text_policy,
            "output_consistency_rules": list(self.output_consistency_rules),
            "image_blueprint": [
                {
                    "image_number": item.image_number,
                    "role": item.role,
                    "purpose": item.purpose,
                    "composition": item.composition,
                    "must_show": list(item.must_show),
                    "must_not_imply": list(item.must_not_imply),
                }
                for item in self.image_blueprint
            ],
            "consistency_key": self.consistency_key,
            "confidence": self.confidence,
            "reasoning": self.reasoning,
            "created_at": self.created_at.isoformat(),
        }


class ProductionCreativeDirector:
    """Turn a queue job into concrete creative direction."""

    def create_brief(self, job: ProductionJob, art_direction: Any) -> ProductionCreativeBrief:
        """Return a production-safe creative brief for one job."""
        subjects = _subjects_for(job)
        required = _required_objects_for(job)
        palette = tuple(
            item.strip()
            for item in str(getattr(art_direction, "palette", "") or "cream, sage, blush, warm gold").split(",")
            if item.strip()
        )[:6]
        style = str(getattr(art_direction, "recommended_style", "") or job.style)
        rendering = str(getattr(art_direction, "rendering_family", "") or getattr(art_direction, "rendering_method", "") or style)
        composition = str(getattr(art_direction, "composition", "") or "cohesive product collection layout")
        background = str(getattr(art_direction, "background_treatment", "") or "clean commercial background")
        lighting = str(getattr(art_direction, "lighting", "") or "soft professional lighting")
        texture = str(getattr(art_direction, "texture", "") or "commercial printable detail")
        mood = str(getattr(art_direction, "mood", "") or "cohesive commercial")
        consistency_key = _consistency_key(
            style=style,
            palette=palette,
            rendering=rendering,
            background=background,
            lighting=lighting,
            texture=texture,
            mood=mood,
        )
        forbidden = (*DEFAULT_FORBIDDEN_TEXT, *_forbidden_for(job))
        negative = (
            "no text",
            "no words",
            "no letters",
            "no numbers",
            "no dates",
            "no year",
            "no logo",
            "no watermark",
            "no signature",
            "no typography",
            "no labels",
            "no captions",
            "no cropped main subject",
            "no unrelated objects",
        )
        return ProductionCreativeBrief(
            product_name=job.product_name,
            product_type=job.category,
            target_customer=job.target_customer or "Etsy digital printable buyers",
            commercial_use_case=_commercial_use_case(job),
            theme=_theme_for(job),
            visual_story=_visual_story(job, subjects),
            style=style,
            rendering_family=rendering,
            palette=palette or ("cream", "sage", "blush", "warm gold"),
            mood=mood,
            subject_list=subjects,
            required_objects=required,
            optional_objects=_optional_objects_for(job),
            forbidden_objects=forbidden,
            composition_rules=(
                composition,
                "all four images must feel like one coordinated product",
                "leave breathing room so no important object is cut off",
            ),
            background_rules=(background, "background must support Etsy thumbnail clarity"),
            texture_rules=(texture, "consistent texture across all four images"),
            lighting_rules=(lighting, "consistent lighting across all four images"),
            negative_prompt=negative,
            text_policy=TEXT_POLICY_FORBIDDEN,
            output_consistency_rules=(
                "same style family",
                "same palette",
                "same rendering family",
                "same mood",
                "same object vocabulary",
                f"consistency key {consistency_key}",
            ),
            image_blueprint=blueprints_for_product(job.category),
            consistency_key=consistency_key,
            confidence=95,
            reasoning="Generated from product, category, Muse art direction, and merchant-safe text policy.",
        )


def _subjects_for(job: ProductionJob) -> tuple[str, ...]:
    tokens = [token for token in job.product_name.replace("-", " ").split() if len(token) > 2]
    return tuple(dict.fromkeys(token.casefold() for token in tokens))[:8]


def _required_objects_for(job: ProductionJob) -> tuple[str, ...]:
    lowered = job.product_name.casefold()
    if "graduation" in lowered:
        return ("graduation cap", "diploma", "ribbon", "laurel sprigs", "stars", "subtle confetti")
    if "teacher" in lowered or "classroom" in lowered:
        return ("apple", "pencil", "book", "stars", "school supplies")
    if "mushroom" in lowered:
        return ("mushrooms", "foliage", "woodland accents")
    if "wedding" in lowered:
        return ("floral sprigs", "ribbon", "soft botanical accents")
    if "birthday" in lowered:
        return ("celebration motifs", "confetti", "party accents")
    return tuple(_subjects_for(job)[:4]) or ("coordinated illustration motifs",)


def _optional_objects_for(job: ProductionJob) -> tuple[str, ...]:
    lowered = job.product_name.casefold()
    if "storybook" in lowered or "woodland" in lowered:
        return ("rabbits", "foxes", "cottages", "flowers")
    return ("small decorative accents", "soft botanical details")


def _forbidden_for(job: ProductionJob) -> tuple[str, ...]:
    lowered = job.product_name.casefold()
    forbidden = ["unrelated themes", "stale assets from another product"]
    if "graduation" in lowered:
        forbidden.extend(("class year", "2024", "2025", "2026", "2027"))
    return tuple(forbidden)


def _commercial_use_case(job: ProductionJob) -> str:
    return "four commercial PNG illustrations for Etsy digital download customers"


def _theme_for(job: ProductionJob) -> str:
    source = job.original_product_name or job.product_name
    return " ".join(source.split()[:5])


def _visual_story(job: ProductionJob, subjects: tuple[str, ...]) -> str:
    return (
        f"A cohesive {job.category} built around "
        f"{', '.join(subjects[:5]) or job.product_name} with one shared visual identity."
    )


def _consistency_key(
    *,
    style: str,
    palette: tuple[str, ...],
    rendering: str,
    background: str,
    lighting: str,
    texture: str,
    mood: str,
) -> str:
    raw = "|".join((style, ",".join(palette), rendering, background, lighting, texture, mood))
    return sha1(raw.encode("utf-8")).hexdigest()[:12]
