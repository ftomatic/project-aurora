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


if __name__ == "__main__":
    unittest.main()
