"""Tests for listing-family business decision rules."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_PATH))

from project_aurora.image_generation.listing_family_decision import (  # noqa: E402
    LISTING_FAMILY_AUTO,
    LISTING_FAMILY_CLIPART,
    LISTING_FAMILY_STORYBOOK,
    ListingFamilyDecisionEngine,
)


class ListingFamilyDecisionEngineTest(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = ListingFamilyDecisionEngine()

    def decide(
        self,
        *,
        category: str = "",
        theme: str = "",
        customer: str = "",
        composition: str = "",
        scene: bool = True,
        override: str = LISTING_FAMILY_AUTO,
    ) -> str:
        return self.engine.decide(
            listing_family=override,
            product_category=category,
            niche_theme=theme,
            intended_customer=customer,
            artwork_composition=composition,
            scene_available=scene,
        ).selected_family

    def test_nursery_selects_storybook(self) -> None:
        self.assertEqual(self.decide(category="nursery clipart"), LISTING_FAMILY_STORYBOOK)

    def test_woodland_selects_storybook(self) -> None:
        self.assertEqual(self.decide(theme="woodland animal families"), LISTING_FAMILY_STORYBOOK)

    def test_cottagecore_selects_storybook(self) -> None:
        self.assertEqual(self.decide(theme="cottagecore tea party"), LISTING_FAMILY_STORYBOOK)

    def test_digital_paper_selects_clipart(self) -> None:
        self.assertEqual(self.decide(category="digital paper"), LISTING_FAMILY_CLIPART)

    def test_floral_elements_selects_clipart(self) -> None:
        self.assertEqual(self.decide(category="floral elements"), LISTING_FAMILY_CLIPART)

    def test_planner_stickers_selects_clipart(self) -> None:
        self.assertEqual(self.decide(category="planner stickers"), LISTING_FAMILY_CLIPART)

    def test_explicit_storybook_override(self) -> None:
        self.assertEqual(
            self.decide(override=LISTING_FAMILY_STORYBOOK, category="icons", scene=True),
            LISTING_FAMILY_STORYBOOK,
        )

    def test_explicit_clipart_override(self) -> None:
        self.assertEqual(
            self.decide(override=LISTING_FAMILY_CLIPART, category="nursery", scene=True),
            LISTING_FAMILY_CLIPART,
        )

    def test_auto_with_existing_scene(self) -> None:
        self.assertEqual(self.decide(scene=True), LISTING_FAMILY_STORYBOOK)

    def test_auto_without_scene_falls_back_to_clipart(self) -> None:
        self.assertEqual(self.decide(theme="woodland nursery", scene=False), LISTING_FAMILY_CLIPART)


if __name__ == "__main__":
    unittest.main()
