"""Tests for Sprint 28 production hardening."""

from __future__ import annotations

import sys
import tempfile
import unittest
import zipfile
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
from project_aurora.merchandising.pricing_engine import FIXED_DEFAULT, PricingEngine  # noqa: E402
from project_aurora.planning.production_queue_manager import (  # noqa: E402
    READY,
    ProductionJob,
    ProductionQueueManager,
)
from project_aurora.production.merchant_package import MerchantPackage  # noqa: E402
from project_aurora.production.merchant_preflight import MerchantPreflight  # noqa: E402
from project_aurora.production.merchant_specification import MerchantSpecification  # noqa: E402
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


def write_digital_paper_package(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    files: list[Path] = []
    for index in range(1, 13):
        path = directory / f"woodland_digital_paper_{index:02d}.jpg"
        Image.new("RGB", (3600, 3600), (index, 120, 80)).save(
            path,
            format="JPEG",
            dpi=(300, 300),
        )
        files.append(path)
    preview = directory / "collage_preview.jpg"
    Image.new("RGB", (1800, 1200), (200, 200, 180)).save(preview, format="JPEG", dpi=(300, 300))
    with zipfile.ZipFile(directory / "woodland_digital_paper.zip", "w") as archive:
        for path in files:
            archive.write(path, arcname=path.name)


def spec(
    category: str,
    *,
    bundle_size: int = 4,
    packaging: str = "NONE",
    preview_requirements: tuple[str, ...] = (),
    qa_requirements: tuple[str, ...] = (),
    thumbnail_rules: tuple[str, ...] = (),
) -> MerchantSpecification:
    return MerchantSpecification(
        category=category,
        physical_dimensions="digital",
        pixel_dimensions=None,
        dpi=300,
        file_formats=("PNG",),
        bundle_size=bundle_size,
        preview_requirements=preview_requirements,
        packaging=packaging,
        thumbnail_rules=thumbnail_rules,
        etsy_expectations=("digital download",),
        qa_requirements=qa_requirements,
    )


class FakeSpecificationLibrary:
    def __init__(self, merchant_spec: MerchantSpecification) -> None:
        self._merchant_spec = merchant_spec

    def resolve(self, category: str, product_name: str = "") -> MerchantSpecification:
        return self._merchant_spec


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

    def test_pricing_uses_phase_one_fixed_default(self) -> None:
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

        self.assertEqual(clipart.launch_price, 2.49)
        self.assertEqual(wall.launch_price, 2.49)
        self.assertEqual(clipart.recommended_price, 2.49)
        self.assertEqual(clipart.source, FIXED_DEFAULT)

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

    def test_digital_paper_capability_requires_complete_assets(self) -> None:
        resolver = ProductCapabilityResolver()
        missing = resolver.resolve(
            "Winter Woodland Digital Paper",
            "digital paper",
            "digital paper",
            assets_dir=self.base_path / "missing_assets",
        )
        asset_dir = self.base_path / "digital_paper_assets"
        write_digital_paper_package(asset_dir)
        complete = resolver.resolve(
            "Winter Woodland Digital Paper",
            "digital paper",
            "digital paper",
            assets_dir=asset_dir,
        )

        self.assertFalse(missing.supported)
        self.assertTrue(missing.requires_zip_package)
        self.assertEqual(missing.required_deliverable_count, 12)
        self.assertFalse(complete.supported)
        self.assertTrue(complete.requires_zip_package)

    def test_transformed_digital_illustration_queue_job_is_not_blocked_by_research_origin(self) -> None:
        queue = ProductionQueueManager(queue_path=self.base_path / "queue.json")

        current_job = queue.add_job(
            priority="High",
            product_name="Winter Woodland Digital Illustration Collection",
            category="digital illustration collection",
            style="Watercolor",
            seasonal_theme="Winter",
            keywords=("winter", "woodland", "digital paper"),
            confidence_score=0.9,
            estimated_competition="Low",
            estimated_demand="High",
            estimated_revenue=100,
            status=READY,
            original_product_name="Winter Woodland Digital Paper",
            original_product_type="digital paper",
            required_image_count=4,
        )

        self.assertEqual(current_job.status, READY)
        self.assertEqual(queue.next_ready_job(), current_job)

    def test_capability_allows_supported_categories_when_requirements_fit(self) -> None:
        for product_name, category in (
            ("Teacher Clipart", "clipart"),
            ("Simple Digital Paper", "digital paper"),
            ("Weekly Planner Pages", "planner"),
            ("Victorian Botanical Journal Kit", "junk journal"),
        ):
            with self.subTest(product_name=product_name):
                resolver = ProductCapabilityResolver(
                    specification_library=FakeSpecificationLibrary(
                        spec(category.title(), bundle_size=20, packaging="NONE")
                    )
                )
                result = resolver.resolve(product_name, category, category)

                self.assertTrue(result.supported)
                self.assertEqual(result.required_deliverable_count, 20)
                self.assertFalse(result.requires_zip_package)

    def test_capability_skips_zip_required_product_before_paid_generation(self) -> None:
        resolver = ProductCapabilityResolver(
            specification_library=FakeSpecificationLibrary(
                spec("Clipart", bundle_size=12, packaging="ZIP")
            )
        )

        result = resolver.resolve("Teacher Clipart", "clipart", "clipart")

        self.assertFalse(result.supported)
        self.assertTrue(result.requires_zip_package)
        self.assertEqual(result.required_deliverable_count, 12)
        self.assertIn("ZIP package", result.reason)

    def test_capability_skips_product_with_more_than_twenty_deliverables(self) -> None:
        resolver = ProductCapabilityResolver(
            specification_library=FakeSpecificationLibrary(
                spec("Clipart", bundle_size=21, packaging="NONE")
            )
        )

        result = resolver.resolve("Mega Clipart", "clipart", "clipart")

        self.assertFalse(result.supported)
        self.assertEqual(result.required_deliverable_count, 21)
        self.assertIn("current limit is 20", result.reason)

    def test_capability_skips_sticker_sheet_when_layout_template_is_missing(self) -> None:
        resolver = ProductCapabilityResolver(
            specification_library=FakeSpecificationLibrary(
                spec(
                    "Stickers",
                    bundle_size=8,
                    packaging="NONE",
                    preview_requirements=("sticker sheet preview",),
                    qa_requirements=("sheet preview",),
                )
            )
        )

        result = resolver.resolve(
            "Spring Garden Sticker Sheet",
            "sticker sheet",
            "sticker sheet",
        )

        self.assertFalse(result.supported)
        self.assertTrue(result.requires_layout_engine)
        self.assertIn("layout/template engine", result.reason)

    def test_capability_allows_sticker_sheet_when_layout_template_exists(self) -> None:
        resolver = ProductCapabilityResolver(
            specification_library=FakeSpecificationLibrary(
                spec(
                    "Stickers",
                    bundle_size=8,
                    packaging="ZIP",
                    preview_requirements=("sticker sheet preview",),
                    qa_requirements=("sheet preview",),
                )
            )
        )
        assets_dir = self.base_path / "sticker_assets"
        assets_dir.mkdir()
        (assets_dir / "sticker_sheet_template.json").write_text("{}", encoding="utf-8")

        result = resolver.resolve(
            "Planner School Icons",
            "sticker sheet",
            "sticker sheet",
            assets_dir=assets_dir,
        )

        self.assertTrue(result.supported)
        self.assertTrue(result.requires_zip_package)
        self.assertEqual(result.required_deliverable_count, 8)

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
        current_job = job("Winter Woodland Digital Paper", "digital paper")
        seo = SEOEngine().build_package(
            {
                "job_id": current_job.id,
                "product_name": current_job.product_name,
                "product_type": current_job.category,
                "target_buyer": "crafters",
            }
        )
        final_dir = self.base_path / "final_product_images"
        write_digital_paper_package(final_dir)
        merchant = MerchantPackage(
            job_id=current_job.id,
            product_name=current_job.product_name,
            product_type=current_job.category,
            capability_mode=IMAGE_ONLY,
            etsy_taxonomy_id=5678,
            etsy_taxonomy_path="Craft Supplies & Tools > Paper > Digital Paper",
            taxonomy_confidence=92,
            price_range=(2.49, 2.49, 2.49),
            recommended_price=2.49,
            launch_price=2.49,
            pricing_reason="fixed default",
            pricing_source=FIXED_DEFAULT,
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
        self.assertEqual(passed.status, "READY_FOR_ETSY_DRAFT")
        self.assertEqual(passed.price, 2.49)
        self.assertEqual(passed.pricing_source, FIXED_DEFAULT)
        rendered = passed.render()
        self.assertIn("Pricing Source\nFIXED_DEFAULT", rendered)
        self.assertIn("Listing Price\n2.49", rendered)
        self.assertIn("Launch Price\n2.49", rendered)
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
