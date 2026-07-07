"""Tests for Prompt Factory 2.0 composer."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_PATH))

from project_aurora.prompt_factory.composition_library import (  # noqa: E402
    get_composition,
)
from project_aurora.prompt_factory.palette_library import get_palette  # noqa: E402
from project_aurora.prompt_factory.prompt_composer import (  # noqa: E402
    PromptComposer,
)
from project_aurora.prompt_factory.prompt_recipe import PromptRecipe  # noqa: E402
from project_aurora.prompt_factory.style_library import get_style  # noqa: E402
from project_aurora.storage.csv_storage import CSVStorage  # noqa: E402
from project_aurora.storage.memory_manager import MemoryManager  # noqa: E402


class PromptComposerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.memory = MemoryManager(
            storage=CSVStorage(base_path=Path(self.temp_dir.name))
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_prompt_recipe_dataclass(self) -> None:
        recipe = PromptRecipe(
            subject="Strawberry party printable",
            character="Main Strawberry Girl",
            style="Storybook Watercolor",
            color_palette="Strawberry Summer",
            lighting="warm soft natural lighting",
            composition="Centered",
            background="white background",
            rendering="highly detailed",
            commercial_requirements="commercial clipart",
            consistency_rules="consistent palette",
            negative_prompt="No text",
            provider_formatting="single image prompt",
            final_prompt="Strawberry party printable, storybook watercolor.",
        )

        self.assertEqual(recipe.style, "Storybook Watercolor")
        self.assertIn("Strawberry", recipe.final_prompt)

    def test_libraries_return_named_components(self) -> None:
        self.assertEqual(get_style("Storybook Watercolor").name, "Storybook Watercolor")
        self.assertEqual(get_palette("Strawberry Summer").name, "Strawberry Summer")
        self.assertEqual(get_composition("Centered").name, "Centered")

    def test_prompt_composer_generates_prompt(self) -> None:
        recipe = PromptComposer().compose(
            subject="Summer strawberry birthday party printable collection",
            character="Main Strawberry Girl",
            style_name="Storybook Watercolor",
            palette_name="Strawberry Summer",
            composition_name="Centered",
        )

        self.assertEqual(recipe.style, "Storybook Watercolor")
        self.assertEqual(recipe.color_palette, "Strawberry Summer")
        self.assertEqual(recipe.composition, "Centered")
        self.assertIn("storybook watercolor illustration", recipe.final_prompt)
        self.assertIn("berry red", recipe.final_prompt)
        self.assertIn("centered composition", recipe.final_prompt)

    def test_negative_prompt_is_generated(self) -> None:
        recipe = PromptComposer().compose(
            subject="Summer strawberry birthday party printable collection",
            character="Main Strawberry Girl",
            style_name="Storybook Watercolor",
            palette_name="Strawberry Summer",
            composition_name="Centered",
        )

        self.assertIn("No text", recipe.negative_prompt)
        self.assertIn("No watermark", recipe.negative_prompt)
        self.assertIn("No blurry details", recipe.negative_prompt)

    def test_prompt_recipe_saved_to_memory(self) -> None:
        recipe = PromptComposer(memory=self.memory).compose(
            subject="Summer strawberry birthday party printable collection",
            character="Main Strawberry Girl",
            style_name="Storybook Watercolor",
            palette_name="Strawberry Summer",
            composition_name="Centered",
        )

        saved = self.memory.load_prompt_recipe()

        self.assertEqual(saved["style"], recipe.style)
        self.assertEqual(saved["color_palette"], "Strawberry Summer")
        self.assertIn("final_prompt", saved)

    def test_unknown_library_value_raises(self) -> None:
        with self.assertRaises(ValueError):
            get_style("Unknown Style")


if __name__ == "__main__":
    unittest.main()
