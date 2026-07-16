"""Tests for Muse AI Art Director."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_PATH))

from project_aurora.image_qa.qa_rules import (  # noqa: E402
    AssetContext,
    CompositionMatchRule,
    PaletteMatchRule,
    RenderingConsistencyRule,
    StyleMatchRule,
)
from project_aurora.muse.muse_engine import MuseEngine  # noqa: E402
from project_aurora.muse.style_library import MuseStyleLibrary  # noqa: E402
from project_aurora.muse.style_memory import StyleMemory  # noqa: E402
from project_aurora.prompt_factory.prompt_composer import PromptComposer  # noqa: E402
from project_aurora.storage.csv_storage import CSVStorage  # noqa: E402
from project_aurora.storage.memory_manager import MemoryManager  # noqa: E402


PRODUCTS = (
    ("Wedding Invitation", "brides", "Wedding Season", "Medium", "party printable"),
    ("Teacher Stickers", "teachers", "Back to School", "Low", "sticker sheet"),
    ("Kitchen Art", "home decor buyers", "Evergreen", "Medium", "wall art"),
    ("Dark Academia", "students and readers", "Autumn", "High", "wall art"),
    ("Coastal Digital Paper", "scrapbookers", "Summer", "Medium", "digital paper"),
    ("Autumn Mushroom", "crafters", "Autumn", "Low", "clipart"),
)


class MuseTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.memory = MemoryManager(CSVStorage(base_path=Path(self.temp_dir.name)))
        self.style_memory = StyleMemory(memory=self.memory)
        self.engine = MuseEngine(memory=self.memory, style_memory=self.style_memory)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_style_library_loads_required_styles(self) -> None:
        library = MuseStyleLibrary.from_file(PROJECT_ROOT / "config" / "style_library.yaml")
        names = {profile.name for profile in library.profiles}

        self.assertGreaterEqual(len(names), 30)
        self.assertIn("Pressed Flowers", names)
        self.assertIn("Flat Vector", names)
        self.assertIn("Dark Academia", names)

    def test_different_products_choose_different_styles(self) -> None:
        chosen: list[str] = []
        for product, audience, season, competition, product_type in PRODUCTS:
            direction = self.engine.select_style(
                product=product,
                audience=audience,
                season=season,
                competition=competition,
                current_portfolio=tuple(chosen),
                product_type=product_type,
            )
            chosen.append(direction.recommended_style)

        self.assertGreaterEqual(len(set(chosen)), 5)
        self.assertIn("Flat Vector", chosen)
        self.assertIn("Pressed Flowers", chosen)

    def test_same_style_not_overused_in_batch(self) -> None:
        chosen: list[str] = []
        for product, audience, season, competition, product_type in PRODUCTS:
            direction = self.engine.select_style(
                product=product,
                audience=audience,
                season=season,
                competition=competition,
                current_portfolio=tuple(chosen),
                product_type=product_type,
            )
            chosen.append(direction.recommended_style)

        for style in set(chosen):
            self.assertLessEqual(chosen.count(style), 2)

    def test_prompt_contains_muse_style_information(self) -> None:
        direction = self.engine.select_style(
            product="Autumn Mushroom",
            audience="crafters",
            season="Autumn",
            competition="Low",
            product_type="clipart",
        )
        recipe = PromptComposer(memory=self.memory).compose_art_directed(
            product="Autumn Mushroom",
            style=direction.recommended_style,
            palette=direction.palette,
            rendering_method=direction.rendering_method,
            composition=direction.composition,
            mood=direction.mood,
        )

        self.assertIn("Product: Autumn Mushroom", recipe.final_prompt)
        self.assertIn(f"Style: {direction.recommended_style}", recipe.final_prompt)
        self.assertIn(f"Palette: {direction.palette}", recipe.final_prompt)
        self.assertIn(f"Rendering: {direction.rendering_method}", recipe.final_prompt)
        self.assertIn(f"Composition: {direction.composition}", recipe.final_prompt)
        self.assertIn(f"Mood: {direction.mood}", recipe.final_prompt)

    def test_style_memory_updates(self) -> None:
        direction = self.engine.select_style(
            product="Teacher Stickers",
            audience="teachers",
            season="Back to School",
            product_type="sticker sheet",
        )

        self.assertEqual(self.style_memory.records[-1].product_name, "Teacher Stickers")
        self.assertEqual(self.style_memory.records[-1].style_used, direction.recommended_style)
        self.assertTrue(self.memory.list_records("style_memory"))

    def test_image_qa_style_metadata_rules(self) -> None:
        context = AssetContext(
            asset_path=Path("mock.png"),
            all_asset_paths=(Path("mock.png"),),
            metadata={
                "expected_style": "Flat Vector",
                "style": "Flat Vector",
                "expected_palette": "bright primary",
                "palette": "bright primary, teal",
                "expected_composition": "Sticker sheet",
                "composition": "Sticker sheet with clear individual icons",
                "expected_rendering": "Flat vector",
                "rendering": "Flat vector illustration",
            },
        )

        self.assertTrue(StyleMatchRule().evaluate(context).passed)
        self.assertTrue(PaletteMatchRule().evaluate(context).passed)
        self.assertTrue(CompositionMatchRule().evaluate(context).passed)
        self.assertTrue(RenderingConsistencyRule().evaluate(context).passed)

    def test_image_qa_rejects_style_mismatch(self) -> None:
        context = AssetContext(
            asset_path=Path("mock.png"),
            all_asset_paths=(Path("mock.png"),),
            metadata={"expected_style": "Flat Vector", "style": "Oil Painting"},
        )

        self.assertFalse(StyleMatchRule().evaluate(context).passed)


if __name__ == "__main__":
    unittest.main()
