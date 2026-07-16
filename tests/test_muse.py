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
    BackgroundTreatmentRule,
    CompositionMatchRule,
    PaletteMatchRule,
    ProductTypeSuitabilityRule,
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

    def test_category_playbook_ranking(self) -> None:
        direction = self.engine.select_style(
            product="Teacher Reward Stickers",
            audience="teachers",
            season="Back to School",
            product_type="teacher printables",
        )

        self.assertEqual(direction.recommended_style, "Flat Vector")
        self.assertEqual(direction.rendering_family, "vector")
        self.assertIn("no watercolor bleed", direction.negative_style_constraints)

    def test_proven_winner_raises_related_coastal_style_score(self) -> None:
        direction = self.engine.select_style(
            product="Coastal Beach Wall Art",
            audience="home decor buyers",
            season="Summer",
            product_type="coastal wall art",
        )

        self.assertEqual(direction.recommended_style, "Coastal Watercolor")
        self.assertIn("Coastal Beach Watercolor", direction.proven_winner_evidence_used)

    def test_proven_winner_does_not_force_coastal_on_unrelated_categories(self) -> None:
        teacher = self.engine.select_style(
            product="Teacher Stickers",
            audience="teachers",
            season="Back to School",
            product_type="teacher printables",
        )
        wedding = self.engine.select_style(
            product="Wedding Invitation",
            audience="brides",
            season="Wedding Season",
            product_type="wedding",
        )

        self.assertNotEqual(teacher.recommended_style, "Coastal Watercolor")
        self.assertNotEqual(wedding.recommended_style, "Coastal Watercolor")

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
        directions = self.engine.select_batch(
            tuple(
                {
                    "product": product,
                    "audience": audience,
                    "season": season,
                    "competition": competition,
                    "product_type": product_type,
                }
                for product, audience, season, competition, product_type in PRODUCTS
            )
        )

        for dimension in (
            "rendering_family",
            "background_treatment",
            "composition",
            "dominant_palette_family",
            "texture_family",
        ):
            values = [str(getattr(direction, dimension)) for direction in directions]
            for value in set(values):
                self.assertLessEqual(values.count(value), 2)

    def test_composition_varies_by_product_type(self) -> None:
        clipart = self.engine.select_style("Mushroom Clipart", product_type="clipart")
        paper = self.engine.select_style("Coastal Digital Paper", product_type="digital paper")
        invitation = self.engine.select_style("Wedding Invitation", product_type="invitations")
        sticker = self.engine.select_style("Teacher Stickers", product_type="sticker sheets")

        self.assertIn("isolated", clipart.composition)
        self.assertIn("seamless pattern", paper.composition)
        self.assertIn("invitation", invitation.composition)
        self.assertIn("cuttable", sticker.composition)

    def test_teacher_wall_art_does_not_receive_sticker_sheet_composition(self) -> None:
        direction = self.engine.select_style(
            product="Classroom Alphabet Wall Art",
            audience="teachers",
            season="Back to School",
            product_type="teacher wall art",
        )

        self.assertEqual(direction.category, "teacher wall art")
        self.assertEqual(direction.recommended_style, "Flat Vector")
        self.assertIn("alphabet poster", direction.composition)
        self.assertIn("wall-art", direction.composition)
        self.assertNotIn("sticker", direction.composition.casefold())

    def test_bridal_shower_games_do_not_receive_landscape_style(self) -> None:
        direction = self.engine.select_style(
            product="Boho Bridal Shower Games",
            audience="brides",
            season="Wedding Season",
            product_type="bridal shower printable",
        )

        self.assertEqual(direction.category, "bridal shower printable")
        self.assertIn(
            direction.recommended_style,
            {"Editorial Minimal", "Fine Line Floral", "Pressed Flowers", "Luxury Wedding"},
        )
        self.assertIn("stationery", direction.composition)
        self.assertNotIn("landscape", direction.composition.casefold())

    def test_sticker_sheet_mapping_is_cuttable_with_outlines(self) -> None:
        direction = self.engine.select_style(
            product="Spring Garden Sticker Sheet",
            audience="crafters",
            season="Spring",
            product_type="sticker sheet",
        )

        self.assertEqual(direction.category, "sticker sheets")
        self.assertIn(direction.recommended_style, {"Flat Vector", "Kawaii"})
        self.assertIn("cuttable", direction.composition)
        self.assertIn("white outlines", direction.composition)

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
            background_treatment=direction.background_treatment,
            lighting=direction.lighting,
            texture=direction.texture,
            typography_direction=direction.typography_direction,
            negative_style_constraints=direction.negative_style_constraints,
        )

        self.assertIn("Product: Autumn Mushroom", recipe.final_prompt)
        self.assertIn(f"Style: {direction.recommended_style}", recipe.final_prompt)
        self.assertIn(f"Palette: {direction.palette}", recipe.final_prompt)
        self.assertIn(f"Rendering Family: {direction.rendering_method}", recipe.final_prompt)
        self.assertIn(f"Composition: {direction.composition}", recipe.final_prompt)
        self.assertIn(f"Background: {direction.background_treatment}", recipe.final_prompt)
        self.assertIn(f"Lighting: {direction.lighting}", recipe.final_prompt)
        self.assertIn(f"Texture: {direction.texture}", recipe.final_prompt)
        self.assertIn(f"Mood: {direction.mood}", recipe.final_prompt)
        for constraint in direction.negative_style_constraints:
            self.assertIn(constraint, recipe.final_prompt)

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
                "expected_palette": "bright primary",
                "expected_composition": "Sticker sheet",
                "expected_rendering": "Flat vector",
                "expected_background_treatment": "white cuttable background",
                "expected_product_type": "sticker sheets",
                "visual_semantic_evaluation": {
                    "style": {"status": "PASS", "score": 92},
                    "palette": {"status": "PASS", "score": 90},
                    "composition": {"status": "PASS", "score": 91},
                    "rendering_family": {"status": "PASS", "score": 93},
                    "background": {"status": "PASS", "score": 88},
                    "product_type_suitability": {"status": "PASS", "score": 94},
                },
            },
        )

        self.assertTrue(StyleMatchRule().evaluate(context).passed)
        self.assertTrue(PaletteMatchRule().evaluate(context).passed)
        self.assertTrue(CompositionMatchRule().evaluate(context).passed)
        self.assertTrue(RenderingConsistencyRule().evaluate(context).passed)
        self.assertTrue(BackgroundTreatmentRule().evaluate(context).passed)
        self.assertTrue(ProductTypeSuitabilityRule().evaluate(context).passed)

    def test_image_qa_rejects_style_mismatch(self) -> None:
        context = AssetContext(
            asset_path=Path("mock.png"),
            all_asset_paths=(Path("mock.png"),),
            metadata={
                "expected_style": "Flat Vector",
                "visual_semantic_evaluation": {
                    "style": {"status": "FAIL", "score": 20},
                },
            },
        )

        self.assertFalse(StyleMatchRule().evaluate(context).passed)

    def test_image_qa_rejects_product_type_mismatch(self) -> None:
        context = AssetContext(
            asset_path=Path("mock.png"),
            all_asset_paths=(Path("mock.png"),),
            metadata={
                "expected_product_type": "digital paper",
                "visual_semantic_evaluation": {
                    "product_type_suitability": {"status": "FAIL", "score": 18},
                },
            },
        )

        self.assertFalse(ProductTypeSuitabilityRule().evaluate(context).passed)


if __name__ == "__main__":
    unittest.main()
