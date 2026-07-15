"""Tests for Sprint 24 research-driven production intelligence."""

from __future__ import annotations

import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(SRC_PATH))
sys.path.insert(0, str(PROJECT_ROOT))

from project_aurora.planning.production_queue_manager import (  # noqa: E402
    ProductionQueueManager,
)
from project_aurora.portfolio.atlas_portfolio_manager import (  # noqa: E402
    AtlasPortfolioManager,
)
from project_aurora.research.athena_market_intelligence import (  # noqa: E402
    AthenaMarketIntelligence,
)
from project_aurora.research.market_opportunity import MarketOpportunity  # noqa: E402
from project_aurora.research.research_config import ResearchPlannerConfig  # noqa: E402
from project_aurora.storage.csv_storage import CSVStorage  # noqa: E402
from project_aurora.storage.memory_manager import MemoryManager  # noqa: E402
from scripts.run_research_planner import (  # noqa: E402
    handoff_to_forge,
    print_quality_gate,
    request_production_approval,
)


class FailingProvider:
    provider_name = "Mock Etsy"
    priority = 1

    def collect(self) -> tuple[MarketOpportunity, ...]:
        raise RuntimeError("Mock credentials missing.")


class OpportunityProvider:
    provider_name = "Mock Research"
    priority = 1

    def __init__(self, opportunities: tuple[MarketOpportunity, ...]) -> None:
        self._opportunities = opportunities

    def collect(self) -> tuple[MarketOpportunity, ...]:
        return self._opportunities


def opportunity(
    index: int,
    *,
    niche: str | None = None,
    audience: str | None = None,
    season: str | None = None,
    product_type: str | None = None,
    style: str | None = None,
    confidence: float = 91,
) -> MarketOpportunity:
    """Build a diverse test opportunity."""
    niches = ("Nursery", "Kitchen", "Teacher", "Wedding", "Botanical", "Holiday")
    audiences = ("parents", "home decorators", "teachers", "brides", "crafters", "gift buyers")
    seasons = ("Spring", "Summer", "Back To School", "Wedding Season", "Fall", "Winter")
    product_types = (
        "wall art",
        "clipart",
        "sticker sheet",
        "party printable",
        "digital paper",
        "junk journal",
    )
    styles = (
        "Soft Nursery",
        "French Country",
        "Kawaii",
        "Boho",
        "Vintage Botanical",
        "Minimalist",
    )
    return MarketOpportunity(
        keyword=f"{niche or niches[index % len(niches)]} Product {index}",
        primary_niche=niche or niches[index % len(niches)],
        subcategory="Test Subcategory",
        target_audience=audience or audiences[index % len(audiences)],
        season=season or seasons[index % len(seasons)],
        product_type=product_type or product_types[index % len(product_types)],
        recommended_artistic_style=style or styles[index % len(styles)],
        trend_score=90 - index * 0.1,
        competition_score=30 + index * 0.1,
        commercial_potential=90,
        confidence=confidence,
        research_sources=("Mock Research",),
    )


class ResearchPlannerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base_path = Path(self.temp_dir.name)
        self.memory = MemoryManager(CSVStorage(base_path=self.base_path / "aurora"))
        self.queue = ProductionQueueManager(queue_path=self.base_path / "queue.json")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def config(self, **overrides: object) -> ResearchPlannerConfig:
        values = {
            "minimum_confidence": 85,
            "candidate_count": 50,
            "daily_products": 5,
            "duplicate_threshold": 0.80,
            "max_per_style": 1,
            "max_per_category": 1,
            "max_per_audience": 1,
            "max_per_season": 1,
            "max_per_product_type": 1,
        }
        values.update(overrides)
        return ResearchPlannerConfig(**values)

    def test_research_provider_unavailable_is_recorded(self) -> None:
        engine = AthenaMarketIntelligence(
            providers=(FailingProvider(),),
            memory=self.memory,
            candidate_count=50,
        )

        report = engine.run()

        self.assertEqual(len(report.opportunities), 0)
        self.assertEqual(report.provider_statuses[0].status, "UNAVAILABLE")
        self.assertIn("Mock credentials missing", report.provider_statuses[0].detail)

    def test_candidate_generation_minimum_50_and_memory_save(self) -> None:
        opportunities = tuple(opportunity(index) for index in range(60))
        engine = AthenaMarketIntelligence(
            providers=(OpportunityProvider(opportunities),),
            memory=self.memory,
            candidate_count=50,
        )

        report = engine.run()
        saved = self.memory.load_record("market_opportunities", "latest")

        self.assertEqual(len(report.opportunities), 50)
        self.assertEqual(saved["opportunity_count"], 50)

    def test_portfolio_diversity_selects_exactly_five(self) -> None:
        opportunities = tuple(opportunity(index) for index in range(12))

        plan = AtlasPortfolioManager(
            config=self.config(),
            queue_manager=self.queue,
            memory=self.memory,
        ).build_portfolio(opportunities)

        self.assertEqual(len(plan.selected), 5)
        for distribution in plan.diversity().values():
            self.assertTrue(all(value == 1 for value in distribution.values()))

    def test_duplicate_prevention_rejects_existing_queue_product(self) -> None:
        self.queue.add_job(
            priority="High",
            product_name="Nursery Product 0",
            category="wall art",
            style="Soft Nursery",
            seasonal_theme="Spring",
            keywords=("nursery",),
            confidence_score=0.91,
            estimated_competition="Low",
            estimated_demand="High",
            estimated_revenue=100,
        )
        opportunities = (opportunity(0),) + tuple(opportunity(index) for index in range(1, 8))

        plan = AtlasPortfolioManager(
            config=self.config(),
            queue_manager=self.queue,
            memory=self.memory,
        ).build_portfolio(opportunities)

        self.assertNotIn("Nursery Product 0", [item.keyword for item in plan.selected])
        rejected = {item.keyword: reason for item, reason in plan.rejected}
        self.assertEqual(rejected["Nursery Product 0"], "Duplicate historical product")

    def test_confidence_threshold_blocks_weak_portfolio(self) -> None:
        opportunities = tuple(opportunity(index, confidence=70) for index in range(8))

        plan = AtlasPortfolioManager(
            config=self.config(minimum_confidence=85),
            queue_manager=self.queue,
            memory=self.memory,
        ).build_portfolio(opportunities)

        self.assertFalse(plan.quality_gate_passed)
        self.assertLess(plan.average_confidence, 85)

    def test_business_report_generation(self) -> None:
        opportunities = tuple(opportunity(index) for index in range(8))

        plan = AtlasPortfolioManager(
            config=self.config(),
            queue_manager=self.queue,
            memory=self.memory,
        ).build_portfolio(opportunities)
        report = plan.to_report()

        self.assertEqual(len(report["business_decision_report"]), 5)
        first = report["business_decision_report"][0]
        self.assertIn("business_reason", first)
        self.assertIn("reason_selected", first)
        self.assertEqual(first["recommended_price"], 1.99)
        self.assertTrue(first["research_sources"])

    def test_approval_workflow(self) -> None:
        opportunities = tuple(opportunity(index) for index in range(8))
        plan = AtlasPortfolioManager(
            config=self.config(),
            queue_manager=self.queue,
            memory=self.memory,
        ).build_portfolio(opportunities)

        with redirect_stdout(StringIO()):
            approved = request_production_approval(
                plan,
                estimate=type("Estimate", (), {"render": lambda self: "$0.80"})(),
                input_fn=lambda prompt: "APPROVE",
            )
            rejected = request_production_approval(
                plan,
                estimate=type("Estimate", (), {"render": lambda self: "$0.80"})(),
                input_fn=lambda prompt: "no",
            )

        self.assertTrue(approved)
        self.assertFalse(rejected)

    def test_handoff_to_forge_uses_approved_plan_without_research_regeneration(self) -> None:
        opportunities = tuple(opportunity(index) for index in range(8))
        plan = AtlasPortfolioManager(
            config=self.config(),
            queue_manager=self.queue,
            memory=self.memory,
        ).build_portfolio(opportunities)

        created = handoff_to_forge(plan, self.queue)

        self.assertEqual(created, 5)
        self.assertEqual(len(self.queue.list_jobs()), 5)
        self.assertTrue(all(job.status == "READY" for job in self.queue.list_jobs()))

    def test_four_selected_with_confidence_pass_uses_replacement_search(self) -> None:
        opportunities = (
            opportunity(0, confidence=88),
            opportunity(1, confidence=88),
            opportunity(2, confidence=88),
            opportunity(3, confidence=88),
            opportunity(
                20,
                niche="Animals",
                audience="pet buyers",
                season="Evergreen",
                product_type="clipart",
                style="Realistic",
                confidence=88,
            ),
        )

        plan = AtlasPortfolioManager(
            config=self.config(minimum_confidence=85),
            queue_manager=self.queue,
            memory=self.memory,
        ).build_portfolio(opportunities)

        self.assertEqual(len(plan.selected), 5)
        self.assertEqual(plan.quality_gate["portfolio_size"], "PASS")
        self.assertEqual(plan.quality_gate["confidence"], "PASS")
        self.assertEqual(plan.quality_gate["status"], "READY_FOR_APPROVAL")

    def test_fifth_candidate_found_without_relaxation(self) -> None:
        opportunities = tuple(opportunity(index, confidence=89) for index in range(5))

        plan = AtlasPortfolioManager(
            config=self.config(),
            queue_manager=self.queue,
            memory=self.memory,
        ).build_portfolio(opportunities)

        self.assertEqual(len(plan.selected), 5)
        self.assertEqual(plan.constraint_relaxations, ())

    def test_fifth_candidate_found_after_one_controlled_relaxation(self) -> None:
        opportunities = (
            opportunity(0),
            opportunity(1),
            opportunity(2),
            opportunity(3),
            opportunity(
                10,
                niche="Animals",
                audience="pet buyers",
                season="Evergreen",
                product_type="wall art",
                style="Realistic",
                confidence=90,
            ),
        )

        plan = AtlasPortfolioManager(
            config=self.config(),
            queue_manager=self.queue,
            memory=self.memory,
        ).build_portfolio(opportunities)

        self.assertEqual(len(plan.selected), 5)
        self.assertEqual(
            plan.constraint_relaxations[0]["constraint"],
            "Allow second product type",
        )
        self.assertEqual(plan.quality_gate["status"], "READY_FOR_APPROVAL")

    def test_confidence_pass_but_size_failure_is_reported_separately(self) -> None:
        opportunities = tuple(opportunity(index, confidence=88) for index in range(4))

        plan = AtlasPortfolioManager(
            config=self.config(minimum_confidence=85),
            queue_manager=self.queue,
            memory=self.memory,
        ).build_portfolio(opportunities)

        self.assertEqual(plan.quality_gate["required_products"], 5)
        self.assertEqual(plan.quality_gate["selected_products"], 4)
        self.assertEqual(plan.quality_gate["portfolio_size"], "FAIL")
        self.assertEqual(plan.quality_gate["confidence"], "PASS")
        self.assertEqual(plan.quality_gate["status"], "QUALITY_GATE_BLOCKED")

    def test_size_pass_but_confidence_failure_is_reported_separately(self) -> None:
        opportunities = tuple(opportunity(index, confidence=86) for index in range(5))

        plan = AtlasPortfolioManager(
            config=self.config(minimum_confidence=90),
            queue_manager=self.queue,
            memory=self.memory,
        ).build_portfolio(opportunities)

        self.assertEqual(plan.quality_gate["selected_products"], 5)
        self.assertEqual(plan.quality_gate["portfolio_size"], "PASS")
        self.assertEqual(plan.quality_gate["confidence"], "FAIL")
        self.assertEqual(plan.quality_gate["status"], "QUALITY_GATE_BLOCKED")

    def test_exactly_five_products_required_before_approval(self) -> None:
        opportunities = tuple(opportunity(index, confidence=88) for index in range(4))
        plan = AtlasPortfolioManager(
            config=self.config(minimum_confidence=85),
            queue_manager=self.queue,
            memory=self.memory,
        ).build_portfolio(opportunities)

        with redirect_stdout(StringIO()) as output:
            approved = request_production_approval(
                plan,
                estimate=type("Estimate", (), {"render": lambda self: "$0.80"})(),
                input_fn=lambda prompt: "APPROVE",
            )
            print_quality_gate(plan)

        self.assertFalse(approved)
        self.assertIn("Selected Products\n4", output.getvalue())
        self.assertIn("Portfolio Size\nFAIL", output.getvalue())


if __name__ == "__main__":
    unittest.main()
