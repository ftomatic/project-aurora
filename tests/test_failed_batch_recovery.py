"""Tests for failed Product Factory batch recovery."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(SRC_PATH))
sys.path.insert(0, str(PROJECT_ROOT))

from project_aurora.planning.production_queue_manager import (  # noqa: E402
    COMPLETED,
    FAILED,
    ProductionJob,
    ProductionQueueManager,
)
from project_aurora.production.production_report import ProductionReport  # noqa: E402
from project_aurora.storage.csv_storage import CSVStorage  # noqa: E402
from project_aurora.storage.memory_manager import MemoryManager  # noqa: E402
from scripts.resume_failed_batch import (  # noqa: E402
    ResumeProductFactoryStageRunner,
    run_failed_batch_recovery,
)
from scripts.run_batch_factory import BatchRuntimeConfig  # noqa: E402


def failed_job(index: int) -> ProductionJob:
    """Create a failed production job."""
    return ProductionJob(
        id=f"job-{index}",
        priority="High",
        product_name=f"Product {index}",
        category="clipart",
        style="Storybook Watercolor",
        seasonal_theme="Evergreen",
        keywords=(f"product-{index}",),
        confidence_score=0.9,
        estimated_competition="Low",
        estimated_demand="High",
        estimated_revenue=120,
        status=FAILED,
    )


def completed_job(index: int) -> ProductionJob:
    """Create a completed production job."""
    job = failed_job(index)
    return ProductionJob(
        id=job.id,
        priority=job.priority,
        product_name="Autumn Mushroom Clipart",
        category=job.category,
        style=job.style,
        seasonal_theme=job.seasonal_theme,
        keywords=job.keywords,
        confidence_score=job.confidence_score,
        estimated_competition=job.estimated_competition,
        estimated_demand=job.estimated_demand,
        estimated_revenue=job.estimated_revenue,
        created_at=job.created_at,
        status=COMPLETED,
    )


class FailedBatchRecoveryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base_path = Path(self.temp_dir.name)
        self.queue_path = self.base_path / "queue.json"
        self.queue = ProductionQueueManager(queue_path=self.queue_path)
        self.memory = MemoryManager(CSVStorage(base_path=self.base_path / "memory"))

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def add_failed_jobs(self, count: int) -> None:
        for index in range(1, count + 1):
            self.queue.add_existing_job(failed_job(index))

    def test_existing_draft_id_is_reused_without_duplicate_creation(self) -> None:
        runner = ResumeProductFactoryStageRunner(
            memory=self.memory,
            etsy_config=type("Config", (), {"is_mock_mode": True})(),
            existing_draft_id="4538323035",
        )

        result = runner.create_etsy_draft(failed_job(1), seo_package=object())

        self.assertEqual(result.status, "DRAFT_CREATED")
        self.assertEqual(result.etsy_listing_id, "4538323035")

    def test_recovery_batch_summary(self) -> None:
        self.add_failed_jobs(5)
        for index in range(1, 6):
            original = ProductionReport(
                job_id=f"job-{index}",
                product=f"Product {index}",
                style="Storybook Watercolor",
                draft_id=f"draft-{index}",
                images=1,
                downloads=0,
                time=1,
                success=False,
                failed_stage="listing_image_upload",
            )
            self.memory.save_record("production_reports", f"job-{index}", original.to_dict())
        returned = [
            ProductionReport(
                job_id=f"job-{index}",
                product=f"Product {index}",
                style="Storybook Watercolor",
                draft_id=f"draft-{index}",
                images=4,
                downloads=4,
                time=1,
                success=True,
                metadata={
                    "image_generation": {
                        "status": "SUCCESS",
                        "warnings": (
                            ["Reused existing valid job generated images."]
                            if index <= 2
                            else []
                        ),
                    },
                    "listing_image_upload": {
                        "status": "SUCCESS",
                        "images_already_present": 1,
                        "images_uploaded_now": 3,
                        "images_present_after": 4,
                    },
                    "customer_download_upload": {
                        "files_uploaded": 4,
                        "metadata": {"total_present": 4},
                    },
                },
            )
            for index in range(1, 6)
        ]

        class FakeResumeService:
            def __init__(self, memory: MemoryManager, queue_manager: ProductionQueueManager, **kwargs: object) -> None:
                self._memory = memory
                self._queue_manager = queue_manager

            def resume(self, job_id: str) -> object:
                report = returned.pop(0)
                self._queue_manager.mark_completed(job_id)
                self._memory.save_record("production_reports", job_id, report.to_dict())
                return object()

        with patch("scripts.resume_failed_batch.ProductFactoryResumeService", FakeResumeService), patch(
            "scripts.resume_failed_batch.EtsyConfig.from_environment",
            return_value=type("Config", (), {"is_mock_mode": True})(),
        ), patch("scripts.resume_failed_batch.print_etsy_config_diagnostics"):
            report = run_failed_batch_recovery(
                limit=5,
                queue_path=self.queue_path,
                memory=self.memory,
                runtime_config=BatchRuntimeConfig(openai_image_delay_seconds=0),
            )

        self.assertEqual(report.jobs_found, 5)
        self.assertEqual(report.jobs_verified_complete, 5)
        self.assertEqual(report.jobs_still_incomplete, 0)
        self.assertEqual(report.drafts_repaired, 5)
        self.assertEqual(report.existing_drafts_reused, 5)
        self.assertEqual(report.new_drafts_created, 0)
        self.assertEqual(report.missing_images_detected, 15)
        self.assertEqual(report.images_uploaded_during_repair, 15)
        self.assertEqual(report.images_present_after, 20)
        self.assertEqual(report.digital_files_present_after, 20)
        self.assertEqual(report.missing_digital_files_uploaded, 20)
        self.assertEqual(report.status, "SUCCESS")
        reloaded_queue = ProductionQueueManager(queue_path=self.queue_path)
        self.assertTrue(all(job.status == COMPLETED for job in reloaded_queue.list_jobs()))

    def test_recovery_continues_after_individual_failure(self) -> None:
        self.add_failed_jobs(2)
        returned = [
            ProductionReport(
                job_id="job-1",
                product="Product 1",
                style="Storybook Watercolor",
                draft_id=None,
                images=0,
                downloads=0,
                time=1,
                success=False,
                failed_stage="image_generation",
                errors=("rate limit exhausted",),
            ),
            ProductionReport(
                job_id="job-2",
                product="Product 2",
                style="Storybook Watercolor",
                draft_id="draft-2",
                images=4,
                downloads=4,
                time=1,
                success=True,
                metadata={
                    "image_generation": {"status": "SUCCESS", "warnings": []},
                    "listing_image_upload": {
                        "images_already_present": 4,
                        "images_uploaded_now": 0,
                        "images_present_after": 4,
                    },
                    "customer_download_upload": {
                        "files_uploaded": 4,
                        "metadata": {"total_present": 4},
                    },
                },
            ),
        ]

        class FakeResumeService:
            def __init__(self, memory: MemoryManager, queue_manager: ProductionQueueManager, **kwargs: object) -> None:
                self._memory = memory
                self._queue_manager = queue_manager

            def resume(self, job_id: str) -> object:
                report = returned.pop(0)
                if report.success:
                    self._queue_manager.mark_completed(job_id)
                else:
                    self._queue_manager.mark_failed(job_id)
                self._memory.save_record("production_reports", job_id, report.to_dict())
                return object()

        with patch("scripts.resume_failed_batch.ProductFactoryResumeService", FakeResumeService), patch(
            "scripts.resume_failed_batch.EtsyConfig.from_environment",
            return_value=type("Config", (), {"is_mock_mode": True})(),
        ), patch("scripts.resume_failed_batch.print_etsy_config_diagnostics"):
            report = run_failed_batch_recovery(
                limit=2,
                queue_path=self.queue_path,
                memory=self.memory,
                runtime_config=BatchRuntimeConfig(openai_image_delay_seconds=0),
            )

        self.assertEqual(report.jobs_verified_complete, 1)
        self.assertEqual(report.jobs_still_incomplete, 1)
        self.assertEqual(report.status, "PARTIAL_FAILURE")

    def test_completed_autumn_job_is_skipped(self) -> None:
        self.queue.add_existing_job(completed_job(1))
        self.queue.add_existing_job(failed_job(2))
        resumed: list[str] = []

        class FakeResumeService:
            def __init__(self, memory: MemoryManager, queue_manager: ProductionQueueManager, **kwargs: object) -> None:
                self._memory = memory
                self._queue_manager = queue_manager

            def resume(self, job_id: str) -> object:
                resumed.append(job_id)
                report = ProductionReport(
                    job_id=job_id,
                    product="Product 2",
                    style="Storybook Watercolor",
                    draft_id="draft-2",
                    images=4,
                    downloads=4,
                    time=1,
                    success=True,
                    metadata={
                        "image_generation": {"status": "SUCCESS", "warnings": []},
                        "listing_image_upload": {
                            "images_already_present": 4,
                            "images_uploaded_now": 0,
                            "images_present_after": 4,
                        },
                        "customer_download_upload": {
                            "files_uploaded": 4,
                            "metadata": {"total_present": 4},
                        },
                    },
                )
                self._queue_manager.mark_completed(job_id)
                self._memory.save_record("production_reports", job_id, report.to_dict())
                return object()

        with patch("scripts.resume_failed_batch.ProductFactoryResumeService", FakeResumeService), patch(
            "scripts.resume_failed_batch.EtsyConfig.from_environment",
            return_value=type("Config", (), {"is_mock_mode": True})(),
        ), patch("scripts.resume_failed_batch.print_etsy_config_diagnostics"):
            report = run_failed_batch_recovery(
                limit=5,
                queue_path=self.queue_path,
                memory=self.memory,
                runtime_config=BatchRuntimeConfig(openai_image_delay_seconds=0),
            )

        self.assertEqual(resumed, ["job-2"])
        self.assertEqual(report.jobs_found, 1)
        self.assertEqual(report.jobs_verified_complete, 1)

    def test_recovery_success_requires_final_etsy_verification(self) -> None:
        self.add_failed_jobs(1)
        bad_report = ProductionReport(
            job_id="job-1",
            product="Product 1",
            style="Storybook Watercolor",
            draft_id="draft-1",
            images=3,
            downloads=4,
            time=1,
            success=True,
            metadata={
                "listing_image_upload": {
                    "images_already_present": 1,
                    "images_uploaded_now": 2,
                    "images_present_after": 3,
                },
                "customer_download_upload": {
                    "files_uploaded": 0,
                    "metadata": {"total_present": 4},
                },
            },
        )

        class FakeResumeService:
            def __init__(self, memory: MemoryManager, queue_manager: ProductionQueueManager, **kwargs: object) -> None:
                self._memory = memory

            def resume(self, job_id: str) -> object:
                self._memory.save_record("production_reports", job_id, bad_report.to_dict())
                return object()

        with patch("scripts.resume_failed_batch.ProductFactoryResumeService", FakeResumeService), patch(
            "scripts.resume_failed_batch.EtsyConfig.from_environment",
            return_value=type("Config", (), {"is_mock_mode": True})(),
        ), patch("scripts.resume_failed_batch.print_etsy_config_diagnostics"):
            report = run_failed_batch_recovery(
                limit=1,
                queue_path=self.queue_path,
                memory=self.memory,
                runtime_config=BatchRuntimeConfig(openai_image_delay_seconds=0),
            )

        self.assertEqual(report.jobs_verified_complete, 0)
        self.assertEqual(report.jobs_still_incomplete, 1)
        self.assertEqual(report.status, "PARTIAL_FAILURE")


if __name__ == "__main__":
    unittest.main()
