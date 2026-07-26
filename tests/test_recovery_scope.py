"""Tests for simplified watercolor production recovery scope."""

from __future__ import annotations

import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(SRC_PATH))

from project_aurora.image_generation.commercial_image_exporter import (  # noqa: E402
    CommercialImageExporter,
    validate_commercial_png,
)
from project_aurora.planning.production_queue_manager import (  # noqa: E402
    FAILED,
    READY,
    UNSUPPORTED_PRODUCT_TYPE,
    ProductionJob,
    ProductionQueueManager,
)
from project_aurora.production.product_capability_resolver import ProductCapabilityResolver  # noqa: E402
from project_aurora.production.product_factory import _simple_watercolor_generation_prompt  # noqa: E402
from project_aurora.production.product_packager import ProductPackager  # noqa: E402
from project_aurora.production.product_specification import build_product_specification  # noqa: E402
from project_aurora.production.watercolor_scope import resolve_watercolor_scope  # noqa: E402
from project_aurora.quality.commercial_image_qa import CommercialImageQA  # noqa: E402
from scripts.recover_supported_ready_products import main as recover_main  # noqa: E402
from scripts.retire_unsupported_products import main as retire_main  # noqa: E402


class RecoveryScopeTest(unittest.TestCase):
    def test_watercolor_mushroom_clipart_maps_to_supported_bundle(self) -> None:
        decision = resolve_watercolor_scope("Autumn Mushroom Clipart", "digital illustration collection")
        self.assertTrue(decision.supported)
        self.assertEqual(decision.canonical_product_type, "watercolor_botanical_collection")

    def test_storybook_animal_maps_to_signature_collection(self) -> None:
        decision = resolve_watercolor_scope("Whimsical Storybook Animal Bakery", "digital illustration collection")
        self.assertTrue(decision.supported)
        self.assertEqual(decision.canonical_product_type, "signature_storybook_animal_collection")

    def test_planner_teacher_typography_products_are_unsupported(self) -> None:
        for name in (
            "Wedding Planner Stickers",
            "Teacher Alphabet Posters",
            "Typography Quote Art",
        ):
            self.assertFalse(resolve_watercolor_scope(name, name).supported)
            self.assertFalse(
                ProductCapabilityResolver().resolve(name, name, name).supported
            )

    def test_simple_prompt_contains_isolated_watercolor_and_forbids_marketing(self) -> None:
        job = _job("Autumn Mushroom Clipart", "digital illustration collection")
        spec = build_product_specification(job)
        prompt = _simple_watercolor_generation_prompt(job, spec).casefold()
        self.assertIn("watercolor", prompt)
        self.assertIn("isolated", prompt)
        self.assertIn("transparent background", prompt)
        self.assertIn("no text", prompt)
        self.assertIn("no poster", prompt)
        self.assertIn("no typography", prompt)
        self.assertNotIn("create an etsy cover", prompt)

    def test_export_converts_to_4000_png_with_dpi_and_alpha(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "source"
            output = Path(temp_dir) / "out"
            for index in range(1, 5):
                _write_png(source / f"source_{index}.png", size=(1024, 900))
            result = CommercialImageExporter(source, output, required_count=4, category="clipart").export()
            self.assertEqual(result.status, "SUCCESS")
            for path_text in result.exported_files:
                path = Path(path_text)
                self.assertFalse(validate_commercial_png(path))
                with Image.open(path) as image:
                    self.assertEqual(image.size, (4000, 4000))
                    self.assertEqual(image.mode, "RGBA")
                    self.assertTrue(image.info.get("dpi"))

    def test_zip_contains_expected_png_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            product_dir = Path(temp_dir)
            for index in range(1, 5):
                _write_png(product_dir / f"clipart_{index:02d}.png", size=(4000, 4000))
            result = ProductPackager().package(
                product_name="Autumn Mushroom Clipart",
                category="clipart",
                product_dir=product_dir,
            )
            self.assertEqual(result.status, "SUCCESS")
            with zipfile.ZipFile(result.package_files[0]) as archive:
                self.assertEqual(len(archive.namelist()), 4)

    def test_missing_optional_visual_qa_does_not_fail(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            job = _job("Autumn Mushroom Clipart", "clipart")
            job_root = Path(temp_dir) / job.id.replace("-", "_")
            final_dir = job_root / "final_product_images"
            files = tuple(final_dir / f"asset_{index}.png" for index in range(1, 5))
            final_dir.mkdir(parents=True, exist_ok=True)
            for path in files:
                path.write_bytes(b"not-empty")
            result = CommercialImageQA().evaluate(
                job=job,
                final_files=files,
                prompt_package={"expected_image_count": 4},
                product_specification=build_product_specification(job),
                workspace=job_root,
            )
            self.assertEqual(result.status, "PASS")

    def test_recovery_dry_run_makes_no_changes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            queue_path = Path(temp_dir) / "queue.json"
            manager = ProductionQueueManager(queue_path=queue_path)
            manager.add_existing_job(_job("Autumn Mushroom Clipart", "clipart", status=FAILED))
            with patch("scripts.recover_supported_ready_products.QUEUE_PATH", queue_path):
                recover_main(["--dry-run", "--all-eligible"])
            self.assertEqual(ProductionQueueManager(queue_path=queue_path).list_jobs()[0].status, FAILED)

    def test_retire_unsupported_apply_preserves_job_with_unsupported_status(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            queue_path = Path(temp_dir) / "queue.json"
            manager = ProductionQueueManager(queue_path=queue_path)
            manager.add_existing_job(_job("Teacher Alphabet Posters", "wall art"))
            with patch("scripts.retire_unsupported_products.QUEUE_PATH", queue_path):
                retire_main(["--apply"])
            job = ProductionQueueManager(queue_path=queue_path).list_jobs()[0]
            self.assertEqual(job.status, UNSUPPORTED_PRODUCT_TYPE)
            self.assertTrue(job.blocking_reason)


def _job(name: str, category: str, status: str = READY) -> ProductionJob:
    return ProductionJob(
        id=name.casefold().replace(" ", "-")[:30],
        priority="High",
        product_name=name,
        category=category,
        style="Watercolor",
        seasonal_theme="Evergreen",
        keywords=tuple(name.casefold().split()),
        confidence_score=0.9,
        estimated_competition="Low",
        estimated_demand="High",
        estimated_revenue=100.0,
        status=status,
        required_image_count=4,
    )


def _write_png(path: Path, size: tuple[int, int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGBA", size, (255, 255, 255, 0))
    for x in range(size[0] // 4, size[0] // 2):
        for y in range(size[1] // 4, size[1] // 2):
            image.putpixel((x, y), (120, 80, 60, 255))
    image.save(path, format="PNG", dpi=(300, 300))


if __name__ == "__main__":
    unittest.main()
