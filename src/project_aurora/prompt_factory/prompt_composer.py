"""Component-based Prompt Factory 2.0 composer."""

from __future__ import annotations

from project_aurora.prompt_factory.composition_library import get_composition
from project_aurora.prompt_factory.palette_library import get_palette
from project_aurora.prompt_factory.prompt_components import (
    PromptComponent,
    PromptComponents,
)
from project_aurora.prompt_factory.prompt_recipe import PromptRecipe
from project_aurora.prompt_factory.style_library import get_style
from project_aurora.storage.memory_manager import MemoryManager


class PromptComposer:
    """Build professional prompts from reusable creative components."""

    def __init__(self, memory: MemoryManager | None = None) -> None:
        self._memory = memory

    def compose(
        self,
        subject: str,
        character: str,
        style_name: str,
        palette_name: str,
        composition_name: str,
        recipe_id: str = "latest",
    ) -> PromptRecipe:
        """Compose and optionally save a prompt recipe."""
        components = self._build_components(
            subject=subject,
            character=character,
            style_name=style_name,
            palette_name=palette_name,
            composition_name=composition_name,
        )
        final_prompt = self._compose_final_prompt(components)
        recipe = PromptRecipe(
            subject=components.subject.render(),
            character=components.character.render(),
            style=components.style.name,
            color_palette=components.color_palette.name,
            lighting=components.lighting.render(),
            composition=components.composition.name,
            background=components.background.render(),
            rendering=components.rendering.render(),
            commercial_requirements=(
                components.commercial_requirements.render()
            ),
            consistency_rules=components.consistency_rules.render(),
            negative_prompt=components.negative_prompt.render(),
            provider_formatting=components.provider_formatting.render(),
            final_prompt=final_prompt,
        )
        if self._memory is not None:
            self._memory.save_prompt_recipe(recipe, recipe_id=recipe_id)
        return recipe

    def compose_art_directed(
        self,
        product: str,
        style: str,
        palette: str,
        rendering_method: str,
        composition: str,
        mood: str,
        background_treatment: str = "",
        lighting: str = "",
        texture: str = "",
        typography_direction: str = "",
        negative_style_constraints: tuple[str, ...] = (),
        recipe_id: str = "latest",
    ) -> PromptRecipe:
        """Compose a prompt from Muse art-direction fields."""
        final_prompt = (
            f"Product: {product},\n"
            f"Style: {style},\n"
            f"Rendering Family: {rendering_method},\n"
            f"Palette: {palette},\n"
            f"Composition: {composition},\n"
            f"Background: {background_treatment or 'style-appropriate production background'},\n"
            f"Lighting: {lighting or 'style-appropriate professional lighting'},\n"
            f"Texture: {texture or 'style-consistent texture'},\n"
            f"Mood: {mood},\n"
            f"Typography Direction: {typography_direction or 'none unless product type requires it'},\n"
            f"Negative Style Constraints: {', '.join(negative_style_constraints) if negative_style_constraints else 'avoid mismatched rendering styles'},\n"
            "commercial digital printable artwork, cohesive product collection, "
            "high detail, clean production-ready assets."
        )
        recipe = PromptRecipe(
            subject=product,
            character=f"{product} cohesive product assets",
            style=style,
            color_palette=palette,
            lighting=lighting or "style-appropriate professional lighting",
            composition=composition,
            background=background_treatment or "transparent or clean printable background as appropriate",
            rendering=rendering_method,
            commercial_requirements="commercial use digital download ready",
            consistency_rules="consistent palette, rendering method, composition, and mood",
            negative_prompt=(
                "No text, No watermark, No logo, No cropped objects, "
                "No inconsistent style, No mismatched palette, "
                + ", ".join(negative_style_constraints)
            ),
            provider_formatting="single image prompt, comma-separated descriptive phrases",
            final_prompt=final_prompt,
        )
        if self._memory is not None:
            self._memory.save_prompt_recipe(recipe, recipe_id=recipe_id)
        return recipe

    @staticmethod
    def _build_components(
        subject: str,
        character: str,
        style_name: str,
        palette_name: str,
        composition_name: str,
    ) -> PromptComponents:
        return PromptComponents(
            subject=PromptComponent(
                name="Subject",
                phrases=(subject,),
            ),
            character=PromptComponent(
                name="Character",
                phrases=(character,),
            ),
            style=get_style(style_name),
            color_palette=get_palette(palette_name),
            lighting=PromptComponent(
                name="Lighting",
                phrases=(
                    "warm soft natural lighting",
                    "gentle highlights",
                    "no harsh shadows",
                ),
            ),
            composition=get_composition(composition_name),
            background=PromptComponent(
                name="Background",
                phrases=(
                    "clean white background",
                    "isolated printable elements",
                ),
            ),
            rendering=PromptComponent(
                name="Rendering",
                phrases=(
                    "highly detailed",
                    "crisp edges",
                    "professional printable quality",
                ),
            ),
            commercial_requirements=PromptComponent(
                name="Commercial Requirements",
                phrases=(
                    "commercial clipart",
                    "digital download ready",
                    "no copyrighted characters",
                ),
            ),
            consistency_rules=PromptComponent(
                name="Consistency Rules",
                phrases=(
                    "consistent character proportions",
                    "consistent palette across all assets",
                    "cohesive storybook collection style",
                ),
            ),
            negative_prompt=PromptComponent(
                name="Negative Prompt",
                phrases=(
                    "No text",
                    "No watermark",
                    "No logo",
                    "No border",
                    "No cropped objects",
                    "No duplicate subjects",
                    "No blurry details",
                ),
            ),
            provider_formatting=PromptComponent(
                name="Provider Formatting",
                phrases=(
                    "single image prompt",
                    "comma-separated descriptive phrases",
                    "optimized for image generation providers",
                ),
            ),
        )

    @staticmethod
    def _compose_final_prompt(components: PromptComponents) -> str:
        parts = (
            components.subject.render(),
            components.character.render(),
            components.style.render(),
            components.color_palette.render(),
            components.lighting.render(),
            components.composition.render(),
            components.background.render(),
            components.rendering.render(),
            components.commercial_requirements.render(),
            components.consistency_rules.render(),
            components.provider_formatting.render(),
        )
        return ",\n".join(parts) + "."
