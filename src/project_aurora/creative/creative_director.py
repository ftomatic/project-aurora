"""Aurora Creative Director."""

from __future__ import annotations

from typing import Any

from project_aurora.config.project_profile import ProjectProfile
from project_aurora.creative.collection_engine import CollectionEngine
from project_aurora.creative.collection_plan import CollectionPlan
from project_aurora.creative.creative_brief import (
    CreativeBrief,
    CreativeScore,
)
from project_aurora.creative.creative_qa import CreativeQAEngine, CreativeQAResult
from project_aurora.creative.moodboard import MoodboardGenerator
from project_aurora.creative.palette_intelligence import PaletteIntelligence
from project_aurora.creative.prompt_blocks import (
    PROMPT_VERSION,
    CreativePrompt,
    CreativePromptBuilder,
)
from project_aurora.creative.style_library import (
    CreativeStyle,
    CreativeStyleLibrary,
)
from project_aurora.storage.memory_manager import MemoryManager


class CreativeDirector:
    """Decide what Aurora should produce for a collection."""

    def __init__(
        self,
        collection_engine: CollectionEngine | None = None,
        style_library: CreativeStyleLibrary | None = None,
        memory: MemoryManager | None = None,
    ) -> None:
        self._collection_engine = collection_engine or CollectionEngine()
        self._style_library = style_library or CreativeStyleLibrary()
        self._palette_intelligence = PaletteIntelligence()
        self._moodboard_generator = MoodboardGenerator()
        self._prompt_builder = CreativePromptBuilder()
        self._qa_engine = CreativeQAEngine()
        self._memory = memory

    def plan_collection(
        self,
        research: dict[str, Any],
        strategy: dict[str, Any],
        project_profile: ProjectProfile,
    ) -> CollectionPlan:
        """Return a complete collection plan."""
        return self._collection_engine.build_plan(
            research=research,
            strategy=strategy,
            project_profile=project_profile,
        )

    def create_brief(
        self,
        *,
        theme: str,
        target_audience: str,
        product_name: str = "",
        product_type: str = "",
        season: str = "Evergreen",
        collection_name: str = "",
        commercial_positioning: str = "",
    ) -> CreativeBrief:
        """Generate and persist a Creative Brief for an approved opportunity."""
        style = self._style_library.select(
            theme=theme,
            product_type=product_type,
            audience=target_audience,
        )
        palette = self._palette_intelligence.generate(
            theme=theme,
            season=season,
            style=style,
        )
        emotion = _emotion_for(theme, season, target_audience)
        composition = _composition_for(product_type, theme)
        moodboard = self._moodboard_generator.generate(
            theme=theme,
            audience=target_audience,
            emotion=emotion,
            style=style,
            composition=composition,
        )
        score = _creative_score(style, theme, target_audience, collection_name)
        brief = CreativeBrief(
            theme=theme,
            target_audience=target_audience,
            emotion=emotion,
            color_palette=palette,
            illustration_style=style.name,
            composition_style=composition,
            lighting_style=_lighting_for(style, emotion),
            texture_style=style.texture,
            typography_style=_typography_for(product_type, theme),
            commercial_positioning=(
                commercial_positioning
                or f"Cohesive commercial Etsy artwork for {target_audience}."
            ),
            style_id=style.style_id,
            palette_id=palette.palette_id,
            moodboard_id=moodboard.moodboard_id,
            prompt_version=PROMPT_VERSION,
            creative_score=score,
            moodboard=moodboard,
            collection_name=collection_name,
            product_name=product_name,
        )
        self._persist_brief(brief)
        return brief

    def build_prompt(self, brief: CreativeBrief, product_name: str = "") -> CreativePrompt:
        """Compose a prompt from reusable creative blocks."""
        prompt = self._prompt_builder.compose(brief, product_name=product_name)
        if self._memory is not None:
            self._memory.save_record("creative_prompts", brief.brief_id, prompt.to_dict())
        return prompt

    def evaluate_creative_direction(
        self,
        *,
        brief: CreativeBrief,
        prompt: CreativePrompt,
        collection_briefs: tuple[CreativeBrief, ...] = (),
    ) -> CreativeQAResult:
        """Run Creative QA for a brief and prompt."""
        result = self._qa_engine.evaluate(
            brief=brief,
            prompt=prompt,
            collection_briefs=collection_briefs,
        )
        if self._memory is not None:
            self._memory.save_record("creative_qa", brief.brief_id, result.to_dict())
        return result

    def direct_collection(
        self,
        *,
        theme: str,
        target_audience: str,
        products: tuple[dict[str, str], ...],
        season: str = "Evergreen",
        collection_name: str = "",
        commercial_positioning: str = "",
    ) -> tuple[CreativeBrief, ...]:
        """Create collection-consistent briefs for all products."""
        collection = collection_name or theme
        anchor = self.create_brief(
            theme=theme,
            target_audience=target_audience,
            product_name=products[0].get("product_name", "") if products else "",
            product_type=products[0].get("product_type", "") if products else "",
            season=season,
            collection_name=collection,
            commercial_positioning=commercial_positioning,
        )
        briefs = [anchor]
        for product in products[1:]:
            briefs.append(
                _variant_brief(
                    anchor=anchor,
                    product_name=product.get("product_name", ""),
                    product_type=product.get("product_type", ""),
                    score=_creative_score(
                        self._style_library.get(anchor.style_id),
                        theme,
                        target_audience,
                        collection,
                    ),
                )
            )
            self._persist_brief(briefs[-1])
        return tuple(briefs)

    @property
    def styles(self) -> tuple[CreativeStyle, ...]:
        """Return available creative styles."""
        return self._style_library.styles

    def _persist_brief(self, brief: CreativeBrief) -> None:
        if self._memory is None:
            return
        self._memory.save_record("creative_briefs", brief.brief_id, brief.to_dict())
        self._memory.save_record("creative_moodboards", brief.moodboard_id, brief.moodboard.to_dict())


