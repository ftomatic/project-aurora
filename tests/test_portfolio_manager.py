"""Tests for Sprint 23 AI Portfolio Manager."""

from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_PATH))

from project_aurora.planning.dynamic_product_planner import ProductCandidate  # noqa: E402
from project_aurora.planning.production_queue_manager import (  # noqa: E402
    ProductionQueueManager,
)
from project_aurora.portfolio.ai_portfolio_manager import (  # noqa: E402
    AIPortfolioManager,
    PortfolioRules,
)
from project_aurora.portfolio.market_segments import classify_market_category  # noqa: E402
from project_aurora.portfolio.portfolio_memory import (  # noqa: E402
    PortfolioMemory,
    PortfolioMemoryRecord,
)
from project_aurora.research.dynamic_market_research import (  # noqa: E402
    DynamicResearchReport,
)


def candidate(
    name: str,
    *,
    product_type: str = "clipart",
    audience: str = "parents",
    style: str = "Storybook Watercolor",
    season: str = "evergreen",
    demand: float = 0.8,
    competition: float = 0.35,
    confidence: float = 0.86,
    keywords: tuple[str, ...] = (),
) -> ProductCandidate:
    """Build a test product candidate."""
    return ProductCandidate(
        product_name=name,
        product_type=product_type,
        target_customer=audience,
        style=style,
        season=season,
        keywords=keywords or tuple(name.casefold().split()),
        demand_score=demand,
        competition_score=competition,
        confidence_score=confidence,
        source_evidence=("test",),
    )


def research() -> DynamicResearchReport:
    """Return a minimal local research report."""
    return DynamicResearchReport(
        signals=(),
        providers_used=("Etsy API", "Google Trends", "Seasonal Calendar"),
        providers_unavailable=(),
    )


