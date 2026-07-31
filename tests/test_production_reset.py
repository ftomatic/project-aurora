"""Tests for safe production reset and STORYBOOK acceptance setup."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(SRC_PATH))

from project_aurora.planning.production_queue_manager import (  # noqa: E402
    READY,
    ProductionJob,
    ProductionQueueManager,
)
from project_aurora.production.art_direction_package import (  # noqa: E402
    build_art_direction_package,
)
from project_aurora.production.product_factory import (  # noqa: E402
    GENERATION_MODE_STORYBOOK,
    ProductFactoryPaths,
    ProductFactoryStageError,
    _job_generation_override,
    _save_art_direction_package,
    _verify_storybook_acceptance_gate,
    _write_asset_manifest,
)
from scripts import create_storybook_acceptance_job, reset_production_queue  # noqa: E402


class ProductionResetTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base_path = Path(self.temp_dir.name)
        self.queue_path = self.base_path / "data" / "aurora" / "production_queue" / "queue.json"
        self.data_root = self.base_path / "data" / "aurora"
        self.queue = ProductionQueueManager(queue_path=self.queue_path)
        self.queue.add_job(
            priority="High",
            product_name="Old Completed Product",
            category="Digital Clipart",
            style="Storybook",
            seasonal_theme="Spring",
            keywords=("old",),
            confidence_score=0.9,
            estimated_competition="Low",
            estimated_demand="High",
            estimated_revenue=10,
            status=READY,
        )
        (self.data_root / "production_reports").mkdir(parents=True)
        (self.data_root / "production_reports" / "latest.json").write_text("{}", encoding="utf-8")
        (self.data_root / "jobs" / "old_job" / "listing_images").mkdir(parents=True)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_archive_creation_and_valid_empty_queue(self) -> None:
        with patch.object(reset_production_queue, "DATA_ROOT", self.data_root), patch.object(
            reset_production_queue, "QUEUE_PATH", self.queue_path
        ), patch.object(
            reset_production_queue, "ARCHIVE_ROOT", self.data_root / "archive"
        ):
            archive = reset_production_queue.archive_current_state("20260730_120000")
            queue_path = reset_production_queue.reset_queue()

        self.assertTrue((archive / "production_queue" / "queue.json").exists())
        self.assertTrue((archive / "production_reports" / "latest.json").exists())
        self.assertEqual(queue_path, self.queue_path)
        loaded = ProductionQueueManager(queue_path=self.queue_path)
        self.assertEqual(loaded.list_jobs(), ())
        payload = json.loads(self.queue_path.read_text(encoding="utf-8"))
        self.assertEqual(payload["job_count"], 0)
        self.assertEqual(payload["jobs"], [])

    def test_create_acceptance_job_receives_new_id_and_storybook_override(self) -> None:
        empty_queue_path = self.base_path / "queue.json"
        with patch.object(create_storybook_acceptance_job, "JOBS_DIR", self.base_path / "jobs"):
            job = create_storybook_acceptance_job.create_acceptance_job(empty_queue_path)

        self.assertTrue(job.id)
        self.assertEqual(job.status, READY)
        self.assertEqual(job.product_name, "Rabbit Garden Tea Party Watercolor Clipart")
        self.assertEqual(_job_generation_override(job), GENERATION_MODE_STORYBOOK)

    def test_storybook_acceptance_gate_rejects_missing_scene_before_etsy(self) -> None:
        job = _acceptance_job("job-accept")
        paths = ProductFactoryPaths(jobs_dir=self.base_path / "jobs").for_job(job)
        paths.final_images_dir.mkdir(parents=True)
        for index in range(1, 5):
            _write_transparent_png(paths.final_images_dir / f"customer_{index}.png")
        art_package = build_art_direction_package(
            product_name=job.product_name,
            product_category=job.category,
            style=job.style,
            season=job.seasonal_theme,
            palette="warm cream, sage green, muted blue, soft coral",
            mood="cozy tea party",
        )
        _save_art_direction_package(paths, art_package)

        with self.assertRaises(ProductFactoryStageError) as raised:
            _verify_storybook_acceptance_gate(
                job,
                paths,
                {
                    "generation_mode": GENERATION_MODE_STORYBOOK,
                    "listing_family": GENERATION_MODE_STORYBOOK,
                    "art_direction_fingerprint": art_package.fingerprint,
                },
            )

        self.assertEqual(raised.exception.stage, "storybook_acceptance_gate")
        self.assertIn("Expected exactly 4 storybook scenes", str(raised.exception))

    def test_storybook_acceptance_gate_passes_complete_clean_assets(self) -> None:
        job = _acceptance_job("job-pass")
        paths = ProductFactoryPaths(jobs_dir=self.base_path / "jobs").for_job(job)
        paths.final_images_dir.mkdir(parents=True)
        paths.storybook_scenes_dir.mkdir(parents=True)
        for index in range(1, 5):
            _write_transparent_png(paths.final_images_dir / f"customer_{index}.png")
        scene_path = paths.storybook_scenes_dir / "scene_01.png"
        for index in range(1, 5):
            _write_opaque_scene(paths.storybook_scenes_dir / f"scene_{index:02d}.png")
        art_package = build_art_direction_package(
            product_name=job.product_name,
            product_category=job.category,
            style=job.style,
            season=job.seasonal_theme,
            palette="warm cream, sage green, muted blue, soft coral",
            mood="cozy tea party",
        )
        _write_asset_manifest(paths.storybook_scenes_dir, art_package.fingerprint, "storybook_scene")

        _verify_storybook_acceptance_gate(
            job,
            paths,
            {
                "generation_mode": GENERATION_MODE_STORYBOOK,
                "listing_family": GENERATION_MODE_STORYBOOK,
                "art_direction_fingerprint": art_package.fingerprint,
            },
        )

        self.assertEqual(len(tuple(paths.listing_images_dir.glob("*.png"))), 4)
        manifest = json.loads((paths.listing_images_dir / "preview_manifest.json").read_text())
        self.assertEqual(manifest["primary_preview_source"], str(scene_path))
        self.assertEqual(manifest["art_direction_fingerprint"], art_package.fingerprint)
        self.assertEqual(manifest["preview_renderer"], "STORYBOOK_NATURE_FULL_CANVAS")
        self.assertEqual(len(manifest["storybook_scene_sources"]), 4)


def _acceptance_job(job_id: str) -> ProductionJob:
    return ProductionJob(
        id=job_id,
        priority="High",
        product_name="Rabbit Garden Tea Party Watercolor Clipart",
        category="Digital Clipart",
        style="Whimsical Storybook Watercolor",
        seasonal_theme="Spring",
        keywords=("rabbit", "tea party", "watercolor"),
        confidence_score=0.99,
        estimated_competition="Low",
        estimated_demand="High",
        estimated_revenue=120,
        status=READY,
        source_evidence=("generation_mode=STORYBOOK",),
    )


def _write_transparent_png(path: Path) -> None:
    image = Image.new("RGBA", (4000, 4000), (255, 255, 255, 0))
    for x in range(800, 3200):
        for y in range(800, 3200):
            image.putpixel((x, y), (120, 80, 40, 255))
    image.save(path, format="PNG", dpi=(300, 300))


def _write_opaque_scene(path: Path) -> None:
    image = Image.new("RGBA", (1200, 1200), (120, 160, 120, 255))
    for x in range(1200):
        for y in range(1200):
            image.putpixel((x, y), ((x * 5) % 255, (y * 3) % 255, 120, 255))
    image.save(path, format="PNG", dpi=(300, 300))


if __name__ == "__main__":
    unittest.main()
