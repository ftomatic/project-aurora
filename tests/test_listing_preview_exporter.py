"""Tests for Etsy listing preview image export."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_PATH))

from project_aurora.image_generation.listing_preview_exporter import (  # noqa: E402
    ListingPreviewExporter,
    PREVIEW_SIZE,
)


def write_transparent_art(path: Path) -> None:
    image = Image.new("RGBA", (4000, 4000), (255, 255, 255, 0))
    ImageDraw.Draw(image).ellipse((1000, 800, 3000, 3200), fill=(160, 90, 60, 255))
    image.save(path, format="PNG", dpi=(300, 300))


def write_storybook_scene(path: Path) -> None:
    image = Image.new("RGBA", (2000, 2000), (120, 160, 120, 255))
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 1200, 2000, 2000), fill=(90, 130, 85, 255))
    draw.ellipse((700, 500, 1300, 1500), fill=(180, 100, 70, 255))
    image.save(path, format="PNG", dpi=(300, 300))


class ListingPreviewExporterTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base_path = Path(self.temp_dir.name)
        self.final_dir = self.base_path / "final_product_images"
        self.preview_dir = self.base_path / "listing_images"
        self.final_dir.mkdir()
        for index in range(1, 5):
            write_transparent_art(self.final_dir / f"art_{index:02d}.png")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_creates_cream_background_preview_images(self) -> None:
        result = ListingPreviewExporter(
            final_images_dir=self.final_dir,
            output_dir=self.preview_dir,
            output_prefix="fox_garden",
        ).export()

        self.assertEqual(result.status, "SUCCESS")
        self.assertEqual(len(result.preview_files), 4)
        with Image.open(result.preview_files[0]) as image:
            self.assertEqual(image.size, PREVIEW_SIZE)
            corner = image.convert("RGBA").getpixel((5, 5))
        self.assertGreater(corner[0], 230)
        self.assertGreater(corner[1], 220)
        self.assertGreater(corner[2], 200)
        self.assertEqual(Path(result.preview_files[0]).parent.name, "listing_images")

    def test_rejects_missing_customer_files(self) -> None:
        result = ListingPreviewExporter(
            final_images_dir=self.base_path / "missing",
            output_dir=self.preview_dir,
            output_prefix="missing",
        ).export()

        self.assertEqual(result.status, "FAILED")
        self.assertIn("Expected exactly 4", result.errors[0])

    def test_storybook_scene_becomes_primary_listing_preview(self) -> None:
        scene_dir = self.base_path / "storybook_scenes"
        scene_dir.mkdir()
        write_storybook_scene(scene_dir / "fox_garden_scene.png")

        result = ListingPreviewExporter(
            final_images_dir=self.final_dir,
            storybook_scenes_dir=scene_dir,
            output_dir=self.preview_dir,
            output_prefix="fox_garden",
        ).export()

        self.assertEqual(result.status, "SUCCESS")
        self.assertEqual(len(result.preview_files), 5)
        self.assertEqual(Path(result.preview_files[0]).name, "fox_garden_preview_01.png")
        self.assertEqual(Path(result.preview_files[1]).name, "fox_garden_preview_02.png")


if __name__ == "__main__":
    unittest.main()
