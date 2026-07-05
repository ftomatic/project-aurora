"""Tests for the Project Aurora product strategy agent."""

from __future__ import annotations

import logging
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_PATH))

from project_aurora.agents.product_strategy_agent import (  # noqa: E402
    ProductStrategyAgent,
)
from project_aurora.research.market_analyzer import MarketTrend  # noqa: E402
from project_aurora.research.recommendation_engine import (  # noqa: E402
    ProductRecommendation,
    ProductionSelection,
    ResearchReport,
)
from project_aurora.research.shop_analyzer import ShopSummary  # noqa: E402
from project_aurora.strategy.product_strategy_engine import (  # noqa: E402
    ProductStrategyEngine,
)


def make_test_logger() -> logging.Logger:
    logger = logging.getLogger("test_product_strategy")
    logger.addHandler(logging.NullHandler())
    logger.propagate = False
    logger.setLevel(logging.INFO)
    return logger


def make_mock_morning_report() -> ResearchReport:
    best = ProductRecommendation(
        name="Strawberry Birthday Party Printable",
        category="Party Printable",
        theme="Strawberry Birthday",
        season="Summer",
        score=126,
        competition_level="medium",
        revenue_potential="high",
        ease_of_production="medium",
        ip_safety="high",
        reasoning="demand score 8/10; medium competition; high revenue",
    )
    backup = ProductRecommendation(
        name="Soft Gingham Digital Paper Pack",
        category="Digital Paper Pack",
        theme="Soft Gingham",
        season="Evergreen",
        score=104,
        competition_level="low",
        revenue_potential="medium",
        ease_of_production="high",
        ip_safety="high",
        reasoning="demand score 7/10; low competition; medium revenue",
    )
    third = ProductRecommendation(
        name="Valentine Bakery Digital Clipart",
        category="Digital Clipart",
        theme="Valentine Bakery",
        season="Valentine",
        score=118,
        competition_level="medium",
        revenue_potential="high",
        ease_of_production="high",
        ip_safety="high",
        reasoning="demand score 9/10; medium competition; high revenue",
    )

    return ResearchReport(
        shop_summary=ShopSummary(
            product_count=3,
            average_price=5.50,
            average_rating=4.8,
            total_sales=100,
            top_categories=(("Sticker Sheet", 1),),
            top_themes=(("Fruit Cottage", 1),),
            covered_categories=frozenset({"Sticker Sheet"}),
            covered_themes=frozenset({"Fruit Cottage"}),
            covered_seasons=frozenset({"Spring"}),
        ),
        market_trends=(
            MarketTrend(
                product_type="Party Printable",
                theme="Strawberry Birthday",
                season="Summer",
                demand_score=8,
                competition_level="medium",
                trend_notes="Fruit birthday sets fit family party searches",
            ),
        ),
        seasonal_opportunities=(),
        competition_estimate=(("medium", 1),),
        recommendations=(best, backup, third),
        production_selection=ProductionSelection(
            best_product=best,
            backup_product=backup,
            collection_expansion="Summer Strawberry Birthday Collection",
            product_type="Party Printable",
            selection_reason="Best local mocked Morning Research output.",
            production_queue=(
                best.name,
                backup.name,
                "Summer Strawberry Birthday Collection",
            ),
        ),
        future_collections=("Summer Strawberry Birthday Collection",),
    )


class ProductStrategyEngineTest(unittest.TestCase):
    def setUp(self) -> None:
        self.report = make_mock_morning_report()
        self.engine = ProductStrategyEngine()

    def test_build_plan_selects_top_morning_research_product(self) -> None:
        plan = self.engine.build_plan(self.report)

        self.assertEqual(
            plan.selected_product,
            "Strawberry Birthday Party Printable",
        )
        self.assertEqual(plan.product_type, "Party Printable Bundle")
        self.assertEqual(
            plan.collection_name,
            "Summer Strawberry Birthday Collection",
        )

    def test_party_printable_plan_includes_required_bundle_fields(self) -> None:
        plan = self.engine.build_plan(self.report)

        self.assertEqual(plan.asset_count, 36)
        self.assertEqual(
            [(item.quantity, item.name) for item in plan.bundle_structure],
            [
                (8, "invitations"),
                (8, "cupcake toppers"),
                (8, "favor tags"),
                (6, "thank-you cards"),
                (6, "digital papers"),
            ],
        )

    def test_plan_includes_buyer_positioning_potential_and_priority(self) -> None:
        plan = self.engine.build_plan(self.report)

        self.assertIn("Parents planning", plan.target_buyer)
        self.assertIn("strawberry birthday", plan.positioning)
        self.assertIn("High", plan.estimated_commercial_potential)
        self.assertEqual(plan.production_priority, "High")
        self.assertTrue(plan.expansion_ideas)

    def test_ceo_summary_starts_with_required_phrase(self) -> None:
        plan = self.engine.build_plan(self.report)

        self.assertTrue(
            plan.ceo_summary.startswith("Today the studio should produce")
        )
        self.assertIn(plan.selected_product, plan.ceo_summary)


class ProductStrategyAgentTest(unittest.TestCase):
    def test_render_plan_contains_required_sections(self) -> None:
        agent = ProductStrategyAgent(logger=make_test_logger())
        rendered_plan = agent.render_plan(make_mock_morning_report())

        required_sections = (
            "CEO Summary",
            "Selected Product",
            "Product Type",
            "Collection",
            "Number of Assets to Create",
            "Bundle Structure",
            "Target Buyer",
            "Positioning",
            "Expansion Ideas",
            "Estimated Commercial Potential",
            "Production Priority",
        )
        for section in required_sections:
            self.assertIn(section, rendered_plan)

        self.assertIn("Strawberry Birthday Party Printable", rendered_plan)
        self.assertIn("- 8 invitations", rendered_plan)
        self.assertIn("Today the studio should produce", rendered_plan)


if __name__ == "__main__":
    unittest.main()