def _creative_score(
    style: CreativeStyle,
    theme: str,
    audience: str,
    collection_name: str,
) -> CreativeScore:
    haystack = f"{theme} {audience} {collection_name}".casefold()
    fit = 78 + sum(4 for category in style.target_categories if category.casefold() in haystack)
    return CreativeScore(
        originality=min(96, 82 + len(style.visual_mood)),
        commercial_appeal=min(98, fit),
        brand_consistency=92,
        visual_harmony=94,
        collection_fit=94 if collection_name else 86,
    )


def _variant_brief(
    *,
    anchor: CreativeBrief,
    product_name: str,
    product_type: str,
    score: CreativeScore,
) -> CreativeBrief:
    return CreativeBrief(
        theme=anchor.theme,
        target_audience=anchor.target_audience,
        emotion=anchor.emotion,
        color_palette=anchor.color_palette,
        illustration_style=anchor.illustration_style,
        composition_style=_composition_for(product_type, anchor.theme),
        lighting_style=anchor.lighting_style,
        texture_style=anchor.texture_style,
        typography_style=_typography_for(product_type, anchor.theme),
        commercial_positioning=anchor.commercial_positioning,
        style_id=anchor.style_id,
        palette_id=anchor.palette_id,
        moodboard_id=anchor.moodboard_id,
        prompt_version=anchor.prompt_version,
        creative_score=score,
        moodboard=anchor.moodboard,
        collection_name=anchor.collection_name,
        product_name=product_name,
    )


def _emotion_for(theme: str, season: str, audience: str) -> str:
    lowered = f"{theme} {season} {audience}".casefold()
    if "dark academia" in lowered:
        return "moody scholarly"
    if "teacher" in lowered:
        return "bright friendly"
    if "wedding" in lowered:
        return "romantic refined"
    if "nursery" in lowered or "baby" in lowered:
        return "gentle sweet"
    if "christmas" in lowered:
        return "nostalgic festive"
    return "cohesive commercial"


def _composition_for(product_type: str, theme: str) -> str:
    lowered = f"{product_type} {theme}".casefold()
    if "digital paper" in lowered:
        return "seamless repeating pattern with coordinated motif spacing"
    if "clipart" in lowered:
        return "individual isolated elements with consistent scale and spacing"
    if "sticker" in lowered:
        return "cuttable sticker sheet with white outlines and clean separation"
    if "invitation" in lowered or "party" in lowered:
        return "printable stationery layout with safe margins and clear focal hierarchy"
    if "wall art" in lowered:
        return "finished wall-art composition with balanced focal point"
    return "cohesive commercial product composition"


def _lighting_for(style: CreativeStyle, emotion: str) -> str:
    if "moody" in emotion:
        return "warm low directional lighting"
    if "bright" in emotion:
        return "bright soft studio lighting"
    if "watercolor" in style.rendering_approach.casefold():
        return "soft natural watercolor lighting"
    return "consistent commercial studio lighting"


def _typography_for(product_type: str, theme: str) -> str:
    lowered = f"{product_type} {theme}".casefold()
    if "wedding" in lowered:
        return "elegant serif with optional script accents"
    if "teacher" in lowered:
        return "readable friendly classroom typography"
    if "birthday" in lowered or "party" in lowered:
        return "playful rounded party typography"
    return "none unless product preview requires buyer-facing text"
