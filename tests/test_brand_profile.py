"""Tests for RainbowMilkStudio brand profile learning and scoring."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_PATH))

from project_aurora.brand_profile import (  # noqa: E402
    build_brand_profile_from_listings,
    load_brand_profile,
    save_brand_profile,
    score_brand_fit,
)


class BrandProfileTest(unittest.TestCase):
    def test_scores_existing_brand_products_highly(self) -> None:
        score = score_brand_fit(
            "Fox Garden Watercolor Clipart",
            "watercolor_woodland_collection",
            "Storybook Watercolor",
        )

        self.assertTrue(score.accepted)
        self.assertGreaterEqual(score.score, 45)
        self.assertIn("fox", score.matched_terms)

    def test_rejects_unrelated_teacher_planner_products(self) -> None:
        score = score_brand_fit(
            "Teacher Planner Alphabet Worksheets",
            "planner",
            "Flat Vector",
        )

        self.assertFalse(score.accepted)
        self.assertEqual(score.score, 0)
        self.assertIn("teacher", score.blocked_terms)

    def test_builds_profile_from_listing_records(self) -> None:
        profile = build_brand_profile_from_listings(
            (
                {
                    "title": "Rabbit Tea Party Watercolor Clipart",
                    "description": "Whimsical woodland rabbit tea party clipart.",
                    "tags": ["rabbit clipart", "watercolor", "woodland"],
                },
                {
                    "title": "Fox Garden Storybook Clipart",
                    "description": "Vintage storybook fox gardening illustrations.",
                    "tags": ["fox clipart", "storybook", "cottagecore"],
                },
            )
        )

        self.assertEqual(profile["source"], "ETSY_SHOP_ANALYSIS")
        self.assertEqual(profile["listing_count"], 2)
        self.assertIn("rabbit", profile["popular_animals"])
        self.assertIn("fox", profile["popular_animals"])

    def test_profile_can_be_saved_and_loaded(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "brand_profile.json"
            save_brand_profile({"brand_name": "RainbowMilkStudio"}, path)

            loaded = load_brand_profile(path)

        self.assertEqual(loaded["brand_name"], "RainbowMilkStudio")
        self.assertEqual(loaded["primary_brand"], "Storybook watercolor woodland illustrations")


if __name__ == "__main__":
    unittest.main()
