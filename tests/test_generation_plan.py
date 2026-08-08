"""Tests for Product Factory generation-mode planning."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_PATH))

from project_aurora.production.generation_plan import (  # noqa: E402
    GENERATION_MODE_BOTANICAL,
    GENERATION_MODE_CHARACTERS,
    GENERATION_MODE_CLIPART,
    GENERATION_MODE_DIGITAL_PAPER,
    GENERATION_MODE_ORIGINAL,
    GENERATION_MODE_STORYBOOK,
    GENERATION_MODE_WEDDING,
    GenerationPlanResolver,
)


class GenerationPlanResolverTest(unittest.TestCase):
    def setUp(self) -> None:
        self.resolver = GenerationPlanResolver()

    def test_auto_nursery_resolves_storybook_before_files_exist(self) -> None:
        plan = self.resolver.resolve(product_name="Mouse Nursery Watercolor Clipart")

        self.assertEqual(plan.resolved_mode, GENERATION_MODE_STORYBOOK)
        self.assertTrue(plan.scene_required)

    def test_auto_woodland_resolves_storybook_before_files_exist(self) -> None:
        plan = self.resolver.resolve(product_name="Fox Woodland Homes Watercolor Clipart")

        self.assertEqual(plan.resolved_mode, GENERATION_MODE_STORYBOOK)

    def test_auto_isolated_floral_elements_resolves_clipart(self) -> None:
        plan = self.resolver.resolve(
            product_name="Floral Elements Watercolor Clipart",
            product_category="isolated floral elements",
        )

        self.assertEqual(plan.resolved_mode, GENERATION_MODE_CLIPART)
        self.assertFalse(plan.scene_required)

    def test_explicit_clipart_override_wins(self) -> None:
        plan = self.resolver.resolve(
            product_name="Woodland Nursery Watercolor Clipart",
            listing_family=GENERATION_MODE_CLIPART,
        )

        self.assertEqual(plan.resolved_mode, GENERATION_MODE_CLIPART)

    def test_explicit_storybook_override_wins(self) -> None:
        plan = self.resolver.resolve(
            product_name="Commercial Floral Elements",
            listing_family=GENERATION_MODE_STORYBOOK,
        )

        self.assertEqual(plan.resolved_mode, GENERATION_MODE_STORYBOOK)
        self.assertTrue(plan.scene_required)

    def test_expanded_generation_modes_are_supported_without_scene(self) -> None:
        for mode in (
            GENERATION_MODE_CHARACTERS,
            GENERATION_MODE_BOTANICAL,
            GENERATION_MODE_DIGITAL_PAPER,
            GENERATION_MODE_WEDDING,
        ):
            with self.subTest(mode=mode):
                plan = self.resolver.resolve(
                    product_name="RainbowMilkStudio Product",
                    listing_family=mode,
                )

                self.assertEqual(plan.resolved_mode, mode)
                self.assertFalse(plan.scene_required)

    def test_explicit_original_mode_uses_storybook_scene_pipeline(self) -> None:
        plan = self.resolver.resolve(
            product_name="Bunny Garden Tea Original Watercolor Collection",
            listing_family=GENERATION_MODE_ORIGINAL,
        )

        self.assertEqual(plan.resolved_mode, GENERATION_MODE_ORIGINAL)
        self.assertTrue(plan.scene_required)


if __name__ == "__main__":
    unittest.main()
