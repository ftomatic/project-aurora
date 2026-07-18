"""Tests for Aurora Collection Intelligence."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_PATH))

from project_aurora.collections.collection_engine import (  # noqa: E402
    CollectionDiscovery,
    CollectionIntelligenceEngine,
    CollectionProductPlanner,
    render_collection_merchant_report,
)
from project_aurora.collections.collection_memory import CollectionMemory  # noqa: E402
from project_aurora.collections.collection_settings import CollectionSettings  # noqa: E402
from project_aurora.storage.csv_storage import CSVStorage  # noqa: E402
from project_aurora.storage.memory_manager import MemoryManager  # noqa: E402


class CollectionIntelligenceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.memory = MemoryManager(CSVStorage(base_path=Path(self.temp_dir.name)))

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_collection_selected(self) -> None:
        plan = CollectionIntelligenceEngine(memory=self.memory).run()

        self.assertTrue(plan.collection.name)
        self.assertGreaterEqual(plan.score.total, 80)
        self.assertIn("collection", plan.why_chosen.casefold())

    def test_five_coordinated_products(self) -> None:
        plan = CollectionIntelligenceEngine(memory=self.memory).run()

        self.assertEqual(len(plan.products), 5)
        self.assertEqual(len({product.subject for product in plan.products}), 5)
        self.assertTrue(
            all(plan.collection.name in product.product_name for product in plan.products)
        )

    def test_shared_style_across_collection(self) -> None:
        plan = CollectionIntelligenceEngine(memory=self.memory).run()

        self.assertTrue(plan.art_direction.master_style)
        self.assertTrue(plan.art_direction.palette)
        self.assertTrue(plan.art_direction.rendering)
        self.assertTrue(
            any(plan.art_direction.master_style in rule for rule in plan.art_direction.consistency_rules)
        )

    def test_cross_sell_generated(self) -> None:
        plan = CollectionIntelligenceEngine(memory=self.memory).run()

        self.assertTrue(plan.cross_sell.related_products)
        self.assertTrue(plan.cross_sell.collection_links)
        self.assertTrue(plan.cross_sell.bundle_suggestions)
        self.assertTrue(plan.cross_sell.future_collection_ideas)
        self.assertIn(
            f"Part of Collection: {plan.collection.name}",
            plan.cross_sell.collection_links,
        )

    def test_collection_memory_prevents_duplicate_score(self) -> None:
        collection_memory = CollectionMemory(memory=self.memory)
        engine = CollectionIntelligenceEngine(
            memory=self.memory,
            collection_memory=collection_memory,
        )
        first = engine.run()
        duplicate_score = collection_memory.duplicate_score(first.collection.name)

        self.assertEqual(duplicate_score, 100)
        self.assertTrue(self.memory.list_records("collection_memory"))

    def test_discovery_returns_known_collection_opportunities(self) -> None:
        opportunities = CollectionDiscovery().discover()
        names = {opportunity.name for opportunity in opportunities}

        self.assertIn("Woodland Nursery", names)
        self.assertIn("French Cottage Kitchen", names)
        self.assertIn("Dark Academia Library", names)

    def test_settings_loads_config(self) -> None:
        settings = CollectionSettings.from_file(PROJECT_ROOT / "config" / "collections.yaml")

        self.assertEqual(settings.collection_size, 5)
        self.assertFalse(settings.allow_single_products)
        self.assertGreaterEqual(settings.minimum_collection_score, 80)

    def test_collection_blueprint_created_correctly(self) -> None:
        plan = CollectionIntelligenceEngine(memory=self.memory).run()

        self.assertIsNotNone(plan.blueprint)
        self.assertEqual(plan.blueprint.theme_name, plan.collection.name)
        self.assertEqual(plan.blueprint.target_audience, plan.collection.audience)
        self.assertTrue(plan.blueprint.primary_colors)
        self.assertTrue(plan.blueprint.typography_style)
        self.assertIn(plan.collection.name, plan.blueprint.visual_identity)
        self.assertIn(plan.collection.audience, plan.blueprint.commercial_positioning)

    def test_expansion_suggestions_generated(self) -> None:
        woodland = next(
            item for item in CollectionDiscovery().discover() if item.name == "Woodland Nursery"
        )

        products = CollectionProductPlanner(collection_size=3).plan_all(woodland)
        subjects = {product.subject for product in products}
        product_types = {product.product_type for product in products}

        self.assertIn("Clipart Bundle", subjects)
        self.assertIn("Digital Paper Pack", subjects)
        self.assertIn("Nursery Wall Art", subjects)
        self.assertIn("Baby Shower Invitation", subjects)
        self.assertIn("clipart", product_types)
        self.assertIn("digital paper", product_types)
        self.assertIn("wall art", product_types)
        self.assertIn("party printable", product_types)

    def test_no_duplicate_collection_products(self) -> None:
        plan = CollectionIntelligenceEngine(memory=self.memory).run()
        product_names = [product.product_name for product in plan.products]

        self.assertEqual(len(product_names), len(set(product_names)))

    def test_roadmap_updates_correctly(self) -> None:
        plan = CollectionIntelligenceEngine(memory=self.memory).run()

        self.assertIsNotNone(plan.roadmap)
        self.assertGreater(len(plan.roadmap.products_planned), len(plan.products))
        self.assertEqual(
            tuple(product.product_name for product in plan.products),
            plan.roadmap.products_completed,
        )
        self.assertTrue(plan.roadmap.products_remaining)
        self.assertGreater(plan.roadmap.estimated_collection_revenue, 0)

    def test_merchant_report_generated(self) -> None:
        plan = CollectionIntelligenceEngine(memory=self.memory).run()
        report = render_collection_merchant_report(plan)

        self.assertIn("Today's Collection", report)
        self.assertIn(plan.collection.name, report)
        self.assertIn("Collection Score", report)
        self.assertIn("Today's Releases", report)
        self.assertIn("Remaining Opportunities", report)
        self.assertIn("Shop Health", report)

    def test_collection_score_contains_sprint35_dimensions(self) -> None:
        plan = CollectionIntelligenceEngine(memory=self.memory).run()
        saved = self.memory.load_record("collection_plans", plan.collection.name.casefold().replace(" ", "_"))
        score = saved["collection_score"]

        self.assertIn("commercial_potential", score)
        self.assertIn("portfolio_fit", score)
        self.assertIn("expansion_potential", score)
        self.assertIn("cross_sell_potential", score)
        self.assertIn("brand_consistency", score)
        self.assertIn("revenue_potential", score)
        self.assertGreaterEqual(score["total"], 80)

    def test_product_linking_generated(self) -> None:
        plan = CollectionIntelligenceEngine(memory=self.memory).run()

        self.assertTrue(plan.cross_sell.related_products)
        self.assertTrue(plan.cross_sell.matching_products)
        self.assertTrue(plan.cross_sell.matching_collections)
        self.assertTrue(all(plan.collection.name in link for link in plan.cross_sell.collection_links))

    def test_shop_health_tracks_collection_state(self) -> None:
        plan = CollectionIntelligenceEngine(memory=self.memory).run()

        self.assertIsNotNone(plan.shop_health)
        self.assertGreaterEqual(plan.shop_health.collections_active, 1)
        self.assertTrue(plan.shop_health.largest_collection)
        self.assertIn(plan.shop_health.collection_diversity, {"Growing", "Healthy"})


if __name__ == "__main__":
    unittest.main()
