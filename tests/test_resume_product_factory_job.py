"""Tests for safely resuming a failed Product Factory job."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(SRC_PATH))

from project_aurora.integrations.etsy.etsy_config import EtsyConfig  # noqa: E402
from project_aurora.planning.production_queue_manager import (  # noqa: E402
    COMPLETED,
    FAILED,
    ProductionJob,
    ProductionQueueManager,
)
from project_aurora.production.product_factory import REPORT_COLLECTION  # noqa: E402
from project_aurora.production.production_report import ProductionReport  # noqa: E402
from project_aurora.storage.csv_storage import CSVStorage  # noqa: E402
from project_aurora.storage.memory_manager import MemoryManager  # noqa: E402
from scripts.resume_product_factory_job import (  # noqa: E402
    ProductFactoryResumeService,
)


JOB_ID = "82a254a0-b5ad-411f-8ba1-b46a6c6c484a"
LISTING_ID = "4538323035"


class FakeResumeEtsyClient:
    """Mock Etsy client for resume tests."""

    def __init__(
        self,
        existing_images: tuple[dict[str, object], ...],
        existing_files: tuple[dict[str, object], ...] = (),
        fail_image_rank: int | None = None,
    ) -> None:
        self.existing_images = existing_images
        self.existing_files = existing_files
        self.fail_image_rank = fail_image_rank
        self.created_drafts = 0
        self.uploaded_images: list[tuple[str, str, int]] = []
        self.uploaded_files: list[tuple[str, str, int | None]] = []

    def list_listing_images(self, listing_id: str) -> tuple[dict[str, object], ...]:
        return self.existing_images

    def upload_listing_image(
        self,
        listing_id: str,
        image_path: Path,
        rank: int,
    ) -> dict[str, object]:
        if rank == self.fail_image_rank:
            raise RuntimeError("image upload failed")
        self.uploaded_images.append((listing_id, image_path.name, rank))
        return {"listing_image_id": f"image-{rank}"}

    def list_listing_digital_files(
        self,
        listing_id: str,
    ) -> tuple[dict[str, object], ...]:
        return self.existing_files

    def upload_listing_digital_file(
        self,
        listing_id: str,
        file_path: Path,
        rank: int | None = None,
    ) -> dict[str, object]:
        self.uploaded_files.append((listing_id, file_path.name, rank))
        return {"listing_file_id": f"file-{rank}"}

    def create_draft_listing(self, payload: object) -> object:
        self.created_drafts += 1
        raise AssertionError("Resume must never create a draft.")


class ResumeProductFactoryJobTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base_path = Path(self.temp_dir.name)
        self.memory = MemoryManager(
            storage=CSVStorage(base_path=self.base_path / "memory")
        )
        self.queue = ProductionQueueManager(queue_path=self.base_path / "queue.json")
        self.queue.add_existing_job(self.make_job())
        self.final_dir = (
            self.base_path
            / "jobs"
            / "job_woodland"
            / "final_product_images"
        )
        self.write_final_images()
        self.save_failed_report()
        self.config = EtsyConfig(
            mode="live",
            shop_id="shop",
            client_id="client",
            shared_secret="secret",
            access_token="token",
            taxonomy_id=123,
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def make_job(self) -> ProductionJob:
        return ProductionJob(
            id=JOB_ID,
            priority="High",
            product_name="Woodland Baby Animals",
            category="Digital Clipart",
            style="Woodland Friends",
            seasonal_theme="Evergreen",
            keywords=("woodland", "baby", "animals"),
            confidence_score=0.96,
            estimated_competition="Low",
            estimated_demand="High",
            estimated_revenue=164,
            status=FAILED,
        )

    def write_final_images(self) -> None:
        self.final_dir.mkdir(parents=True)
        for index in range(1, 5):
            Image.new("RGBA", (3600, 3600), (255, index, 0, 255)).save(
                self.final_dir / f"strawberry_birthday_party_printable_{index:02d}.png",
                format="PNG",
                dpi=(300, 300),
            )

    def save_failed_report(self) -> None:
        report = ProductionReport(
            job_id=JOB_ID,
            product="Woodland Baby Animals",
            style="Woodland Friends",
            draft_id=LISTING_ID,
            images=4,
            downloads=0,
            time=20.748,
            success=False,
            failed_stage="listing_image_upload",
            errors=("listing_image_upload failed.",),
            job_paths={
                "job_root": str(self.final_dir.parent),
                "generated_images_dir": str(self.final_dir.parent / "generated_images"),
                "final_product_images_dir": str(self.final_dir),
                "digital_downloads_dir": str(self.final_dir.parent / "digital_downloads"),
            },
            metadata={
                "etsy_draft": {
                    "status": "DRAFT_CREATED",
                    "etsy_listing_id": LISTING_ID,
                },
                "listing_image_upload": {
                    "status": "PARTIAL_FAILURE",
                    "images_uploaded": 3,
                    "failed": 1,
                },
            },
        )
        self.memory.save_record(REPORT_COLLECTION, JOB_ID, report.to_dict())

    def service(self, client: FakeResumeEtsyClient) -> ProductFactoryResumeService:
        return ProductFactoryResumeService(
            memory=self.memory,
            queue_manager=self.queue,
            config=self.config,
            client=client,
        )

    def test_resume_uploads_only_missing_image_then_digital_files(self) -> None:
        client = FakeResumeEtsyClient(
            existing_images=(
                {"rank": 1, "filename": "strawberry_birthday_party_printable_01.png"},
                {"rank": 2, "filename": "strawberry_birthday_party_printable_02.png"},
                {"rank": 3, "filename": "strawberry_birthday_party_printable_03.png"},
            )
        )

        result = self.service(client).resume(JOB_ID)

        self.assertEqual(result.etsy_listing_id, LISTING_ID)
        self.assertEqual(result.resumed_from_stage, "listing_image_upload")
        self.assertEqual(result.images_already_present, 3)
        self.assertEqual(result.images_uploaded_now, 1)
        self.assertEqual(result.downloads_uploaded, 4)
        self.assertEqual(result.final_status, "COMPLETED")
        self.assertEqual(
            client.uploaded_images,
            [
                (
                    LISTING_ID,
                    "strawberry_birthday_party_printable_04.png",
                    4,
                )
            ],
        )
        self.assertEqual([item[2] for item in client.uploaded_files], [1, 2, 3, 4])
        self.assertEqual(client.created_drafts, 0)
        self.assertEqual(self.queue.list_jobs()[0].status, COMPLETED)
        saved = self.memory.load_record(REPORT_COLLECTION, JOB_ID)
        self.assertTrue(saved["success"])
        self.assertEqual(saved["downloads"], 4)
        self.assertEqual(saved["metadata"]["listing_image_upload"]["status"], "SUCCESS")

    def test_resume_skips_all_existing_images(self) -> None:
        client = FakeResumeEtsyClient(
            existing_images=tuple(
                {
                    "rank": index,
                    "filename": f"strawberry_birthday_party_printable_{index:02d}.png",
                }
                for index in range(1, 5)
            )
        )

        result = self.service(client).resume(JOB_ID)

        self.assertEqual(result.images_already_present, 4)
        self.assertEqual(result.images_uploaded_now, 0)
        self.assertEqual(client.uploaded_images, [])
        self.assertEqual(result.final_status, "COMPLETED")

    def test_failed_image_sync_does_not_upload_downloads_or_complete_queue(self) -> None:
        client = FakeResumeEtsyClient(
            existing_images=(
                {"rank": 1, "filename": "strawberry_birthday_party_printable_01.png"},
                {"rank": 2, "filename": "strawberry_birthday_party_printable_02.png"},
                {"rank": 3, "filename": "strawberry_birthday_party_printable_03.png"},
            ),
            fail_image_rank=4,
        )

        result = self.service(client).resume(JOB_ID)

        self.assertEqual(result.final_status, "FAILED")
        self.assertEqual(client.uploaded_files, [])
        self.assertEqual(self.queue.list_jobs()[0].status, FAILED)
        saved = self.memory.load_record(REPORT_COLLECTION, JOB_ID)
        self.assertFalse(saved["success"])
        self.assertEqual(saved["failed_stage"], "listing_image_upload")


if __name__ == "__main__":
    unittest.main()
