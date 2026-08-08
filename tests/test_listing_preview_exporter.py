"""Tests for Etsy listing preview image export."""

from __future__ import annotations

import sys
import tempfile
import unittest
import json
from pathlib import Path

from PIL import Image, ImageDraw

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_PATH))

from project_aurora.image_generation.listing_family_decision import (  # noqa: E402
    LISTING_FAMILY_CLIPART,
    LISTING_FAMILY_STORYBOOK,
)
from project_aurora.image_generation.listing_preview_exporter import (  # noqa: E402
    ListingPreviewExporter,
    PREVIEW_SIZE,
    _opaque_occupancy,
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

    def test_creates_transparent_clipart_preview_images(self) -> None:
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
        self.assertEqual(corner[3], 0)
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
        for index in range(1, 5):
            write_storybook_scene(scene_dir / f"fox_garden_scene_{index}.png")

        result = ListingPreviewExporter(
            final_images_dir=self.final_dir,
            storybook_scenes_dir=scene_dir,
            output_dir=self.preview_dir,
            output_prefix="fox_garden",
        ).export()

        self.assertEqual(result.status, "SUCCESS")
        self.assertEqual(len(result.preview_files), 4)
        self.assertEqual(Path(result.preview_files[0]).name, "fox_garden_preview_01.png")

    def test_clipart_family_ignores_existing_storybook_scene(self) -> None:
        scene_dir = self.base_path / "storybook_scenes"
        scene_dir.mkdir()
        write_storybook_scene(scene_dir / "fox_garden_scene.png")

        result = ListingPreviewExporter(
            final_images_dir=self.final_dir,
            storybook_scenes_dir=scene_dir,
            output_dir=self.preview_dir,
            output_prefix="fox_garden",
            listing_family=LISTING_FAMILY_CLIPART,
        ).export()

        self.assertEqual(result.status, "SUCCESS")
        self.assertEqual(len(result.preview_files), 4)
        self.assertEqual(Path(result.preview_files[0]).name, "fox_garden_preview_01.png")

    def test_storybook_family_without_scene_falls_back_to_clipart(self) -> None:
        result = ListingPreviewExporter(
            final_images_dir=self.final_dir,
            output_dir=self.preview_dir,
            output_prefix="fox_garden",
            listing_family=LISTING_FAMILY_STORYBOOK,
        ).export()

        self.assertEqual(result.status, "SUCCESS")
        self.assertEqual(len(result.preview_files), 4)

    def test_storybook_primary_scene_occupies_most_canvas(self) -> None:
        scene_dir = self.base_path / "storybook_scenes"
        scene_dir.mkdir()
        for index in range(1, 5):
            write_storybook_scene(scene_dir / f"fox_garden_scene_{index}.png")

        result = ListingPreviewExporter(
            final_images_dir=self.final_dir,
            storybook_scenes_dir=scene_dir,
            output_dir=self.preview_dir,
            output_prefix="fox_garden",
            listing_family=LISTING_FAMILY_STORYBOOK,
        ).export()

        self.assertEqual(result.status, "SUCCESS")
        with Image.open(result.preview_files[0]) as image:
            pixels = image.convert("RGBA")
            center = pixels.getpixel((PREVIEW_SIZE[0] // 2, PREVIEW_SIZE[1] // 2))
            margin = pixels.getpixel((30, 30))
        self.assertNotEqual(center, margin)

    def test_storybook_primary_preview_uses_full_canvas_without_grid_template(self) -> None:
        scene_dir = self.base_path / "storybook_scenes"
        scene_dir.mkdir()
        for index in range(1, 5):
            write_storybook_scene(scene_dir / f"fox_garden_scene_{index}.png")

        result = ListingPreviewExporter(
            final_images_dir=self.final_dir,
            storybook_scenes_dir=scene_dir,
            output_dir=self.preview_dir,
            output_prefix="fox_garden",
            listing_family=LISTING_FAMILY_STORYBOOK,
        ).export()

        self.assertEqual(result.status, "SUCCESS")
        with Image.open(result.preview_files[0]) as image:
            preview = image.convert("RGBA")
            corner = preview.getpixel((10, 10))
            occupancy = _opaque_occupancy(preview)
        self.assertGreaterEqual(occupancy[0], 0.85)
        self.assertGreaterEqual(occupancy[1], 0.85)
        self.assertLess(corner[0], 180)
        self.assertLess(corner[1], 200)

    def test_clipart_preview_keeps_transparency_preview_background(self) -> None:
        result = ListingPreviewExporter(
            final_images_dir=self.final_dir,
            output_dir=self.preview_dir,
            output_prefix="fox_garden",
            listing_family=LISTING_FAMILY_CLIPART,
        ).export()

        self.assertEqual(result.status, "SUCCESS")
        with Image.open(result.preview_files[0]) as image:
            corner = image.convert("RGBA").getpixel((10, 10))
        self.assertEqual(corner[3], 0)

    def test_storybook_listing_uses_four_scene_previews(self) -> None:
        scene_dir = self.base_path / "storybook_scenes"
        scene_dir.mkdir()
        for index in range(1, 5):
            write_storybook_scene(scene_dir / f"fox_garden_scene_{index}.png")

        result = ListingPreviewExporter(
            final_images_dir=self.final_dir,
            storybook_scenes_dir=scene_dir,
            output_dir=self.preview_dir,
            output_prefix="fox_garden",
            listing_family=LISTING_FAMILY_STORYBOOK,
        ).export()

        self.assertEqual(result.status, "SUCCESS")
        manifest = json.loads((self.preview_dir / "preview_manifest.json").read_text())
        self.assertEqual(manifest["preview_renderer"], "STORYBOOK_NATURE_FULL_CANVAS")
        self.assertEqual(len(result.preview_files), 4)
        self.assertEqual(len(manifest["storybook_scene_sources"]), 4)


if __name__ == "__main__":
    unittest.main()
