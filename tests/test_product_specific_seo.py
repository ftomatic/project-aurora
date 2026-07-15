"""Regression tests for product-specific Etsy SEO tags."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(SRC_PATH))
sys.path.insert(0, str(PROJECT_ROOT))

from project_aurora.integrations.etsy.etsy_config import EtsyConfig  # noqa: E402
from project_aurora.integrations.etsy.etsy_listing_mapper import (  # noqa: E402
    EtsyListingMapper,
)
from project_aurora.listing.listing_package import (  # noqa: E402
    READY_FOR_ETSY_DRAFT,
    ListingPackage,
)
from project_aurora.planning.production_queue_manager import ProductionJob  # noqa: E402
from project_aurora.production.product_factory import (  # noqa: E402
    DefaultProductFactoryStageRunner,
    ProductFactoryPaths,
)
from project_aurora.production.production_report import ProductionReport  # noqa: E402
from project_aurora.seo.seo_audit import audit_listing_seo  # noqa: E402
from project_aurora.storage.csv_storage import CSVStorage  # noqa: E402
from project_aurora.storage.memory_manager import MemoryManager  # noqa: E402
from scripts.fix_existing_etsy_tags import repair_existing_etsy_tags  # noqa: E402


PRODUCTS = (
    ("job-spring", "Spring Bunny Nursery Art", "wall art"),
    ("job-wildflower", "Wildflower Wedding Invitation", "party printable"),
    ("job-moody", "Moody Dark Academia Prints", "wall art"),
)
FIVE_PRODUCTS = (
    *PRODUCTS,
    ("job-pastel", "Pastel Baby Animal Clipart", "clipart"),
    ("job-new-year", "New Year Planner Stickers", "sticker sheet"),
)


class FakePatchClient:
    def __init__(self, drafts: tuple[dict[str, object], ...] = ()) -> None:
        self.drafts = drafts
        self.calls: list[tuple[str, dict[str, object]]] = []

    def list_shop_draft_listings(self) -> tuple[dict[str, object], ...]:
        return self.drafts

    def update_listing_fields(self, listing_id: str, fields: dict[str, object]) -> dict[str, object]:
        self.calls.append((listing_id, fields))
        return {"listing_id": listing_id, **fields}


class ProductSpecificSEOTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base_path = Path(self.temp_dir.name)
        self.memory = MemoryManager(CSVStorage(base_path=self.base_path / "memory"))
        self.runner = DefaultProductFactoryStageRunner(
            memory=self.memory,
            etsy_config=EtsyConfig(mode="mock"),
            paths=ProductFactoryPaths(jobs_dir=self.base_path / "jobs"),
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def job(self, job_id: str, product_name: str, category: str) -> ProductionJob:
        return ProductionJob(
            id=job_id,
            priority="High",
            product_name=product_name,
            category=category,
            style="Storybook Watercolor",
            seasonal_theme="Evergreen",
            keywords=tuple(product_name.casefold().split()),
            confidence_score=0.9,
            estimated_competition="Low",
            estimated_demand="High",
            estimated_revenue=120,
        )

    def write_final_images(self, job: ProductionJob) -> tuple[str, ...]:
        final_dir = self.runner.job_paths(job).final_images_dir
        final_dir.mkdir(parents=True, exist_ok=True)
        paths: list[str] = []
        for index in range(1, 5):
            path = final_dir / f"{job.id}_{index:02d}.png"
            Image.new("RGBA", (3600, 3600), (255, index, 0, 255)).save(
                path,
                format="PNG",
                dpi=(300, 300),
            )
            paths.append(str(path))
        return tuple(paths)

    def save_verified_report(
        self,
        job: ProductionJob,
        listing_id: str,
        write_seo: bool = True,
    ) -> None:
        package = self.runner.generate_seo(job) if write_seo else None
        report = ProductionReport(
            job_id=job.id,
            product=job.product_name,
            style=job.style,
            draft_id=listing_id,
            images=4,
            downloads=4,
            time=1,
            success=True,
            job_paths=self.runner.job_paths(job).to_dict(),
            metadata={
                "seo_generation": {"tags": list(package.tags)}
                if package is not None
                else {}
            },
        )
        if not write_seo:
            seo_path = self.runner.job_paths(job).job_root / "seo" / "seo_package.json"
            if seo_path.exists():
                seo_path.unlink()
        self.memory.save_record("production_reports", job.id, report.to_dict())

    def test_three_products_receive_distinct_job_specific_tags(self) -> None:
        packages = []
        for job_id, product_name, category in PRODUCTS:
            packages.append(self.runner.generate_seo(self.job(job_id, product_name, category)))

        tag_sets = [package.tags for package in packages]

        self.assertTrue(all(len(tags) == 13 for tags in tag_sets))
        self.assertEqual(len({tuple(tags) for tags in tag_sets}), 3)
        for package, (job_id, product_name, _category) in zip(packages, PRODUCTS):
            self.assertEqual(package.job_id, job_id)
            self.assertEqual(package.product_name, product_name)
            seo_path = self.runner.job_paths(
                self.job(job_id, product_name, _category)
            ).job_root / "seo" / "seo_package.json"
            self.assertTrue(seo_path.exists())

    def test_etsy_payload_receives_correct_job_specific_tags(self) -> None:
        job = self.job(*PRODUCTS[1])
        files = self.write_final_images(job)
        package = self.runner.generate_seo(job)
        listing = ListingPackage(
            product_name=job.product_name,
            collection_name=job.product_name,
            listing_status=READY_FOR_ETSY_DRAFT,
            seo_package_id=job.id,
            prompt_package_id=job.id,
            approved_mockup_files=files,
            approved_generated_image_files=files,
            is_digital_download=True,
            price=1.99,
        )

        payload = EtsyListingMapper().map_to_draft(
            listing_package=listing,
            seo_package=package,
            config=EtsyConfig(mode="mock"),
        )

        self.assertEqual(payload.tags, package.tags)
        self.assertIn("wildflower", payload.tags)
        self.assertNotIn("spring bunny", payload.tags)

    def test_restart_loads_current_job_seo_not_another_job(self) -> None:
        first = self.job(*PRODUCTS[0])
        second = self.job(*PRODUCTS[2])
        first_package = self.runner.generate_seo(first)
        second_package = self.runner.generate_seo(second)

        restarted = DefaultProductFactoryStageRunner(
            memory=self.memory,
            etsy_config=EtsyConfig(mode="mock"),
            paths=ProductFactoryPaths(jobs_dir=self.base_path / "jobs"),
        )
        loaded = restarted.generate_seo(second)

        self.assertEqual(loaded.tags, second_package.tags)
        self.assertNotEqual(loaded.tags, first_package.tags)

    def test_mismatched_seo_package_fails_before_etsy_draft(self) -> None:
        spring = self.job(*PRODUCTS[0])
        moody = self.job(*PRODUCTS[2])
        wrong_package = self.runner.generate_seo(spring)
        self.write_final_images(moody)

        with self.assertRaises(RuntimeError):
            self.runner.create_etsy_draft(moody, wrong_package)

    def test_audit_and_repair_patch_only_tags_for_five_current_drafts(self) -> None:
        jobs = [self.job(*product) for product in FIVE_PRODUCTS]
        for index, job in enumerate(jobs, start=1):
            self.save_verified_report(job, f"listing-{index}")

        audit = audit_listing_seo(self.memory)
        client = FakePatchClient(
            tuple(
                {
                    "listing_id": f"listing-{index}",
                    "state": "draft",
                    "tags": ["old tag"],
                }
                for index in range(1, 6)
            )
        )
        output = StringIO()
        with redirect_stdout(output):
            report = repair_existing_etsy_tags(
                self.memory,
                client,  # type: ignore[arg-type]
                input_fn=lambda _prompt: "FIX 5 TAGS",
            )

        self.assertEqual(len(audit), 5)
        self.assertEqual(report["status"], "SUCCESS")
        self.assertEqual(report["drafts_found"], 5)
        self.assertEqual(report["eligible"], 5)
        self.assertIn("Drafts Found\n5", output.getvalue())
        self.assertIn("Drafts Eligible for Tag Repair\n5", output.getvalue())
        self.assertEqual(len(client.calls), 5)
        for _listing_id, fields in client.calls:
            self.assertEqual(tuple(fields.keys()), ("tags",))
            self.assertEqual(len(fields["tags"]), 13)

    def test_published_listing_is_skipped_before_patch(self) -> None:
        jobs = [self.job(*product) for product in FIVE_PRODUCTS]
        for index, job in enumerate(jobs, start=1):
            self.save_verified_report(job, f"listing-{index}")
        drafts = tuple(
            {
                "listing_id": f"listing-{index}",
                "state": "draft" if index < 5 else "active",
                "tags": ["old tag"],
            }
            for index in range(1, 6)
        )
        client = FakePatchClient(drafts)

        with redirect_stdout(StringIO()):
            report = repair_existing_etsy_tags(
                self.memory,
                client,  # type: ignore[arg-type]
                input_fn=lambda _prompt: "FIX 5 TAGS",
            )

        self.assertEqual(report["status"], "ELIGIBLE_DRAFT_COUNT_MISMATCH")
        self.assertEqual(len(client.calls), 0)
        self.assertIn(
            {"product": jobs[4].product_name, "etsy_listing_id": "listing-5", "reason": "NOT_CURRENT_DRAFT"},
            report["skipped"],
        )

    def test_deleted_listing_is_skipped_before_patch(self) -> None:
        jobs = [self.job(*product) for product in FIVE_PRODUCTS]
        for index, job in enumerate(jobs, start=1):
            self.save_verified_report(job, f"listing-{index}")
        client = FakePatchClient(
            tuple(
                {
                    "listing_id": f"listing-{index}",
                    "state": "draft",
                    "tags": ["old tag"],
                }
                for index in range(1, 5)
            )
        )

        with redirect_stdout(StringIO()):
            report = repair_existing_etsy_tags(
                self.memory,
                client,  # type: ignore[arg-type]
                input_fn=lambda _prompt: "FIX 5 TAGS",
            )

        self.assertEqual(report["status"], "ELIGIBLE_DRAFT_COUNT_MISMATCH")
        self.assertEqual(len(client.calls), 0)
        self.assertIn(
            {"product": jobs[4].product_name, "etsy_listing_id": "listing-5", "reason": "NOT_CURRENT_DRAFT"},
            report["skipped"],
        )

    def test_unverified_seo_package_is_skipped_before_patch(self) -> None:
        jobs = [self.job(*product) for product in FIVE_PRODUCTS]
        for index, job in enumerate(jobs, start=1):
            self.save_verified_report(job, f"listing-{index}", write_seo=index != 5)
        client = FakePatchClient(
            tuple(
                {
                    "listing_id": f"listing-{index}",
                    "state": "draft",
                    "tags": ["old tag"],
                }
                for index in range(1, 6)
            )
        )

        with redirect_stdout(StringIO()):
            report = repair_existing_etsy_tags(
                self.memory,
                client,  # type: ignore[arg-type]
                input_fn=lambda _prompt: "FIX 5 TAGS",
            )

        self.assertEqual(report["status"], "ELIGIBLE_DRAFT_COUNT_MISMATCH")
        self.assertEqual(len(client.calls), 0)
        self.assertIn(
            {"product": jobs[4].product_name, "etsy_listing_id": "listing-5", "reason": "MISSING_SEO"},
            report["skipped"],
        )

    def test_cli_scripts_do_not_require_scripts_package_imports(self) -> None:
        audit = subprocess.run(
            [sys.executable, "scripts/audit_etsy_listing_seo.py"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        repair_help = subprocess.run(
            [sys.executable, "scripts/fix_existing_etsy_tags.py", "--help"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(audit.returncode, 0, audit.stderr)
        self.assertEqual(repair_help.returncode, 0, repair_help.stderr)
        self.assertNotIn("ModuleNotFoundError", audit.stderr + repair_help.stderr)


if __name__ == "__main__":
    unittest.main()
