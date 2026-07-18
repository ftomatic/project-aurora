"""Tests for Sprint 33 Opportunity Intelligence Engine."""

from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_PATH))

from project_aurora.opportunity_intelligence import OpportunityIntelligenceEngine  # noqa: E402
from project_aurora.planning.production_queue_manager import ProductionQueueManager  # noqa: E402
from project_aurora.portfolio.atlas_portfolio_manager import AtlasPortfolioManager  # noqa: E402
from project_aurora.research.athena_market_intelligence import (  # noqa: E402
    AthenaMarketIntelligence,
)
from project_aurora.research.market_opportunity import MarketOpportunity  # noqa: E402
from project_aurora.research.research_config import ResearchPlannerConfig  # noqa: E402
from project_aurora.storage.csv_storage import CSVStorage  # noqa: E402
from project_aurora.storage.memory_manager import MemoryManager  # noqa: E402


class MockProvider:
    provider_name = "Mock Market Research"
    priority = 1

    def __init__(self, opportunities: tuple[MarketOpportunity, ...]) -> None:
        self._opportunities = opportunities

    def collect(self) -> tuple[MarketOpportunity, ...]:
        return self._opportunities


def opportunity(
    keyword: str,
    *,
    niche: str = "Nursery",
    audience: str = "parents",
    season: str = "Summer",
    product_type: str = "clipart",
    style: str = "Storybook Watercolor",
    trend: float = 90,
    competition: float = 35,
    commercial: float = 90,
    confidence: float = 91,
) -> MarketOpportunity:
    return MarketOpportunity(
        keyword=keyword,
        primary_niche=niche,
        subcategory=f"{niche} Subcategory",
        target_audience=audience,
        season=season,
        product_type=product_type,
        recommended_artistic_style=style,
        trend_score=trend,
        competition_score=competition,
        commercial_potential=commercial,
        confidence=confidence,
        research_sources=("Mock Market Research",),
    )


class OpportunityIntelligenceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base_path = Path(self.temp_dir.name)
        self.memory = MemoryManager(CSVStorage(base_path=self.base_path / "memory"))
        self.queue = ProductionQueueManager(queue_path=self.base_path / "queue.json")
        self.engine = OpportunityIntelligenceEngine(current_date=datetime(2026, 7, 17))

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def config(self) -> ResearchPlannerConfig:
        return ResearchPlannerConfig(
            minimum_confidence=85,
            candidate_count=50,
            daily_products=5,
            minimum_portfolio_size=3,
            max_per_style=1,
            max_per_category=1,
            max_per_audience=1,
            max_per_season=1,
            max_per_product_type=1,
        )

    def test_higher_demand_increases_score(self) -> None:
        low = self.engine.score(opportunity("Low Demand Clipart", trend=60))
        high = self.engine.score(opportunity("High Demand Clipart", trend=95))

        self.assertGreater(high.opportunity_score, low.opportunity_score)
        self.assertGreater(high.contributions["demand"], low.contributions["demand"])

    def test_higher_competition_lowers_score(self) -> None:
        low_competition = self.engine.score(opportunity("Low Competition Clipart", competition=20))
        high_competition = self.engine.score(opportunity("High Competition Clipart", competition=80))

        self.assertGreater(low_competition.opportunity_score, high_competition.opportunity_score)
        self.assertGreater(
            low_competition.contributions["competition"],
            high_competition.contributions["competition"],
        )

    def test_higher_margin_product_type_increases_score(self) -> None:
        clipart = self.engine.score(opportunity("Woodland Clipart", product_type="clipart"))
        wall_art = self.engine.score(opportunity("Woodland Wall Art", product_type="wall art"))

        self.assertGreater(clipart.margin_score, wall_art.margin_score)
        self.assertGreater(clipart.average_selling_price_score, wall_art.average_selling_price_score)

    def test_seasonality_changes_ranking(self) -> None:
        summer = self.engine.score(opportunity("Summer Party Bundle", season="Summer"))
        spring = self.engine.score(opportunity("Spring Bunny Printable", season="Spring"))

        self.assertGreater(summer.seasonality_score, spring.seasonality_score)
        self.assertGreater(summer.opportunity_score, spring.opportunity_score)

    def test_portfolio_diversity_affects_score(self) -> None:
        selected = (
            opportunity(
                "Existing Nursery Clipart",
                niche="Nursery",
                audience="parents",
                season="Summer",
                product_type="clipart",
                style="Storybook Watercolor",
            ),
        )
        related = self.engine.score(
            opportunity(
                "Another Nursery Clipart",
                niche="Nursery",
                audience="parents",
                season="Summer",
                product_type="clipart",
                style="Storybook Watercolor",
            ),
            selected_today=selected,
        )
        different = self.engine.score(
            opportunity(
                "Kitchen Digital Paper",
                niche="Kitchen",
                audience="home decorators",
                season="Fall",
                product_type="digital paper",
                style="Vintage Botanical",
            ),
            selected_today=selected,
        )

        self.assertGreater(different.portfolio_diversity_score, related.portfolio_diversity_score)

    def test_merchant_report_sorts_by_opportunity_score(self) -> None:
        opportunities = (
            opportunity("Weak Product", niche="A", audience="A", season="Spring", product_type="wall art", style="A", trend=70, competition=70, commercial=70),
            opportunity("Strong Product", niche="B", audience="B", season="Summer", product_type="clipart", style="B", trend=95, competition=20, commercial=95),
            opportunity("Middle Product", niche="C", audience="C", season="Fall", product_type="digital paper", style="C", trend=84, competition=35, commercial=85),
            opportunity("Fourth Product", niche="D", audience="D", season="Winter", product_type="sticker sheet", style="D", trend=84, competition=40, commercial=84),
            opportunity("Fifth Product", niche="E", audience="E", season="Wedding Season", product_type="party printable", style="E", trend=86, competition=39, commercial=85),
        )

        plan = AtlasPortfolioManager(
            config=self.config(),
            queue_manager=self.queue,
            memory=self.memory,
        ).build_portfolio(opportunities)

        report_scores = [
            item["opportunity_score"]
            for item in plan.to_report()["business_decision_report"]
        ]
        self.assertEqual(report_scores, sorted(report_scores, reverse=True))
        self.assertEqual(plan.decisions[0].product, "Strong Product")

    def test_top_n_selection_is_deterministic(self) -> None:
        opportunities = (
            opportunity("Same Score B", niche="B", audience="B", season="Summer", product_type="clipart", style="B"),
            opportunity("Same Score A", niche="A", audience="A", season="Summer", product_type="clipart", style="A"),
            opportunity("Same Score C", niche="C", audience="C", season="Summer", product_type="clipart", style="C"),
        )

        ranked = self.engine.rank(opportunities)

        self.assertEqual([item.keyword for item, _score in ranked], ["Same Score A", "Same Score B", "Same Score C"])

    def test_athena_persists_opportunity_scores_and_future_learning_fields(self) -> None:
        opportunities = (opportunity("Future Learning Clipart"),)
        report = AthenaMarketIntelligence(
            providers=(MockProvider(opportunities),),
            memory=self.memory,
            candidate_count=1,
        ).run()

        saved_report = self.memory.load_record("market_opportunities", "latest")
        score_keys = self.memory.list_records("opportunity_scores")
        saved_score = self.memory.load_record("opportunity_scores", report.opportunities[0].id)

        self.assertEqual(len(saved_report["opportunity_scores"]), 1)
        self.assertEqual(score_keys, (report.opportunities[0].id,))
        self.assertIn("future_learning", saved_score)
        self.assertIsNone(saved_score["future_learning"]["sales"])

    def test_rejected_products_include_weakest_factor_and_suggestion(self) -> None:
        opportunities = (
            opportunity("Nursery One", niche="Nursery", audience="parents", season="Summer", product_type="clipart", style="A"),
            opportunity("Nursery Two", niche="Nursery", audience="teachers", season="Fall", product_type="wall art", style="B"),
            opportunity("Kitchen One", niche="Kitchen", audience="home", season="Winter", product_type="digital paper", style="C"),
        )

        plan = AtlasPortfolioManager(
            config=self.config(),
            queue_manager=self.queue,
            memory=self.memory,
        ).build_portfolio(opportunities)
        rejected_reasons = " ".join(reason for _item, reason in plan.rejected)

        self.assertIn("Opportunity Score", rejected_reasons)
        self.assertIn("Weakest factor", rejected_reasons)
        self.assertIn("Suggested improvement", rejected_reasons)


if __name__ == "__main__":
    unittest.main()
