"""Tests for Sprint 31 intelligent portfolio memory."""

from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(SRC_PATH))

from project_aurora.planning.production_queue_manager import (  # noqa: E402
    ProductionQueueManager,
)
from project_aurora.portfolio.atlas_portfolio_manager import AtlasPortfolioManager  # noqa: E402
from project_aurora.portfolio.merchant_memory import (  # noqa: E402
    EXACT_DUPLICATE,
    SEASONAL_REFRESH,
    MerchantMemoryRecord,
    analyze_similarity,
    record_from_opportunity,
    similarity_score,
)
from project_aurora.research.market_opportunity import MarketOpportunity  # noqa: E402
from project_aurora.research.research_config import ResearchPlannerConfig  # noqa: E402
from project_aurora.storage.csv_storage import CSVStorage  # noqa: E402
from project_aurora.storage.memory_manager import MemoryManager  # noqa: E402
from scripts.run_research_planner import handoff_to_forge  # noqa: E402


def config(**overrides: object) -> ResearchPlannerConfig:
    values = {
        "minimum_confidence": 85,
        "candidate_count": 50,
        "daily_products": 5,
        "minimum_portfolio_size": 3,
        "duplicate_threshold": 0.80,
        "max_per_style": 5,
        "max_per_category": 5,
        "max_per_audience": 5,
        "max_per_season": 5,
        "max_per_product_type": 5,
    }
    values.update(overrides)
    return ResearchPlannerConfig(**values)


def opp(
    name: str,
    *,
    product_type: str = "digital paper",
    style: str = "Watercolor",
    niche: str = "Woodland",
    audience: str = "crafters",
    season: str = "Winter",
    confidence: float = 91,
) -> MarketOpportunity:
    return MarketOpportunity(
        keyword=name,
        primary_niche=niche,
        subcategory=niche,
        target_audience=audience,
        season=season,
        product_type=product_type,
        recommended_artistic_style=style,
        trend_score=90,
        competition_score=35,
        commercial_potential=90,
        confidence=confidence,
        research_sources=("Mock Research",),
    )