class AIPortfolioManagerTest(unittest.TestCase):
    def test_category_balancing(self) -> None:
        manager = AIPortfolioManager(
            PortfolioRules(
                max_per_category=2,
                max_per_style=20,
                max_per_audience=20,
                max_per_season=20,
                max_per_product_type=20,
            )
        )
        candidates = (
            candidate("Nursery Bunny Clipart", keywords=("nursery", "bunny")),
            candidate("Nursery Bear Clipart", keywords=("nursery", "bear")),
            candidate("Nursery Moon Clipart", keywords=("nursery", "moon")),
            candidate("Christmas Tags Clipart", keywords=("christmas", "tags")),
            candidate("Christmas Ornament Clipart", keywords=("christmas",)),
            candidate("Kitchen Lemon Wall Art", product_type="wall art", keywords=("kitchen",)),
            candidate("Botanical Rose Digital Paper", product_type="digital paper", keywords=("botanical",)),
            candidate("Boho Rainbow Sticker Sheet", product_type="sticker sheet", keywords=("boho",)),
            candidate("Farmhouse Cow Clipart", keywords=("farmhouse", "cow")),
            candidate("Wedding Floral Invitation", product_type="party printable", keywords=("wedding",)),
            candidate("Halloween Ghost Clipart", keywords=("halloween",)),
            candidate("Teacher Classroom Stickers", product_type="sticker sheet", keywords=("teacher",)),
        )

        plan = manager.plan(
            candidates=candidates,
            research=research(),
            memory=PortfolioMemory(),
            count=10,
        )

        counts = plan.category_distribution()
        self.assertEqual(len(plan.selected), 10)
        self.assertTrue(all(value <= 2 for value in counts.values()))

    def test_style_balancing(self) -> None:
        styles = (
            "Storybook Watercolor",
            "Storybook Watercolor",
            "Storybook Watercolor",
            "Vintage Botanical",
            "Vintage Botanical",
            "Soft Nursery",
            "Cute Halloween",
            "Boho",
            "Minimalist",
            "Gouache",
            "Pencil Sketch",
        )
        candidates = tuple(
            candidate(
                f"Portfolio Product {index} Clipart",
                style=style,
                audience=f"audience {index}",
                season=f"season {index}",
                keywords=(f"category{index}",),
            )
            for index, style in enumerate(styles, start=1)
        )

        plan = AIPortfolioManager(
            PortfolioRules(
                max_per_category=20,
                max_per_style=2,
                max_per_audience=20,
                max_per_season=20,
                max_per_product_type=20,
            )
        ).plan(
            candidates=candidates,
            research=research(),
            memory=PortfolioMemory(),
            count=10,
        )

        self.assertTrue(all(value <= 2 for value in plan.style_distribution().values()))

    def test_duplicate_prevention_uses_historical_memory(self) -> None:
        duplicate = "Woodland Baby Animals Clipart Bundle"
        memory = PortfolioMemory(
            (
                PortfolioMemoryRecord(
                    product_name=duplicate,
                    market_category="Animals",
                    audience="Parents",
                    art_style="Storybook Watercolor",
                    product_type="clipart",
                    holiday="evergreen",
                    keywords=("woodland", "baby", "animals"),
                    date_produced=date.today(),
                    queue_status="COMPLETED",
                ),
            )
        )
        candidates = (
            candidate(duplicate, keywords=("woodland", "baby", "animals")),
            candidate("Kitchen Strawberry Wall Art", product_type="wall art", keywords=("kitchen",)),
            candidate("Teacher Apple Sticker Sheet", product_type="sticker sheet", keywords=("teacher",)),
        )

        plan = AIPortfolioManager().plan(
            candidates=candidates,
            research=research(),
            memory=memory,
            count=2,
        )

        self.assertNotIn(duplicate, [item.product_name for item in plan.selected])
        self.assertIn(duplicate, [item.product_name for item in plan.rejected_duplicates])

    def test_portfolio_scoring_prefers_demand_and_low_competition(self) -> None:
        high = candidate(
            "High Opportunity Floral Clipart",
            demand=0.96,
            competition=0.18,
            confidence=0.95,
            keywords=("floral", "commercial", "clipart"),
        )
        low = candidate(
            "Low Opportunity Floral Clipart",
            demand=0.45,
            competition=0.86,
            confidence=0.5,
            keywords=("floral",),
        )

        plan = AIPortfolioManager().plan(
            candidates=(low, high),
            research=research(),
            memory=PortfolioMemory(),
            count=1,
        )

        self.assertEqual(plan.selected[0].product_name, high.product_name)
        self.assertGreater(plan.candidates[0].score, plan.candidates[-1].score)

    def test_wildcard_is_highest_confidence_remaining_opportunity(self) -> None:
        candidates = (
            candidate("Balanced Nursery Clipart", confidence=0.82, keywords=("nursery",)),
            candidate("Balanced Kitchen Wall Art", product_type="wall art", confidence=0.81, keywords=("kitchen",)),
            candidate("Emerging Coquette Bow Clipart", confidence=0.99, demand=0.92, keywords=("coquette", "bow")),
        )

        plan = AIPortfolioManager().plan(
            candidates=candidates,
            research=research(),
            memory=PortfolioMemory(),
            count=2,
        )

        self.assertIsNotNone(plan.wildcard)
        self.assertEqual(plan.wildcard.product_name, "Emerging Coquette Bow Clipart")

    def test_memory_can_be_built_from_queue(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            queue = ProductionQueueManager(queue_path=Path(temp_dir) / "queue.json")
            queue.add_job(
                priority="High",
                product_name="Vintage Christmas Tags Clipart",
                category="clipart",
                style="Vintage Christmas",
                seasonal_theme="Christmas",
                keywords=("vintage", "christmas", "tags"),
                confidence_score=0.9,
                estimated_competition="Low",
                estimated_demand="High",
                estimated_revenue=120,
                target_customer="crafters",
            )

            memory = PortfolioMemory.from_queue(queue)

        self.assertEqual(len(memory.records), 1)
        self.assertEqual(memory.records[0].market_category, "Christmas")
        self.assertEqual(memory.records[0].audience, "Crafters")

    def test_style_rotation_avoids_repetitive_artwork(self) -> None:
        memory = PortfolioMemory(
            (
                PortfolioMemoryRecord(
                    product_name="Woodland Fox Clipart",
                    market_category="Animals",
                    audience="Parents",
                    art_style="Storybook Watercolor",
                    product_type="clipart",
                    holiday="evergreen",
                    keywords=("woodland", "fox"),
                    date_produced=date.today(),
                    queue_status="COMPLETED",
                ),
            )
        )
        candidates = (
            candidate(
                "Woodland Deer Clipart",
                style="Storybook Watercolor",
                keywords=("woodland", "deer", "animals"),
            ),
        )

        plan = AIPortfolioManager().plan(
            candidates=candidates,
            research=research(),
            memory=memory,
            count=1,
        )

        self.assertNotEqual(plan.selected[0].art_style, "Storybook Watercolor")

    def test_market_category_classifier_supports_many_segments(self) -> None:
        self.assertEqual(
            classify_market_category(
                "French Country Kitchen Wall Art",
                "wall art",
                ("kitchen", "farmhouse"),
            ),
            "Kitchen",
        )

    def test_report_contains_required_daily_sections(self) -> None:
        candidates = tuple(
            candidate(
                f"Report Product {index} Clipart",
                audience=f"audience {index}",
                season=f"season {index}",
                keywords=(f"keyword{index}",),
            )
            for index in range(1, 4)
        )
        plan = AIPortfolioManager(
            PortfolioRules(max_per_category=3, max_per_style=3)
        ).plan(
            candidates=candidates,
            research=research(),
            memory=PortfolioMemory(),
            count=3,
        )

        report = plan.to_report()

        self.assertIn("category_distribution", report)
        self.assertIn("trend_sources_used", report)
        self.assertIn("wildcard_selection", report)
        self.assertIn("estimated_revenue_opportunity", report)


if __name__ == "__main__":
    unittest.main()
