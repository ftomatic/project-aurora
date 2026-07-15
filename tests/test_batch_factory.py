"""Tests for Sprint 21 Batch Production Factory."""

from __future__ import annotations

import sys
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(SRC_PATH))

from project_aurora.planning.production_queue_manager import (  # noqa: E402
    COMPLETED,
    FAILED,
    READY,
    ProductionJob,
    ProductionQueueManager,
)
from project_aurora.production.product_factory import REPORT_COLLECTION  # noqa: E402
from project_aurora.production.production_report import ProductionReport  # noqa: E402
from project_aurora.storage.csv_storage import CSVStorage  # noqa: E402
from project_aurora.storage.memory_manager import MemoryManager  # noqa: E402
from scripts.run_batch_factory import (  # noqa: E402
    BatchProductionFactory,
    _build_batch_report,
    parse_args,
    print_batch_report,
)


def make_job(index: int, status: str = READY) -> ProductionJob:
    """Create one deterministic production job."""
    return ProductionJob(
        id=f"job-{index}",
        priority="High",
        product_name=f"Product {index}",
        category="Digital Clipart",
        style="Storybook Watercolor",
        seasonal_theme="Evergreen",
        keywords=(f"product-{index}", "clipart"),
        confidence_score=1 - index * 0.01,
        estimated_competition="Low",
        estimated_demand="High",
        estimated_revenue=100 + index,
        status=status,
    )


class FakeBatchStageRunner:
    """No-network stage runner with configurable failures."""

    def __init__(self, fail_products: set[str] | None = None) -> None:
        self._fail_products = fail_products or set()

    def compose_prompts(self, job: ProductionJob) -> object:
        return SimpleNamespace(final_prompt=f"Prompt for {job.product_name}")

    def generate_images(self, job: ProductionJob) -> object:
        if job.product_name in self._fail_products:
            return SimpleNamespace(
                status="FAILED",
                generated_files=(),
                errors=(f"{job.product_name} image generation failed.",),
            )
        return SimpleNamespace(
            status="SUCCESS",
            generated_files=("1.png", "2.png", "3.png", "4.png"),
            warnings=(),
        )

    def run_image_qa(self, job: ProductionJob) -> tuple[object, ...]:
        return tuple(
            SimpleNamespace(status="PASS", asset_name=f"{index}.png")
            for index in range(1, 5)
        )

    def export_commercial_images(self, job: ProductionJob) -> object:
        return SimpleNamespace(
            status="SUCCESS",
            exported_files=("f1.png", "f2.png", "f3.png", "f4.png"),
            warnings=(),
            errors=(),
        )

    def generate_seo(self, job: ProductionJob) -> object:
        return SimpleNamespace(status="SUCCESS", title=f"{job.product_name} SEO")

    def create_etsy_draft(self, job: ProductionJob, seo_package: object) -> object:
        return SimpleNamespace(
            status="DRAFT_CREATED",
            etsy_listing_id=f"listing-{job.id}",
            warnings=(),
        )

    def upload_listing_images(self, job: ProductionJob) -> object:
        return SimpleNamespace(
            status="SUCCESS",
            images_uploaded=4,
            failed=0,
            warnings=(),
        )

    def upload_customer_downloads(
        self,
        job: ProductionJob,
        listing_id: str | None,
    ) -> object:
        return SimpleNamespace(
            status="SUCCESS",
            files_uploaded=4,
            failed=0,
            warnings=(),
        )


class BatchFactoryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base_path = Path(self.temp_dir.name)
        self.queue = ProductionQueueManager(queue_path=self.base_path / "queue.json")
        self.memory = MemoryManager(
            storage=CSVStorage(base_path=self.base_path / "memory")
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def add_jobs(self, count: int) -> None:
        for index in range(1, count + 1):
            self.queue.add_existing_job(make_job(index))

    def run_batch(
        self,
        count: int,
        fail_products: set[str] | None = None,
    ):
        return BatchProductionFactory(
            queue_manager=self.queue,
            memory=self.memory,
            stage_runner_factory=lambda _job: FakeBatchStageRunner(fail_products),
        ).run(count)

    def test_all_succeed(self) -> None:
        self.add_jobs(2)

        report = self.run_batch(count=2)

        self.assertEqual(report.requested, 2)
        self.assertEqual(report.completed, 2)
        self.assertEqual(report.failed, 0)
        self.assertEqual(report.drafts_created, 2)
        self.assertEqual(report.draft_ids, ("listing-job-1", "listing-job-2"))
        self.assertEqual(report.images_generated, 8)
        self.assertEqual(report.downloads_uploaded, 8)
        self.assertEqual(
            [job.status for job in self.queue.list_jobs()],
            [COMPLETED, COMPLETED],
        )

    def test_one_failure_continues_to_next_job(self) -> None:
        self.add_jobs(3)

        report = self.run_batch(count=3, fail_products={"Product 2"})

        self.assertEqual(report.completed, 2)
        self.assertEqual(report.failed, 1)
        self.assertEqual(report.drafts_created, 2)
        self.assertEqual(report.draft_ids, ("listing-job-1", "listing-job-3"))
        self.assertEqual(report.images_generated, 8)
        self.assertEqual(report.downloads_uploaded, 8)
        self.assertEqual(len(report.failure_summary), 1)
        self.assertEqual(report.failure_summary[0]["product"], "Product 2")
        statuses = {job.product_name: job.status for job in self.queue.list_jobs()}
        self.assertEqual(statuses["Product 1"], COMPLETED)
        self.assertEqual(statuses["Product 2"], FAILED)
        self.assertEqual(statuses["Product 3"], COMPLETED)

    def test_empty_queue(self) -> None:
        report = self.run_batch(count=3)

        self.assertEqual(report.attempted, 0)
        self.assertEqual(report.completed, 0)
        self.assertEqual(report.failed, 0)
        self.assertEqual(report.drafts_created, 0)
        self.assertEqual(report.draft_ids, ())

    def test_count_exceeds_queue_size(self) -> None:
        self.add_jobs(2)

        report = self.run_batch(count=5)

        self.assertEqual(report.requested, 5)
        self.assertEqual(report.attempted, 2)
        self.assertEqual(report.completed, 2)
        self.assertEqual(len(report.reports), 2)

    def test_production_reports_saved(self) -> None:
        self.add_jobs(1)

        report = self.run_batch(count=1)
        latest_batch = self.memory.load_record(REPORT_COLLECTION, "latest_batch")
        latest_job = self.memory.load_record(REPORT_COLLECTION, "latest")

        self.assertEqual(latest_batch["requested"], 1)
        self.assertEqual(latest_batch["completed"], 1)
        self.assertEqual(latest_batch["draft_ids"], ["listing-job-1"])
        self.assertEqual(latest_batch["reports"][0]["job_id"], "job-1")
        self.assertEqual(latest_job["job_id"], "job-1")
        self.assertEqual(report.completed, 1)

    def test_queue_state_transitions_leave_unprocessed_ready(self) -> None:
        self.add_jobs(3)

        self.run_batch(count=2)

        statuses = {job.product_name: job.status for job in self.queue.list_jobs()}
        self.assertEqual(statuses["Product 1"], COMPLETED)
        self.assertEqual(statuses["Product 2"], COMPLETED)
        self.assertEqual(statuses["Product 3"], READY)

    def test_cli_count_argument(self) -> None:
        args = parse_args(["--count", "3"])

        self.assertEqual(args.count, 3)
        self.assertFalse(args.live)

    def test_batch_report_counts_drafts_from_production_reports(self) -> None:
        reports = tuple(
            ProductionReport(
                job_id=f"job-{index}",
                product=f"Product {index}",
                style="Storybook Watercolor",
                draft_id=str(4538300845 + index) if index == 1 else None,
                images=4,
                downloads=4,
                time=60 + index,
                success=True,
                metadata={
                    "etsy_draft": {
                        "status": "DRAFT_CREATED",
                        "etsy_listing_id": str(4538300845 + index),
                    }
                },
            )
            for index in range(1, 4)
        )

        report = _build_batch_report(
            requested=3,
            reports=reports,
            elapsed_time=0.001,
        )

        self.assertEqual(report.completed, 3)
        self.assertEqual(report.failed, 0)
        self.assertEqual(report.drafts_created, 3)
        self.assertEqual(
            report.draft_ids,
            ("4538300846", "4538300847", "4538300848"),
        )
        self.assertEqual(report.images_generated, 12)
        self.assertEqual(report.downloads_uploaded, 12)
        self.assertEqual(report.elapsed_time, 186)

    def test_batch_output_prints_draft_ids_and_real_elapsed_time(self) -> None:
        report = _build_batch_report(
            requested=3,
            reports=(
                ProductionReport(
                    job_id="job-1",
                    product="Product 1",
                    style="Storybook Watercolor",
                    draft_id="4538300846",
                    images=4,
                    downloads=4,
                    time=63.002,
                    success=True,
                ),
            ),
            elapsed_time=0.001,
        )

        with patch("sys.stdout", new_callable=StringIO) as output:
            print_batch_report(report)

        rendered = output.getvalue()
        self.assertIn("Drafts Created\n1", rendered)
        self.assertIn("Draft IDs\n4538300846", rendered)
        self.assertIn("Elapsed Time\n63.00 seconds", rendered)


if __name__ == "__main__":
    unittest.main()
