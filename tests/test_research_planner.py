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
    COMPLETED,
    FAILED,
    ProductionQueueManager,
)
from project_aurora.production.generation_strategy import (  # noqa: E402
    GENERATION_MODE_STORYBOOK,
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
    build_brand_profile_portfolio_candidates,
    handoff_to_forge,
    parse_args,
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
    product_name: str | None = None,
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
        keyword=product_name or f"{niche or niches[index % len(niches)]} Product {index}",
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

    def test_duplicate_prevention_ranks_existing_queue_product_lower(self) -> None:
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
        self.assertTrue(plan.quality_gate_passed)

    def test_failed_queue_product_does_not_permanently_block_selection(self) -> None:
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
            status=FAILED,
        )
        opportunities = (opportunity(0),)

        plan = AtlasPortfolioManager(
            config=self.config(daily_products=1),
            queue_manager=self.queue,
            memory=self.memory,
        ).build_portfolio(opportunities)

        self.assertEqual([item.keyword for item in plan.selected], ["Nursery Product 0"])
        self.assertTrue(plan.quality_gate_passed)

    def test_research_planner_count_argument_sets_required_products(self) -> None:
        args = parse_args(["--auto-approve", "--count", "1"])

        self.assertTrue(args.auto_approve)
        self.assertEqual(args.count, 1)

    def test_confidence_threshold_warns_for_weak_portfolio(self) -> None:
        opportunities = tuple(opportunity(index, confidence=70) for index in range(8))

        plan = AtlasPortfolioManager(
            config=self.config(minimum_confidence=85),
            queue_manager=self.queue,
            memory=self.memory,
        ).build_portfolio(opportunities)

        self.assertTrue(plan.quality_gate_passed)
        self.assertEqual(plan.quality_gate["status"], "READY_WITH_WARNINGS")
        self.assertIn("Confidence preference relaxed.", plan.quality_gate["warnings"])
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
        opportunities = (
            opportunity(
                0,
                niche="Woodland",
                product_name="Fox Woodland Watercolor Clipart",
                audience="parents",
                season="Evergreen",
                product_type="watercolor_woodland_collection",
                style="Storybook Watercolor",
            ),
            opportunity(
                1,
                niche="Botanical",
                product_name="Cottage Mushroom Botanical Clipart",
                audience="crafters",
                season="Spring",
                product_type="watercolor_botanical_collection",
                style="Vintage Botanical",
            ),
            opportunity(
                2,
                niche="Animals",
                product_name="Rabbit Tea Party Watercolor Clipart",
                audience="nursery buyers",
                season="Summer",
                product_type="watercolor_animal_collection",
                style="Soft Nursery",
            ),
            opportunity(
                3,
                niche="Mushrooms",
                product_name="Mouse Bakery Watercolor Clipart",
                audience="cottagecore buyers",
                season="Fall",
                product_type="watercolor_clipart_bundle",
                style="Cottagecore",
            ),
            opportunity(
                4,
                niche="Holiday",
                product_name="Bear Christmas Watercolor Clipart",
                audience="gift buyers",
                season="Winter",
                product_type="watercolor_seasonal_collection",
                style="Whimsical Storybook",
            ),
        )
        plan = AtlasPortfolioManager(
            config=self.config(max_per_product_type=5),
            queue_manager=self.queue,
            memory=self.memory,
        ).build_portfolio(opportunities)

        created = handoff_to_forge(plan, self.queue, generation_mode="storybook")

        self.assertEqual(created, 5)
        self.assertEqual(len(self.queue.list_jobs()), 5)
        self.assertTrue(all(job.status == "READY" for job in self.queue.list_jobs()))
        self.assertTrue(
            all(
                f"generation_mode={GENERATION_MODE_STORYBOOK}" in job.source_evidence
                for job in self.queue.list_jobs()
            )
        )

    def test_handoff_uses_fallback_candidates_when_selected_products_already_exist(self) -> None:
        existing = opportunity(
            0,
            product_name="Mouse Nursery Watercolor Clipart",
            product_type="watercolor_animal_collection",
            style="Storybook Watercolor",
        )
        replacement = opportunity(
            99,
            product_name="Fox Tea Party Watercolor Clipart",
            product_type="watercolor_animal_collection",
            style="Storybook Watercolor",
        )
        self.queue.add_job(
            priority="High",
            product_name=existing.keyword.title(),
            category="watercolor_animal_collection",
            style="Storybook Watercolor",
            seasonal_theme="Evergreen",
            keywords=("mouse", "nursery"),
            confidence_score=0.96,
            estimated_competition="Low",
            estimated_demand="High",
            estimated_revenue=100,
            status=COMPLETED,
        )
        plan = AtlasPortfolioManager(
            config=self.config(daily_products=1),
            queue_manager=self.queue,
            memory=self.memory,
        ).build_portfolio((existing,))

        with redirect_stdout(StringIO()) as output:
            created = handoff_to_forge(
                plan,
                self.queue,
                fallback_opportunities=(existing, replacement),
                target_new_jobs=1,
            )

        self.assertEqual(created, 1)
        names = {job.product_name for job in self.queue.list_jobs()}
        self.assertIn("Fox Tea Party Watercolor Clipart", names)
        rendered = output.getvalue()
        self.assertIn("Mouse Nursery Watercolor Clipart", rendered)
        self.assertIn("Production job already exists in queue.", rendered)

    def test_brand_profile_candidates_filter_legacy_products_before_atlas(self) -> None:
        legacy = (
            opportunity(
                0,
                product_name="Teacher Boho Rainbow Decor",
                niche="Teacher",
                product_type="classroom printable",
                style="Flat Vector",
            ),
            opportunity(
                1,
                product_name="Vintage Lace Digital Paper",
                niche="Digital Paper",
                product_type="digital paper",
                style="Vintage Botanical",
            ),
        )

        with redirect_stdout(StringIO()) as output:
            candidates = build_brand_profile_portfolio_candidates(
                legacy,
                target_count=5,
            )

        names = {candidate.keyword for candidate in candidates}
        self.assertNotIn("Teacher Boho Rainbow Decor", names)
        self.assertNotIn("Vintage Lace Digital Paper", names)
        self.assertTrue(any("Watercolor Clipart" in name for name in names))
        self.assertIn("Teacher Boho Rainbow Decor", output.getvalue())
        self.assertIn("Products Filtered", output.getvalue())

    def test_explicit_digital_paper_mode_selects_digital_paper_candidates(self) -> None:
        opportunities = (
            opportunity(
                0,
                product_name="Rabbit Gardening Watercolor Clipart",
                niche="Woodland",
                product_type="clipart",
                style="Storybook Watercolor",
            ),
            opportunity(
                1,
                product_name="Vintage Lace Digital Paper",
                niche="Digital Paper",
                product_type="digital paper",
                style="Vintage Botanical",
            ),
            opportunity(
                2,
                product_name="Moon Star Digital Paper",
                niche="Digital Paper",
                product_type="digital paper",
                style="Soft Nursery",
            ),
        )

        candidates = build_brand_profile_portfolio_candidates(
            opportunities,
            target_count=5,
            generation_mode="digital-paper",
        )

        names = {candidate.keyword for candidate in candidates}
        self.assertIn("Vintage Lace Digital Paper", names)
        self.assertIn("Moon Star Digital Paper", names)
        self.assertNotIn("Rabbit Gardening Watercolor Clipart", names)

    def test_handoff_logs_skipped_products_and_counts_attempts(self) -> None:
        opportunities = (
            opportunity(
                0,
                product_name="Teacher Boho Rainbow Decor",
                product_type="classroom printable",
                style="Flat Vector",
            ),
        )
        plan = AtlasPortfolioManager(
            config=self.config(daily_products=1, minimum_confidence=85),
            queue_manager=self.queue,
            memory=self.memory,
        ).build_portfolio(opportunities)

        with redirect_stdout(StringIO()) as output:
            created = handoff_to_forge(plan, self.queue)

        self.assertEqual(created, 0)
        self.assertIn("Enqueue Attempted\n1", output.getvalue())
        self.assertIn("Teacher Boho Rainbow Decor", output.getvalue())
        self.assertIn("SKIPPED", output.getvalue())
        self.assertIn("Unsupported recovery product type: teacher", output.getvalue())

    def test_handoff_explicit_digital_paper_uses_digital_print_category(self) -> None:
        opportunities = (
            opportunity(
                1,
                product_name="Vintage Lace Digital Paper",
                niche="Digital Paper",
                product_type="digital paper",
                style="Vintage Botanical",
            ),
        )
        plan = AtlasPortfolioManager(
            config=self.config(daily_products=1, minimum_confidence=85),
            queue_manager=self.queue,
            memory=self.memory,
        ).build_portfolio(opportunities)

        created = handoff_to_forge(
            plan,
            self.queue,
            generation_mode="digital-paper",
        )

        self.assertEqual(created, 1)
        job = self.queue.list_jobs()[0]
        self.assertEqual(job.category, "digital print")
        self.assertIn("generation_mode=DIGITAL_PAPER", job.source_evidence)

    def test_explicit_wedding_mode_selects_printable_wedding_candidates(self) -> None:
        opportunities = (
            opportunity(
                0,
                product_name="Hedgehog Tea Party Watercolor Clipart",
                niche="Woodland",
                product_type="clipart",
                style="Storybook Watercolor",
            ),
            opportunity(
                1,
                product_name="Coquette Bow Bridal Clipart",
                niche="Wedding",
                product_type="clipart",
                style="Coquette",
            ),
            opportunity(
                2,
                product_name="Vintage Lace Digital Paper",
                niche="Wedding",
                product_type="digital paper",
                style="Victorian",
            ),
            opportunity(
                3,
                product_name="Wildflower Wedding Invitation",
                niche="Wedding",
                product_type="party printable",
                style="Vintage Botanical",
            ),
            opportunity(
                4,
                product_name="French Country Wedding Menu",
                niche="Wedding",
                product_type="party printable",
                style="French Country",
            ),
        )

        candidates = build_brand_profile_portfolio_candidates(
            opportunities,
            target_count=5,
            generation_mode="wedding",
        )

        names = {candidate.keyword for candidate in candidates}
        self.assertIn("Wildflower Wedding Invitation", names)
        self.assertIn("French Country Wedding Menu", names)
        self.assertNotIn("Hedgehog Tea Party Watercolor Clipart", names)
        self.assertNotIn("Coquette Bow Bridal Clipart", names)
        self.assertNotIn("Vintage Lace Digital Paper", names)

    def test_explicit_character_mode_uses_character_candidates(self) -> None:
        candidates = build_brand_profile_portfolio_candidates(
            (),
            target_count=5,
            generation_mode="characters",
        )

        self.assertTrue(candidates)
        self.assertTrue(all("character" in item.keyword.casefold() for item in candidates))
        self.assertTrue(
            any("Kids" in item.keyword or "Fairy" in item.keyword for item in candidates)
        )
        self.assertTrue(
            all(item.product_type == "watercolor_character_collection" for item in candidates)
        )

    def test_explicit_botanical_mode_uses_botanical_candidates(self) -> None:
        candidates = build_brand_profile_portfolio_candidates(
            (),
            target_count=5,
            generation_mode="botanical",
        )

        names = {item.keyword for item in candidates}
        self.assertIn("Wildflower Meadow Botanical Clipart", names)
        self.assertIn("Flowering Tree Branch Botanical Clipart", names)
        self.assertTrue(all(item.product_type == "watercolor_botanical_collection" for item in candidates))

    def test_explicit_clipart_mode_uses_distinct_clipart_candidates(self) -> None:
        candidates = build_brand_profile_portfolio_candidates(
            (),
            target_count=5,
            generation_mode="clipart",
        )

        names = {item.keyword for item in candidates}
        self.assertIn("Bird Garden Watercolor Clipart", names)
        self.assertIn("Magical Tree House Watercolor Clipart", names)
        self.assertFalse(all("character" in item.keyword.casefold() for item in candidates))

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
        self.assertEqual(plan.quality_gate["status"], "READY_FOR_PRODUCTION")

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
        self.assertEqual(plan.quality_gate["status"], "READY_FOR_PRODUCTION")

    def test_confidence_pass_but_size_failure_is_reported_separately(self) -> None:
        opportunities = tuple(opportunity(index, confidence=88) for index in range(4))

        plan = AtlasPortfolioManager(
            config=self.config(minimum_confidence=85),
            queue_manager=self.queue,
            memory=self.memory,
        ).build_portfolio(opportunities)

        self.assertEqual(plan.quality_gate["required_products"], 5)
        self.assertEqual(plan.quality_gate["selected_products"], 4)
        self.assertEqual(plan.quality_gate["portfolio_size"], "PASS")
        self.assertEqual(plan.quality_gate["portfolio_size_warning"], "WARNING")
        self.assertEqual(plan.quality_gate["confidence"], "PASS")
        self.assertEqual(plan.quality_gate["status"], "READY_WITH_WARNINGS")

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
        self.assertEqual(plan.quality_gate["status"], "READY_WITH_WARNINGS")
        self.assertIn("Confidence preference relaxed.", plan.quality_gate["warnings"])

    def test_low_confidence_products_still_enter_production_with_warnings(self) -> None:
        opportunities = tuple(opportunity(index, confidence=60) for index in range(5))

        plan = AtlasPortfolioManager(
            config=self.config(minimum_confidence=85),
            queue_manager=self.queue,
            memory=self.memory,
        ).build_portfolio(opportunities)

        self.assertEqual(plan.quality_gate["selected_products"], 5)
        self.assertEqual(plan.quality_gate["portfolio_size"], "PASS")
        self.assertEqual(plan.quality_gate["status"], "READY_WITH_WARNINGS")

    def test_one_or_more_valid_products_required_before_approval(self) -> None:
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

        self.assertTrue(approved)
        self.assertIn("Selected Products\n4", output.getvalue())
        self.assertIn("Portfolio Size\nPASS", output.getvalue())


if __name__ == "__main__":
    unittest.main()
