"""Tests for the Aurora content production queue."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_PATH))

from project_aurora.production.production_queue import (  # noqa: E402
    ProductionQueue,
)
from project_aurora.production.queue_item import (  # noqa: E402
    ProductionQueueItem,
    SUPPORTED_CONTENT_TYPES,
    SUPPORTED_PLATFORMS,
    SUPPORTED_STATUSES,
)
from project_aurora.strategy.product_plan import (  # noqa: E402
    BundleItem,
    ProductPlan,
)


def make_strategy() -> ProductPlan:
    return ProductPlan(
        selected_product="Strawberry Birthday Party Printable",
        product_type="Party Printable Bundle",
        collection_name="Summer Strawberry Birthday Collection",
        asset_count=36,
        bundle_structure=(BundleItem(quantity=8, name="invitations"),),
        target_buyer="Parents planning summer birthday parties",
        positioning="Cute cottagecore strawberry printable party bundle",
        expansion_ideas=("Matching thank-you set",),
        estimated_commercial_potential="High",
        production_priority="High",
        ceo_summary="Today the studio should produce...",
    )


class ProductionQueueTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.queue = ProductionQueue(queue_dir=Path(self.temp_dir.name))

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_create_queue_item(self) -> None:
        item = self.queue.create_queue_item(
            product_name="Strawberry Birthday Party Printable",
            product_category="Party Printable Bundle",
            platform="Etsy",
            content_type="product_listing",
            priority="High",
            prompt="Create an Etsy listing.",
            notes="Sample task.",
            item_id="etsy_listing_1",
        )

        self.assertIsInstance(item, ProductionQueueItem)
        self.assertEqual(item.id, "etsy_listing_1")
        self.assertEqual(item.status, "pending")
        self.assertIn(item.platform, SUPPORTED_PLATFORMS)
        self.assertIn(item.content_type, SUPPORTED_CONTENT_TYPES)
        self.assertIn(item.status, SUPPORTED_STATUSES)

    def test_create_queue_from_strategy(self) -> None:
        items = self.queue.create_queue_from_strategy(make_strategy())

        self.assertEqual(len(items), 8)
        self.assertTrue(all(item.status == "pending" for item in items))
        self.assertIn("Etsy", {item.platform for item in items})
        self.assertIn("TikTok", {item.platform for item in items})
        self.assertIn("Instagram", {item.platform for item in items})
        self.assertIn("Pinterest", {item.platform for item in items})
        self.assertIn("Shopify", {item.platform for item in items})

    def test_save_queue_json(self) -> None:
        items = self.queue.create_queue_from_strategy(make_strategy())

        result = self.queue.save_queue(items, queue_name="test_queue")

        self.assertEqual(result.item_count, len(items))
        self.assertTrue(result.path.exists())
        self.assertEqual(result.path.name, "test_queue.json")

    def test_load_queue_json(self) -> None:
        items = self.queue.create_queue_from_strategy(make_strategy())
        self.queue.save_queue(items, queue_name="test_queue")

        loaded_items = self.queue.load_queue(queue_name="test_queue")

        self.assertEqual(len(loaded_items), len(items))
        self.assertEqual(loaded_items[0].product_name, items[0].product_name)
        self.assertEqual(loaded_items[0].platform, items[0].platform)

    def test_filter_pending_items(self) -> None:
        pending_item = self.queue.create_queue_item(
            product_name="Strawberry Birthday Party Printable",
            product_category="Party Printable Bundle",
            platform="Etsy",
            content_type="product_listing",
            priority="High",
            prompt="Create listing.",
            item_id="pending",
        )
        completed_item = self.queue.create_queue_item(
            product_name="Strawberry Birthday Party Printable",
            product_category="Party Printable Bundle",
            platform="Shopify",
            content_type="email_promo",
            priority="High",
            prompt="Create email.",
            status="completed",
            item_id="completed",
        )

        pending_items = self.queue.list_pending(
            (pending_item, completed_item)
        )

        self.assertEqual(pending_items, (pending_item,))

    def test_update_item_status(self) -> None:
        items = self.queue.create_queue_from_strategy(make_strategy())

        updated_items = self.queue.update_status(
            items,
            item_id=items[0].id,
            status="in_progress",
        )

        self.assertEqual(updated_items[0].status, "in_progress")
        self.assertGreater(
            updated_items[0].updated_at,
            items[0].updated_at,
        )

    def test_update_missing_item_raises(self) -> None:
        items = self.queue.create_queue_from_strategy(make_strategy())

        with self.assertRaises(ValueError):
            self.queue.update_status(items, item_id="missing", status="failed")


if __name__ == "__main__":
    unittest.main()
