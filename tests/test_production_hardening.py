"""Tests for Sprint 28 production hardening."""

from __future__ import annotations

import sys
import tempfile
import unittest
from http.client import RemoteDisconnected
from pathlib import Path
from types import SimpleNamespace

from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_PATH))
sys.path.insert(0, str(PROJECT_ROOT))

from project_aurora.integrations.etsy.etsy_taxonomy_resolver import EtsyTaxonomyResolver  # noqa: E402
from project_aurora.integrations.etsy.etsy_upload_manager import (  # noqa: E402
    EtsyUploadManager,
    EtsyUploadPolicy,
)
from project_aurora.merchandising.pricing_engine import PricingEngine  # noqa: E402
from project_aurora.planning.production_queue_manager import ProductionJob  # noqa: E402
from project_aurora.production.merchant_package import MerchantPackage  # noqa: E402
from project_aurora.production.merchant_preflight import MerchantPreflight  # noqa: E402
from project_aurora.production.product_capability_resolver import (  # noqa: E402
    IMAGE_ONLY,
    IMAGE_WITH_SHORT_TEXT,
    TEMPLATE_REQUIRED,
    ProductCapabilityResolver,
)
from project_aurora.seo.seo_engine import SEOEngine  # noqa: E402
from project_aurora.storage.csv_storage import CSVStorage  # noqa: E402
from project_aurora.storage.memory_manager import MemoryManager  # noqa: E402


def job(product_name: str, category: str) -> ProductionJob:
    return ProductionJob(
        id="job-1",
        priority="High",
        product_name=product_name,
        category=category,
        style="Flat Vector",
        seasonal_theme="Evergreen",
        keywords=tuple(product_name.casefold().split()),
        confidence_score=0.9,
        estimated_competition="Low",
        estimated_demand="High",
        estimated_revenue=100,
        demand_score=0.9,
    )


def write_commercial_png(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGBA", (3600, 3600), (255, 0, 0, 255)).save(
        path,
        format="PNG",
        dpi=(300, 300),
    )


class ProductionHardeningTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base_path = Path(self.temp_dir.name)
        self.memory = MemoryManager(CSVStorage(base_path=self.base_path / "memory"))

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_taxonomy_resolves_different_product_types(self) -> None:
        resolver = EtsyTaxonomyResolver()

        clipart = resolver.resolve(product_name="Woodland Animals Clipart", product_type="clipart", category="clipart")
        paper = resolver.resolve(product_name="Winter Woodland Digital Paper", product_type="digital paper", category="digital paper")
        wall = resolver.resolve(product_name="Mother's Day Floral Art", product_type="wall art", category="wall art")
        sticker = resolver.resolve(product_name="Spring Garden Sticker Sheet", product_type="sticker sheet", category="sticker sheet")

        self.assertTrue(clipart.resolved)
        self.assertTrue(paper.resolved)
        self.assertTrue(wall.resolved)
        self.assertTrue(sticker.resolved)
        self.assertGreater(len({clipart.taxonomy_id, paper.taxonomy_id, wall.taxonomy_id, sticker.taxonomy_id}), 1)

    def test_unknown_taxonomy_blocks_resolution(self) -> None:
        result = EtsyTaxonomyResolver().resolve(
            product_name="Unsupported Mystery Product",
            product_type="unknown",
            category="unknown",
        )

        self.assertFalse(result.resolved)
        self.assertIn("No verified taxonomy", result.resolution_reason)

    def test_pricing_varies_and_is_not_global_199(self) -> None:
        engine = PricingEngine()

        clipart = engine.resolve_price(
            product_name="Woodland Animals Clipart",
            product_type="clipart",
            category="clipart",
            bundle_size=10,
            image_count=10,
            commercial_license=True,
            competition_level="Low",
            demand_score=0.9,
            confidence_score=0.9,
        )
        wall = engine.resolve_price(
            product_name="Nursery Bunny Wall Art",
            product_type="wall art",
            category="wall art",
            bundle_size=4,
            image_count=4,
            commercial_license=True,
            competition_level="Medium",
            demand_score=0.8,
            confidence_score=0.8,
        )

        self.assertNotEqual(clipart.launch_price, wall.launch_price)
        self.assertNotEqual(clipart.launch_price, 1.99)
        self.assertEqual(clipart.source, "CONFIGURED_FALLBACK")

    def test_capability_blocks_long_text_games_and_allows_visual_products(self) -> None:
        resolver = ProductCapabilityResolver()

        bridal = resolver.resolve("Boho Bridal Shower Games", "bridal shower printable", "bridal shower printable")
        wall = resolver.resolve("Classroom Alphabet Wall Art", "teacher wall art", "teacher wall art")
        clipart = resolver.resolve("Autumn Mushroom Clipart", "clipart", "clipart")
        short = resolver.resolve("Hello Label", "gift tags", "gift tags")

        self.assertEqual(bridal.mode, TEMPLATE_REQUIRED)
        self.assertFalse(bridal.supported)
        self.assertEqual(wall.mode, IMAGE_ONLY)
        self.assertTrue(clipart.supported)
        self.assertIn(short.mode, {IMAGE_ONLY, IMAGE_WITH_SHORT_TEXT})

    def test_upload_manager_retries_remote_disconnect_then_success(self) -> None:
        path = self.base_path / "file.png"
        path.write_bytes(b"png")
        calls = {"count": 0}

        def uploader() -> dict[str, str]:
            calls["count"] += 1
            if calls["count"] == 1:
                raise RemoteDisconnected("remote end closed connection without response")
            return {"listing_file_id": "file-1"}

        waits: list[float] = []
        manager = EtsyUploadManager(
            memory=self.memory,
            policy=EtsyUploadPolicy(max_attempts=4, backoff_seconds=(0, 0, 0), delay_between_files_seconds=0),
            sleeper=lambda seconds: waits.append(seconds),
        )
        checkpoint = manager.upload_one(
            listing_id="listing-1",
            job_id="job-1",
            upload_type="digital_file",
            file_path=path,
            rank=1,
            uploader=uploader,
        )

        self.assertEqual(checkpoint.status, "SUCCESS")
        self.assertEqual(calls["count"], 2)
        self.assertEqual(waits, [0])
        self.assertTrue(self.memory.list_records("etsy_upload_checkpoints"))

    def test_upload_manager_fails_after_repeated_disconnects(self) -> None:
        path = self.base_path / "file.png"
        path.write_bytes(b"png")
        manager = EtsyUploadManager(
            memory=self.memory,
            policy=EtsyUploadPolicy(max_attempts=2, backoff_seconds=(0,), delay_between_files_seconds=0),
            sleeper=lambda _seconds: None,
        )

        checkpoint = manager.upload_one(
            listing_id="listing-1",
            job_id="job-1",
            upload_type="digital_file",
            file_path=path,
            rank=1,
            uploader=lambda: (_ for _ in ()).throw(RemoteDisconnected("remote closed")),
        )

        self.assertEqual(checkpoint.status, "FAILED")
        self.assertEqual(checkpoint.attempts, 2)

    def test_merchant_preflight_blocks_missing_taxonomy_and_passes_valid_package(self) -> None:
        current_job = job("Autumn Mushroom Clipart", "clipart")
        seo = SEOEngine().build_package(
            {
                "job_id": current_job.id,
                "product_name": current_job.product_name,
                "product_type": current_job.category,
                "target_buyer": "crafters",
            }
        )
        final_dir = self.base_path / "final_product_images"
        for index in range(1, 5):
            write_commercial_png(final_dir / f"autumn_mushroom_{index:02d}.png")
        merchant = MerchantPackage(
            job_id=current_job.id,
            product_name=current_job.product_name,
            product_type=current_job.category,
            capability_mode=IMAGE_ONLY,
            etsy_taxonomy_id=6844,
            etsy_taxonomy_path="Craft Supplies & Tools > Digital > Clip Art & Image Files",
            taxonomy_confidence=92,
            price_range=(3.99, 5.99, 8.99),
            recommended_price=8.49,
            launch_price=7.99,
            pricing_reason="configured fallback",
            pricing_source="CONFIGURED_FALLBACK",
            selected_style="Storybook Watercolor",
            style_confidence=90,
            composition="isolated elements",
            background="transparent",
            product_capability_result={"supported": True},
        )

        passed = MerchantPreflight().run(
            job=current_job,
            merchant_package=merchant,
            seo_package=seo,
            final_images_dir=final_dir,
        )
        failed = MerchantPreflight().run(
            job=current_job,
            merchant_package=MerchantPackage(
                **{**merchant.to_dict(), "etsy_taxonomy_id": 0, "generated_at": merchant.generated_at}
            ),
            seo_package=seo,
            final_images_dir=final_dir,
        )

        self.assertEqual(passed.status, "READY_FOR_ETSY_DRAFT")
        self.assertEqual(failed.status, "PREFLIGHT_FAILED")


if __name__ == "__main__":
    unittest.main()
