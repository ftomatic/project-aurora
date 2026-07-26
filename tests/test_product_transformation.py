"""Tests for transforming research opportunities into production-safe products."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_PATH))
sys.path.insert(0, str(PROJECT_ROOT))

from project_aurora.integrations.etsy.etsy_taxonomy_resolver import EtsyTaxonomyResolver  # noqa: E402
from project_aurora.planning.product_transformer import (  # noqa: E402
    TRANSFORMED_IMAGE_COUNT,
    TRANSFORMED_PRODUCT_TYPE,
    ProductTransformationEngine,
)
from project_aurora.planning.production_queue_manager import READY, ProductionQueueManager  # noqa: E402
from project_aurora.portfolio.atlas_portfolio_manager import AtlasPortfolioPlan, BusinessDecision  # noqa: E402
from project_aurora.production.product_capability_resolver import ProductCapabilityResolver  # noqa: E402
from project_aurora.research.market_opportunity import MarketOpportunity  # noqa: E402
from project_aurora.seo.seo_engine import SEOEngine  # noqa: E402
from scripts.run_research_planner import handoff_to_forge  # noqa: E402


def opportunity(
    name: str,
    product_type: str,
    *,
    style: str = "Vintage Botanical",
    niche: str = "Crafts",
    audience: str = "crafters",
    season: str = "Evergreen",
    confidence: float = 92,
) -> MarketOpportunity:
    return MarketOpportunity(
        keyword=name,
        primary_niche=niche,
        subcategory="Research",
        target_audience=audience,
        season=season,
        product_type=product_type,
        recommended_artistic_style=style,
        trend_score=92,
        competition_score=35,
        commercial_potential=90,
        confidence=confidence,
        research_sources=("Mock Research",),
    )


def plan_with(opportunities: tuple[MarketOpportunity, ...]) -> AtlasPortfolioPlan:
    decisions = tuple(
        BusinessDecision(
            product=item.keyword,
            business_reason="Mock reason",
            trend_summary="Mock trend",
            target_customer=item.target_audience,
            competition="Low",
            demand="High",
            commercial_opportunity="High",
            expected_search_intent="Digital download",
            recommended_price=1.99,
            recommended_bundle_opportunities=("4 PNG illustrations",),
            suggested_boards=("Crafts",),
            suggested_instagram_theme=item.recommended_artistic_style,
            confidence_score=item.confidence,
            research_sources=item.research_sources,
            reason_selected="Selected",
        )
        for item in opportunities
    )
    return AtlasPortfolioPlan(
        selected=opportunities,
        rejected=(),
        decisions=decisions,
        average_confidence=92,
        quality_gate_passed=True,
        quality_gate={},
        constraint_relaxations=(),
        selection_failure_reasons=(),
        provider_status=(),
    )


class ProductTransformationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.transformer = ProductTransformationEngine()

    def test_digital_paper_transforms_to_four_image_collection(self) -> None:
        result = self.transformer.transform(
            opportunity("Vintage Floral Digital Paper Pack", "digital paper")
        )

        self.assertEqual(result.production_product_type, TRANSFORMED_PRODUCT_TYPE)
        self.assertEqual(result.required_image_count, TRANSFORMED_IMAGE_COUNT)
        self.assertTrue(result.requires_zip_package)
        self.assertFalse(result.requires_template_engine)
        self.assertFalse(result.requires_layout_engine)
        self.assertTrue(result.eligible)
        self.assertIn("Digital Illustration Collection", result.production_product_name)
        self.assertNotIn("Paper Pack", result.production_product_name)

    def test_junk_journal_transforms_to_four_image_collection(self) -> None:
        result = self.transformer.transform(
            opportunity("Woodland Junk Journal Kit", "junk journal")
        )

        self.assertEqual(result.production_product_type, TRANSFORMED_PRODUCT_TYPE)
        self.assertIn("Digital Illustration Collection", result.production_product_name)
        self.assertNotIn("Junk Journal", result.production_product_name)
        self.assertTrue(result.requires_zip_package)
        self.assertTrue(result.eligible)

    def test_sticker_sheet_transforms_to_individual_illustrations(self) -> None:
        result = self.transformer.transform(
            opportunity("Cute Animal Sticker Sheet", "sticker sheet")
        )

        self.assertEqual(result.required_image_count, 4)
        self.assertIn("Sticker Illustration Set", result.production_product_name)
        self.assertNotIn("Sheet", result.production_product_name)
        self.assertFalse(result.requires_layout_engine)
        self.assertTrue(result.eligible)

    def test_scrapbook_paper_transforms_without_large_pack_claim(self) -> None:
        result = self.transformer.transform(
            opportunity("Botanical Scrapbook Paper Pack", "scrapbook paper")
        )
        seo = SEOEngine().build_package(
            {
                "job_id": "job-1",
                "product_name": result.production_product_name,
                "product_type": result.production_product_type,
                "target_buyer": "crafters",
                "style": result.production_style,
            }
        )

        combined = f"{seo.title}\n{seo.description}".casefold()
        self.assertNotIn("12 seamless", combined)
        self.assertNotIn("paper pack", combined)
        self.assertNotIn("sticker sheet", combined)
        self.assertIn("4 high-quality", combined)

    def test_transformed_taxonomy_and_capability_are_production_safe(self) -> None:
        result = self.transformer.transform(
            opportunity("Seasonal Planner Kit", "planner kit")
        )
        capability = ProductCapabilityResolver().resolve(
            result.production_product_name,
            result.production_product_type,
            result.production_product_type,
        )
        taxonomy = EtsyTaxonomyResolver().resolve(
            product_name=result.production_product_name,
            product_type=result.production_product_type,
            category=result.production_product_type,
        )

        self.assertTrue(capability.supported)
        self.assertEqual(capability.required_deliverable_count, 4)
        self.assertTrue(capability.requires_zip_package)
        self.assertFalse(capability.requires_layout_engine)
        self.assertTrue(taxonomy.resolved)
        self.assertEqual(taxonomy.validated_product_type, "digital illustration collection")

    def test_daily_handoff_creates_five_ready_whimsical_safe_jobs(self) -> None:
        opportunities = (
            opportunity("Woodland Fox Digital Paper Pack", "digital paper", style="Watercolor", niche="Nursery"),
            opportunity("Cottage Mouse Junk Journal Kit", "junk journal", style="Storybook", niche="Journals"),
            opportunity("Vintage Floral Scrapbook Paper Pack", "scrapbook paper", niche="Botanical"),
            opportunity("Autumn Pumpkin Planner Kit", "planner kit", season="Fall", niche="Seasonal"),
            opportunity("Boho Teacher Sticker Sheet", "sticker sheet", niche="Teacher", audience="teachers"),
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            queue = ProductionQueueManager(queue_path=Path(temp_dir) / "queue.json")

            created = handoff_to_forge(plan_with(opportunities), queue)
            jobs = queue.list_jobs()

        self.assertEqual(created, 5)
        self.assertEqual(len(jobs), 5)
        self.assertTrue(all(job.status == READY for job in jobs))
        self.assertTrue(all(job.category == TRANSFORMED_PRODUCT_TYPE for job in jobs))
        self.assertTrue(all(job.required_image_count == 4 for job in jobs))
        self.assertTrue(all(job.requires_zip_package for job in jobs))
        self.assertTrue(all(not job.requires_template_engine for job in jobs))
        self.assertTrue(all(not job.requires_layout_engine for job in jobs))
        self.assertGreaterEqual(sum(job.whimsical_batch_designation for job in jobs), 2)
        self.assertIsNotNone(queue.next_ready_job())


if __name__ == "__main__":
    unittest.main()
