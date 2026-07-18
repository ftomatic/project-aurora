"""Tests for Sprint 36 Creative Director AI."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_PATH))

from project_aurora.creative import (  # noqa: E402
    CreativeDirector,
    CreativePromptBuilder,
    CreativeQAEngine,
    CreativeStyleLibrary,
)
from project_aurora.creative.creative_brief import CreativeBrief, CreativeScore  # noqa: E402
from project_aurora.storage.csv_storage import CSVStorage  # noqa: E402
from project_aurora.storage.memory_manager import MemoryManager  # noqa: E402


class CreativeDirectorAITest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.memory = MemoryManager(CSVStorage(base_path=Path(self.temp_dir.name)))
        self.director = CreativeDirector(memory=self.memory)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_creative_brief_generated_and_persisted(self) -> None:
        brief = self.director.create_brief(
            theme="Woodland Nursery",
            target_audience="parents",
            product_name="Woodland Nursery Clipart Bundle",
            product_type="clipart",
            season="Spring",
            collection_name="Woodland Nursery",
            commercial_positioning="Soft coordinated nursery graphics for Etsy buyers.",
        )

        self.assertIsInstance(brief, CreativeBrief)
        self.assertEqual(brief.theme, "Woodland Nursery")
        self.assertEqual(brief.target_audience, "parents")
        self.assertTrue(brief.color_palette.primary)
        self.assertTrue(brief.illustration_style)
        self.assertTrue(brief.moodboard.visual_motifs)
        self.assertTrue(brief.prompt_version)
        self.assertGreaterEqual(brief.creative_score.overall_creative_score, 80)
        self.assertEqual(self.memory.load_record("creative_briefs", brief.brief_id)["brief_id"], brief.brief_id)
        self.assertEqual(
            self.memory.load_record("creative_moodboards", brief.moodboard_id)["moodboard_id"],
            brief.moodboard_id,
        )

    def test_styles_loaded_correctly(self) -> None:
        library = CreativeStyleLibrary()
        names = {style.name for style in library.styles}

        self.assertIn("Watercolor", names)
        self.assertIn("Vintage Botanical", names)
        self.assertIn("Scandinavian", names)
        self.assertIn("Cottagecore", names)
        self.assertIn("Boho", names)
        self.assertIn("Mid-Century Modern", names)
        self.assertIn("Minimalist", names)
        self.assertIn("French Country", names)
        self.assertIn("Whimsical Storybook", names)
        self.assertIn("Dark Academia", names)
        self.assertIn("Coastal", names)
        self.assertIn("Farmhouse", names)

    def test_palettes_generated_with_seasonal_shift(self) -> None:
        summer = self.director.create_brief(
            theme="Strawberry Birthday",
            target_audience="parents",
            product_type="party printable",
            season="Summer",
        )
        winter = self.director.create_brief(
            theme="Vintage Christmas",
            target_audience="holiday crafters",
            product_type="clipart",
            season="Christmas",
        )

        self.assertEqual(summer.color_palette.primary, "berry red")
        self.assertEqual(winter.color_palette.primary, "pine green")
        self.assertNotEqual(summer.palette_id, winter.palette_id)

    def test_prompt_builder_composes_from_blocks(self) -> None:
        brief = self.director.create_brief(
            theme="Wildflower Wedding",
            target_audience="brides",
            product_name="Wildflower Wedding Invitation",
            product_type="party printable",
            season="Wedding Season",
        )
        prompt = CreativePromptBuilder().compose(brief)

        self.assertIn("Subject:", prompt.subject)
        self.assertIn("Style:", prompt.style)
        self.assertIn("Composition:", prompt.composition)
        self.assertIn("Color:", prompt.color)
        self.assertIn("Texture:", prompt.texture)
        self.assertIn("Quality:", prompt.quality)
        self.assertIn("Commercial requirements:", prompt.commercial_requirements)
        self.assertIn("No watermark", prompt.negative_prompt)
        self.assertIn(brief.illustration_style, prompt.final_prompt)

    def test_creative_qa_rejects_inconsistent_outputs(self) -> None:
        anchor = self.director.create_brief(
            theme="Woodland Nursery",
            target_audience="parents",
            product_name="Woodland Nursery Clipart",
            product_type="clipart",
            season="Spring",
            collection_name="Woodland Nursery",
        )
        inconsistent = self.director.create_brief(
            theme="Woodland Nursery",
            target_audience="parents",
            product_name="Woodland Nursery Dark Poster",
            product_type="wall art",
            season="Spring",
            collection_name="Woodland Nursery",
        )
        inconsistent = CreativeBrief(
            **{
                **inconsistent.to_dict(),
                "color_palette": inconsistent.color_palette,
                "creative_score": CreativeScore(
                    originality=90,
                    commercial_appeal=60,
                    brand_consistency=70,
                    visual_harmony=70,
                    collection_fit=60,
                ),
                "moodboard": inconsistent.moodboard,
                "illustration_style": "Dark Academia",
                "lighting_style": "warm low directional lighting",
                "created_at": inconsistent.created_at,
            }
        )
        prompt = CreativePromptBuilder().compose(inconsistent)
        result = CreativeQAEngine().evaluate(
            brief=inconsistent,
            prompt=prompt,
            collection_briefs=(anchor,),
        )

        self.assertEqual(result.status, "FAIL")
        self.assertIn("commercial appeal", result.checks_failed)
        self.assertIn("collection consistency", result.checks_failed)

    def test_collection_consistency_maintained(self) -> None:
        briefs = self.director.direct_collection(
            theme="Woodland Nursery",
            target_audience="parents",
            season="Spring",
            collection_name="Woodland Nursery",
            products=(
                {"product_name": "Woodland Nursery Clipart Bundle", "product_type": "clipart"},
                {"product_name": "Woodland Nursery Digital Paper Pack", "product_type": "digital paper"},
                {"product_name": "Woodland Nursery Wall Art", "product_type": "wall art"},
            ),
        )

        self.assertEqual(len(briefs), 3)
        self.assertEqual(len({brief.illustration_style for brief in briefs}), 1)
        self.assertEqual(len({brief.palette_id for brief in briefs}), 1)
        self.assertEqual(len({brief.lighting_style for brief in briefs}), 1)
        self.assertEqual({brief.collection_name for brief in briefs}, {"Woodland Nursery"})
        for brief in briefs:
            prompt = self.director.build_prompt(brief)
            qa = self.director.evaluate_creative_direction(
                brief=brief,
                prompt=prompt,
                collection_briefs=briefs,
            )
            self.assertEqual(qa.status, "PASS", qa.checks_failed)

    def test_output_persists_required_ids_and_scores(self) -> None:
        brief = self.director.create_brief(
            theme="Boho Teacher",
            target_audience="teachers",
            product_name="Boho Teacher Classroom Decor",
            product_type="wall art",
            season="Back To School",
            collection_name="Boho Teacher",
        )
        prompt = self.director.build_prompt(brief)
        qa = self.director.evaluate_creative_direction(brief=brief, prompt=prompt)
        saved = self.memory.load_record("creative_briefs", brief.brief_id)

        self.assertTrue(saved["style_id"])
        self.assertTrue(saved["palette_id"])
        self.assertTrue(saved["moodboard_id"])
        self.assertTrue(saved["prompt_version"])
        self.assertIn("overall_creative_score", saved["creative_score"])
        self.assertEqual(qa.status, "PASS")
        self.assertEqual(
            self.memory.load_record("creative_prompts", brief.brief_id)["prompt_version"],
            brief.prompt_version,
        )


if __name__ == "__main__":
    unittest.main()
