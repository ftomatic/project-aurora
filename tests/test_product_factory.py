"""Tests for Sprint 20 Product Factory orchestration."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_PATH))

from project_aurora.planning.production_queue_manager import (  # noqa: E402
    COMPLETED,
    FAILED,
    READY,
    ProductionJob,
    ProductionQueueManager,
)
from project_aurora.production.product_factory import (  # noqa: E402
    REPORT_COLLECTION,
    ProductFactory,
)
from project_aurora.production.production_report import (  # noqa: E402
    ProductionReport,
)
from project_aurora.storage.csv_storage import CSVStorage  # noqa: E402
from project_aurora.storage.memory_manager import MemoryManager  # noqa: E402


def make_job(job_id: str = "job-1") -> ProductionJob:
    return ProductionJob(
        id=job_id,
        priority="High",
        product_name="Woodland Baby Animals",
        category="Digital Clipart",
        style="Storybook Watercolor",
        seasonal_theme="Evergreen",
        keywords=("woodland", "baby", "animals"),
        confidence_score=0.96,
        estimated_competition="Low",
        estimated_demand="High",
        estimated_revenue=164.0,
        status=READY,
    )


class FakeStageRunner:
    def __init__(self, fail_stage: str | None = None) -> None:
        self.fail_stage = fail_stage
        self.calls: list[str] = []

    def compose_prompts(self, job: ProductionJob) -> object:
        self.calls.append("prompt_composition")
        return SimpleNamespace(final_prompt="prompt")

    def generate_images(self, job: ProductionJob) -> object:
        self.calls.append("image_generation")
        if self.fail_stage == "image_generation":
            return SimpleNamespace(
                status="FAILED",
                errors=("OpenAI image generation failed.",),
                generated_files=(),
            )
        return SimpleNamespace(
            status="SUCCESS",
            generated_files=("image1.png", "image2.png", "image3.png", "image4.png"),
            warnings=(),
        )

    def run_image_qa(self, job: ProductionJob) -> tuple[object, ...]:
        self.calls.append("image_qa")
        return (
            SimpleNamespace(status="PASS", asset_name="image1.png"),
            SimpleNamespace(status="PASS", asset_name="image2.png"),
            SimpleNamespace(status="PASS", asset_name="image3.png"),
            SimpleNamespace(status="PASS", asset_name="image4.png"),
        )

    def export_commercial_images(self, job: ProductionJob) -> object:
        self.calls.append("commercial_export")
        return SimpleNamespace(
            status="SUCCESS",
            exported_files=("final1.png", "final2.png", "final3.png", "final4.png"),
            warnings=(),
            errors=(),
        )

    def generate_seo(self, job: ProductionJob) -> object:
        self.calls.append("seo_generation")
        return SimpleNamespace(status="SUCCESS", title="SEO title", warnings=())

    def create_etsy_draft(self, job: ProductionJob, seo_package: object) -> object:
        self.calls.append("etsy_draft")
        if self.fail_stage == "etsy_draft":
            return SimpleNamespace(
                status="VALIDATION_FAILED",
                etsy_listing_id=None,
                errors=("Draft validation failed.",),
            )
        return SimpleNamespace(
            status="DRAFT_CREATED",
            etsy_listing_id="4537338498",
            warnings=(),
        )

    def upload_listing_images(self, job: ProductionJob) -> object:
        self.calls.append("listing_image_upload")
        if self.fail_stage == "listing_image_upload":
            return SimpleNamespace(
                status="PARTIAL_FAILURE",
                images_uploaded=2,
                failed=2,
                errors=("Image upload failed.",),
            )
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
        self.calls.append("customer_download_upload")
        return SimpleNamespace(
            status="SUCCESS",
            files_uploaded=4,
            failed=0,
            warnings=(),
        )


class ProductFactoryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base_path = Path(self.temp_dir.name)
        self.queue = ProductionQueueManager(
            queue_path=self.base_path / "queue.json",
            id_factory=lambda: "unused",
        )
        self.memory = MemoryManager(
            storage=CSVStorage(base_path=self.base_path / "memory")
        )
        self.job = self.queue.add_existing_job(make_job())

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_production_report_dataclass(self) -> None:
        report = ProductionReport(
            job_id="job-1",
            product="Woodland Baby Animals",
            style="Storybook Watercolor",
            draft_id="4537338498",
            images=4,
            downloads=4,
            time=1.2,
            success=True,
        )

        self.assertEqual(report.queue_status, COMPLETED)
        self.assertEqual(report.to_dict()["draft_id"], "4537338498")

    def test_factory_success_marks_queue_complete_and_saves_report(self) -> None:
        runner = FakeStageRunner()

        report = ProductFactory(
            queue_manager=self.queue,
            memory=self.memory,
            stage_runner=runner,
        ).execute(self.job)

        self.assertTrue(report.success)
        self.assertEqual(report.draft_id, "4537338498")
        self.assertEqual(report.images, 4)
        self.assertEqual(report.downloads, 4)
        self.assertEqual(self.queue.list_jobs()[0].status, COMPLETED)
        saved = self.memory.load_record(REPORT_COLLECTION, "latest")
        self.assertEqual(saved["product"], "Woodland Baby Animals")
        self.assertEqual(saved["queue_status"], COMPLETED)
        self.assertEqual(
            runner.calls,
            [
                "prompt_composition",
                "image_generation",
                "image_qa",
                "commercial_export",
                "seo_generation",
                "etsy_draft",
                "listing_image_upload",
                "customer_download_upload",
            ],
        )

    def test_image_failure_stops_and_marks_queue_failed(self) -> None:
        runner = FakeStageRunner(fail_stage="image_generation")

        report = ProductFactory(
            queue_manager=self.queue,
            memory=self.memory,
            stage_runner=runner,
        ).execute(self.job)

        self.assertFalse(report.success)
        self.assertEqual(report.failed_stage, "image_generation")
        self.assertEqual(self.queue.list_jobs()[0].status, FAILED)
        self.assertIn("OpenAI image generation failed.", report.errors[0])
        self.assertEqual(runner.calls, ["prompt_composition", "image_generation"])

    def test_etsy_failure_preserves_draft_id_and_partial_images(self) -> None:
        runner = FakeStageRunner(fail_stage="listing_image_upload")

        report = ProductFactory(
            queue_manager=self.queue,
            memory=self.memory,
            stage_runner=runner,
        ).execute(self.job)

        self.assertFalse(report.success)
        self.assertEqual(report.failed_stage, "listing_image_upload")
        self.assertEqual(report.draft_id, "4537338498")
        self.assertEqual(report.images, 4)
        self.assertEqual(report.downloads, 0)
        self.assertEqual(self.queue.list_jobs()[0].status, FAILED)
        self.assertNotIn("customer_download_upload", runner.calls)

    def test_queue_transitions_from_ready_to_failed_on_draft_error(self) -> None:
        runner = FakeStageRunner(fail_stage="etsy_draft")

        report = ProductFactory(
            queue_manager=self.queue,
            memory=self.memory,
            stage_runner=runner,
        ).execute(self.job)

        self.assertFalse(report.success)
        self.assertEqual(report.failed_stage, "etsy_draft")
        self.assertIsNone(report.draft_id)
        self.assertEqual(self.queue.list_jobs()[0].status, FAILED)


if __name__ == "__main__":
    unittest.main()
