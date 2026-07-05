"""Tests for the Project Aurora morning research agent."""

from __future__ import annotations

import logging
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_PATH))

from project_aurora.agents.morning_research_agent import (  # noqa: E402
    MorningResearchAgent,
    MorningResearchPaths,
)


def make_test_logger() -> logging.Logger:
    logger = logging.getLogger("test_morning_research")
    logger.addHandler(logging.NullHandler())
    logger.propagate = False
    logger.setLevel(logging.INFO)
    return logger


class MorningResearchAgentTest(unittest.TestCase):
    def setUp(self) -> None:
        self.paths = MorningResearchPaths(
            shop_csv=(
                PROJECT_ROOT / "data" / "research" / "sample_shop.csv"
            ),
            market_trends_csv=(
                PROJECT_ROOT
                / "data"
                / "research"
                / "sample_market_trends.csv"
            ),
        )
        self.agent = MorningResearchAgent(logger=make_test_logger())

    def test_build_report_scores_top_ten_recommendations(self) -> None:
        report = self.agent.build_report(self.paths)

        self.assertEqual(report.shop_summary.product_count, 8)
        self.assertEqual(len(report.market_trends), 12)
        self.assertEqual(len(report.recommendations), 10)
        self.assertGreaterEqual(
            report.recommendations[0].score,
            report.recommendations[-1].score,
        )

    def test_recommendations_include_reasoning(self) -> None:
        report = self.agent.build_report(self.paths)

        for recommendation in report.recommendations:
            self.assertTrue(recommendation.reasoning)
            self.assertIn("demand score", recommendation.reasoning)
            self.assertIn("competition", recommendation.reasoning)
            self.assertIn("revenue potential", recommendation.reasoning)
            self.assertIn("production ease", recommendation.reasoning)
            self.assertIn("IP safety", recommendation.reasoning)

    def test_agent_selects_today_production_work(self) -> None:
        report = self.agent.build_report(self.paths)
        selection = report.production_selection

        self.assertEqual(selection.best_product, report.recommendations[0])
        self.assertEqual(selection.backup_product, report.recommendations[1])
        self.assertEqual(selection.product_type, selection.best_product.category)
        self.assertIn(selection.best_product.name, selection.production_queue)
        self.assertIn(selection.backup_product.name, selection.production_queue)
        self.assertIn(
            selection.collection_expansion,
            selection.production_queue,
        )
        self.assertIn("shop fit", selection.selection_reason)
        self.assertIn("IP safety", selection.selection_reason)

    def test_render_report_contains_required_sections(self) -> None:
        rendered_report = self.agent.render_report(self.paths)

        required_sections = (
            "Current Shop Summary",
            "Market Trends",
            "Seasonal Opportunities",
            "Competition Estimate",
            "Selected for Production Today",
            "Top 10 Recommended Products",
            "Future Collection Suggestions",
        )
        for section in required_sections:
            self.assertIn(section, rendered_report)

    def test_report_uses_local_sample_data(self) -> None:
        rendered_report = self.agent.render_report(self.paths)

        self.assertIn("RainbowMilkStudio", rendered_report)
        self.assertIn("Coquette Bows Printable Planner", rendered_report)
        self.assertIn("Today's Best Product", rendered_report)
        self.assertIn("Move into Production Queue", rendered_report)


if __name__ == "__main__":
    unittest.main()
