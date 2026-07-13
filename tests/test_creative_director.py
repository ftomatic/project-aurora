"""Tests for Aurora Creative Director."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_PATH))

from project_aurora.config.profile_loader import (  # noqa: E402
    ProjectProfileLoader,
)
from project_aurora.creative.collection_engine import CollectionEngine  # noqa: E402
from project_aurora.creative.collection_plan import CollectionPlan  # noqa: E402
from project_aurora.creative.creative_director import (  # noqa: E402
    CreativeDirector,
)


PROFILE_PATH = (
    PROJECT_ROOT / "config" / "projects" / "rainbow_milk_studio.yaml"
)


def make_research() -> dict[str, object]:
    return {
        "production_selection": {
            "best_product": {
                "name": "Strawberry Birthday Party Printable",
                "theme": "Strawberry Birthday",
                "season": "Summer",
            }
        }
    }


def make_strategy() -> dict[str, object]:
    return {
        "selected_product": "Strawberry Birthday Party Printable",
        "product_type": "Party Printable Bundle",
        "collection_name": "Summer Strawberry Birthday Collection",
        "asset_count": 36,
        "target_buyer": "Parents planning girls' summer birthday parties",
        "positioning": "Cute cottagecore strawberry printable party bundle",
        "production_priority": "High",
    }


class CreativeDirectorTest(unittest.TestCase):
    def setUp(self) -> None:
        self.profile = ProjectProfileLoader().load(PROFILE_PATH)

    def test_collection_plan_dataclass(self) -> None:
        plan = CollectionPlan(
            collection_name="Summer Strawberry Birthday",
            theme="Storybook Watercolor",
            season="Summer",
            target_customer="Parents",
            art_style="Storybook Watercolor Cottagecore",
            primary_palette=("strawberry red",),
            secondary_palette=("cream white",),
            recommended_products=("Invitation",),
            master_assets=("Main Strawberry Girl",),
            shared_elements=("strawberries",),
            cross_sell_products=("Matching Clipart",),
            upsell_products=("Deluxe Bundle",),
            estimated_revenue=120.0,
            estimated_generation_cost=0.62,
            priority="High",
        )

        self.assertEqual(plan.status, "READY FOR IMAGE GENERATION")
        self.assertEqual(plan.collection_name, "Summer Strawberry Birthday")

    def test_collection_engine_builds_complete_plan(self) -> None:
        plan = CollectionEngine().build_plan(
            research=make_research(),
            strategy=make_strategy(),
            project_profile=self.profile,
        )

        self.assertEqual(plan.collection_name, "Summer Strawberry Birthday")
        self.assertEqual(plan.theme, "Storybook Watercolor")
        self.assertEqual(len(plan.recommended_products), 10)
        self.assertEqual(len(plan.master_assets), 4)
        self.assertIn("Matching Clipart", plan.cross_sell_products)
        self.assertIn("Pinterest Launch Graphics", plan.upsell_products)

    def test_creative_director_returns_collection_plan(self) -> None:
        plan = CreativeDirector().plan_collection(
            research=make_research(),
            strategy=make_strategy(),
            project_profile=self.profile,
        )

        self.assertIsInstance(plan, CollectionPlan)
        self.assertEqual(plan.priority, "High")
        self.assertIn("strawberry red", plan.primary_palette)

    def test_revenue_estimation(self) -> None:
        revenue = CollectionEngine.estimate_revenue(
            recommended_products=tuple(f"Product {index}" for index in range(10)),
            upsell_products=tuple(f"Upsell {index}" for index in range(5)),
            default_price=1.99,
        )

        self.assertEqual(revenue, 59.9)

    def test_generation_cost_estimation(self) -> None:
        cost = CollectionEngine.estimate_generation_cost(
            (
                "Main Strawberry Girl",
                "Berry Pattern",
                "Watercolor Background",
                "Floral Accent Pack",
            )
        )

        self.assertEqual(cost, 0.62)


if __name__ == "__main__":
    unittest.main()
