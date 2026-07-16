"""Tests for style-image manual review workflow."""

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

from project_aurora.production.product_factory import REPORT_COLLECTION  # noqa: E402
from project_aurora.production.production_report import ProductionReport  # noqa: E402
from project_aurora.storage.csv_storage import CSVStorage  # noqa: E402
from project_aurora.storage.memory_manager import MemoryManager  # noqa: E402
from scripts.review_failed_style_images import (  # noqa: E402
    approve_job,
    review_job_images,
)


class StyleImageReviewTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base_path = Path(self.temp_dir.name)
        self.memory = MemoryManager(CSVStorage(base_path=self.base_path / "memory"))
        self.job_id = "job-style-fail"
        self.generated_dir = self.base_path / "jobs" / self.job_id / "generated_images"
        rejected = self.generated_dir / "rejected" / "attempt_1"
        rejected.mkdir(parents=True)
        for index in range(1, 5):
            Image.new("RGBA", (1024, 1024), (255, index, 0, 255)).save(
                rejected / f"review_image_{index:02d}.png",
                format="PNG",
            )
        report = ProductionReport(
            job_id=self.job_id,
            product="Classroom Alphabet Wall Art",
            style="Flat Vector",
            draft_id=None,
            images=4,
            downloads=0,
            time=1,
            success=False,
            failed_stage="image_qa",
            job_paths={
                "generated_images_dir": str(self.generated_dir),
                "final_product_images_dir": str(self.generated_dir.parent / "final_product_images"),
                "digital_downloads_dir": str(self.generated_dir.parent / "digital_downloads"),
            },
        )
        self.memory.save_record(REPORT_COLLECTION, self.job_id, report.to_dict())

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_review_reports_not_evaluated_and_contact_sheet(self) -> None:
        reviews = review_job_images(self.memory, self.job_id)

        self.assertEqual(len(reviews), 4)
        self.assertTrue(all(review.technical_qa == "PASS" for review in reviews))
        self.assertTrue(all(review.semantic_evaluation_status == "NOT_EVALUATED" for review in reviews))
        self.assertTrue(Path(reviews[0].preview_path).exists())

    def test_approved_existing_images_are_reused(self) -> None:
        approve_job(self.memory, self.job_id)

        active = tuple(sorted(self.generated_dir.glob("*.png")))
        approval = self.memory.load_record("style_image_reviews", f"{self.job_id}_approval")

        self.assertEqual(len(active), 4)
        self.assertTrue(approval["reuse_existing_images"])
        self.assertEqual(approval["resume_from_stage"], "image_qa")


if __name__ == "__main__":
    unittest.main()