class Sprint31PortfolioMemoryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base_path = Path(self.temp_dir.name)
        self.memory = MemoryManager(CSVStorage(base_path=self.base_path / "memory"))
        self.queue = ProductionQueueManager(queue_path=self.base_path / "queue.json")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def build(self, opportunities: tuple[MarketOpportunity, ...]):
        return AtlasPortfolioManager(
            config=config(),
            queue_manager=self.queue,
            memory=self.memory,
        ).build_portfolio(opportunities)

    def test_flexible_quality_gate_sizes(self) -> None:
        for count, expected in ((5, True), (4, True), (3, True), (2, False), (0, False)):
            with self.subTest(count=count):
                opportunities = tuple(
                    opp(
                        f"Product {index}",
                        product_type=f"type-{index}",
                        style=f"style-{index}",
                        niche=f"niche-{index}",
                        audience=f"audience-{index}",
                        season=f"season-{index}",
                    )
                    for index in range(count)
                )
                plan = self.build(opportunities)

                self.assertEqual(plan.quality_gate_passed, expected)
                self.assertEqual(plan.quality_gate["selected"], count)
                if expected:
                    self.assertEqual(plan.quality_gate["portfolio_size"], "PASS")
                else:
                    self.assertEqual(plan.quality_gate["portfolio_size"], "FAIL")

    def test_exact_duplicate_rejected(self) -> None:
        self.queue.add_job(
            priority="High",
            product_name="Winter Woodland Digital Paper",
            category="digital paper",
            style="Watercolor",
            seasonal_theme="Winter",
            keywords=("winter", "woodland", "digital", "paper"),
            confidence_score=0.91,
            estimated_competition="Low",
            estimated_demand="High",
            estimated_revenue=100,
            target_customer="crafters",
        )

        plan = self.build(
            (
                opp("Winter Woodland Digital Paper"),
                opp("Botanical Kitchen Prints", product_type="wall art", style="Vintage", niche="Kitchen"),
                opp("Teacher Apple Stickers", product_type="sticker sheet", style="Vector", niche="Teacher"),
            )
        )

        rejected = {item.keyword: reason for item, reason in plan.rejected}
        self.assertIn("Winter Woodland Digital Paper", rejected)
        self.assertTrue(plan.merchant_rejections)
        self.assertEqual(plan.merchant_rejections[0]["duplicate_class"], EXACT_DUPLICATE)
        self.assertIn("suggested_alternatives", plan.merchant_rejections[0])

    def test_concept_variants_and_different_categories_allowed(self) -> None:
        memory_record = record_from_opportunity(opp("Winter Woodland Digital Paper"))

        variant = analyze_similarity(
            opp("Vintage Winter Woodland Paper", style="Vintage Botanical"),
            (memory_record,),
        )
        category_variant = analyze_similarity(
            opp("Woodland Nursery Prints", product_type="wall art", style="Storybook", audience="parents"),
            (memory_record,),
        )

        self.assertTrue(variant.allowed)
        self.assertTrue(category_variant.allowed)
        self.assertLess(variant.score, 100)

    def test_seasonal_refresh_cooldown(self) -> None:
        old = MerchantMemoryRecord(
            product_concept="Christmas Gift Tags",
            theme="Holiday",
            style="Watercolor",
            category="gift tags",
            bundle_size=4,
            target_audience="gift buyers",
            season="Christmas",
            keywords=("christmas", "gift", "tags"),
            creation_date=datetime.now() - timedelta(days=120),
        )
        recent = MerchantMemoryRecord(
            product_concept="Christmas Gift Tags",
            theme="Holiday",
            style="Watercolor",
            category="gift tags",
            bundle_size=4,
            target_audience="gift buyers",
            season="Christmas",
            keywords=("christmas", "gift", "tags"),
            creation_date=datetime.now() - timedelta(days=10),
        )

        allowed = analyze_similarity(opp("Christmas Gift Tags", product_type="gift tags", niche="Holiday"), (old,))
        blocked = analyze_similarity(opp("Christmas Gift Tags", product_type="gift tags", niche="Holiday"), (recent,))

        self.assertEqual(allowed.duplicate_class, SEASONAL_REFRESH)
        self.assertTrue(allowed.allowed)
        self.assertFalse(blocked.allowed)

    def test_similarity_scoring_ranges(self) -> None:
        base = record_from_opportunity(opp("Winter Woodland Digital Paper"))
        different = record_from_opportunity(opp("Kitchen Herb Wall Art", product_type="wall art", niche="Kitchen"))
        related = record_from_opportunity(opp("Woodland Clipart", product_type="clipart", style="Gouache"))
        duplicate = record_from_opportunity(opp("Winter Woodland Digital Paper"))

        self.assertLessEqual(similarity_score(base, different), 30)
        self.assertLess(similarity_score(base, related), 81)
        self.assertEqual(similarity_score(base, duplicate), 100)

    def test_queue_created_when_minimum_portfolio_satisfied(self) -> None:
        plan = self.build(
            tuple(
                opp(
                    f"Minimum Product {index}",
                    product_type=f"type-{index}",
                    style=f"style-{index}",
                    niche=f"niche-{index}",
                    audience=f"audience-{index}",
                    season=f"season-{index}",
                )
                for index in range(3)
            )
        )

        created = handoff_to_forge(plan, self.queue)

        self.assertTrue(plan.quality_gate_passed)
        self.assertEqual(created, 3)
        self.assertEqual(len(self.queue.list_jobs()), 3)

    def test_alternative_generator_uses_meaningful_theme_phrase(self) -> None:
        self.queue.add_job(
            priority="High",
            product_name="Back To School Teacher Stickers",
            category="sticker sheet",
            style="Kawaii",
            seasonal_theme="Back To School",
            keywords=("back", "to", "school", "teacher", "stickers"),
            confidence_score=0.91,
            estimated_competition="Low",
            estimated_demand="High",
            estimated_revenue=100,
            target_customer="teachers",
        )

        plan = self.build((opp("Back To School Teacher Stickers", product_type="sticker sheet", style="Kawaii", niche="Teacher", audience="teachers", season="Back To School"),))

        alternatives = plan.merchant_rejections[0]["suggested_alternatives"]
        self.assertIn("Teacher Alphabet Posters", alternatives)
        self.assertNotIn("Back Digital Paper", alternatives)


if __name__ == "__main__":
    unittest.main()
