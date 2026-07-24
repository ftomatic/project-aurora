"""Tests for final commercial image export."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_PATH))

from project_aurora.image_generation.commercial_image_exporter import (  # noqa: E402
    COMMERCIAL_IMAGE_SIZE,
    DIGITAL_PAPER_JPEG_QUALITY,
    DIGITAL_PAPER_IMAGE_SIZE,
    DIGITAL_PAPER_MIN_SHARPNESS,
    DIGITAL_PAPER_PREVIEW_SIZE,
    PARTY_PRINTABLE_IMAGE_SIZE,
    PARTY_PRINTABLE_PREVIEW_SIZE,
    STICKER_IMAGE_SIZE,
    STICKER_PREVIEW_SIZE,
    WALL_ART_RATIOS,
    WALL_ART_MIN_SHARPNESS,
    CommercialImageExporter,
    validate_commercial_jpg,
    validate_commercial_png,
)
from project_aurora.image_generation.image_inspector import inspect_png  # noqa: E402


def write_png(
    path: Path,
    color: tuple[int, int, int, int],
    size: tuple[int, int] = (32, 32),
) -> None:
    Image.new("RGBA", size, color).save(path, format="PNG")


def write_quadrant_png(path: Path, size: tuple[int, int] = (100, 100)) -> None:
    image = Image.new("RGBA", size, (255, 255, 255, 255))
    half_width = size[0] // 2
    half_height = size[1] // 2
    for x in range(size[0]):
        for y in range(size[1]):
            if x < half_width and y < half_height:
                image.putpixel((x, y), (255, 0, 0, 255))
            elif x >= half_width and y < half_height:
                image.putpixel((x, y), (0, 255, 0, 255))
            elif x < half_width and y >= half_height:
                image.putpixel((x, y), (0, 0, 255, 255))
            else:
                image.putpixel((x, y), (255, 255, 0, 255))
            if (x + y) % 4 in {0, 1}:
                current = image.getpixel((x, y))
                image.putpixel(
                    (x, y),
                    (
                        max(0, current[0] - 80),
                        max(0, current[1] - 80),
                        max(0, current[2] - 80),
                        255,
                    ),
                )
    image.save(path, format="PNG")


def write_sharp_pattern_png(path: Path, size: tuple[int, int] = (256, 256)) -> None:
    image = Image.new("RGBA", size, (255, 255, 255, 255))
    for x in range(size[0]):
        for y in range(size[1]):
            if ((x // 8) + (y // 8)) % 2 == 0:
                image.putpixel((x, y), (20, 120, 100, 255))
            else:
                image.putpixel((x, y), (255, 235, 80, 255))
    image.save(path, format="PNG")


def assert_color_close(
    test_case: unittest.TestCase,
    actual: tuple[int, int, int],
    expected: tuple[int, int, int],
    tolerance: int = 35,
) -> None:
    for actual_channel, expected_channel in zip(actual, expected):
        test_case.assertLessEqual(abs(actual_channel - expected_channel), tolerance)


class CommercialImageExporterTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base_path = Path(self.temp_dir.name)
        self.source_dir = self.base_path / "generated_images"
        self.output_dir = self.base_path / "final_product_images"
        self.source_dir.mkdir()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def write_valid_sources(self) -> None:
        for index in range(1, 5):
            write_png(
                self.source_dir / f"source_{index:02d}.png",
                (255, index * 20, 0, 255),
            )

    def write_valid_source_count(self, count: int) -> None:
        for index in range(1, count + 1):
            write_png(
                self.source_dir / f"source_{index:02d}.png",
                (255, index * 20, 0, 255),
            )

    def test_exports_1024_sources_to_4000_pngs_with_300_dpi(self) -> None:
        for index in range(1, 5):
            write_png(
                self.source_dir / f"source_{index:02d}.png",
                (255, index * 20, 0, 255),
                size=(1024, 1024),
            )

        result = CommercialImageExporter(
            source_dir=self.source_dir,
            output_dir=self.output_dir,
        ).export()

        self.assertEqual(result.status, "SUCCESS")
        self.assertEqual(len(result.exported_files), 4)
        self.assertEqual(
            Path(result.exported_files[0]).name,
            "strawberry_birthday_party_printable_01.png",
        )
        for exported_file in result.exported_files:
            path = Path(exported_file)
            self.assertEqual(validate_commercial_png(path), ())
            with Image.open(path) as image:
                self.assertEqual(image.size, COMMERCIAL_IMAGE_SIZE)
                self.assertGreaterEqual(max(image.size), 4000)
                dpi = image.info["dpi"]
                self.assertAlmostEqual(float(dpi[0]), 300, delta=1)
                self.assertAlmostEqual(float(dpi[1]), 300, delta=1)

    def test_transparency_is_preserved(self) -> None:
        for index in range(1, 5):
            path = self.source_dir / f"source_{index:02d}.png"
            image = Image.new("RGBA", (32, 32), (255, 0, 0, 0))
            image.putpixel((0, 0), (255, 0, 0, 255))
            image.save(path, format="PNG")

        result = CommercialImageExporter(
            source_dir=self.source_dir,
            output_dir=self.output_dir,
        ).export()

        self.assertEqual(result.status, "SUCCESS")
        inspection = inspect_png(Path(result.exported_files[0]))
        self.assertEqual(inspection.alpha_minimum, 0)
        self.assertEqual(inspection.alpha_maximum, 255)

    def test_rejects_fewer_or_more_than_four_valid_sources(self) -> None:
        write_png(self.source_dir / "one.png", (255, 0, 0, 255))

        result = CommercialImageExporter(
            source_dir=self.source_dir,
            output_dir=self.output_dir,
        ).export()

        self.assertEqual(result.status, "FAILED")
        self.assertIn("Expected exactly 4", result.errors[0])

    def test_exports_five_sources_when_required_count_is_five(self) -> None:
        self.write_valid_source_count(5)

        result = CommercialImageExporter(
            source_dir=self.source_dir,
            output_dir=self.output_dir,
            required_count=5,
        ).export()

        self.assertEqual(result.status, "SUCCESS")
        self.assertEqual(len(result.exported_files), 5)
        for exported_file in result.exported_files:
            with Image.open(exported_file) as image:
                self.assertEqual(image.size, COMMERCIAL_IMAGE_SIZE)

    def test_rejects_four_sources_when_five_are_required(self) -> None:
        self.write_valid_source_count(4)

        result = CommercialImageExporter(
            source_dir=self.source_dir,
            output_dir=self.output_dir,
            required_count=5,
        ).export()

        self.assertEqual(result.status, "FAILED")
        self.assertIn("Expected exactly 5", result.errors[0])

    def test_exports_printable_wall_art_jpg_ratios_and_preview(self) -> None:
        for index in range(1, 6):
            write_sharp_pattern_png(self.source_dir / f"source_{index:02d}.png")
        self.output_dir.mkdir()
        write_png(self.output_dir / "stale_square.png", (255, 0, 0, 255))

        result = CommercialImageExporter(
            source_dir=self.source_dir,
            output_dir=self.output_dir,
            required_count=5,
            category="Printable Wall Art",
        ).export()

        self.assertEqual(result.status, "SUCCESS")
        self.assertEqual(len(result.exported_files), 5)
        for exported_file, (label, size) in zip(result.exported_files, WALL_ART_RATIOS):
            path = Path(exported_file)
            self.assertEqual(path.suffix, ".jpg")
            self.assertIn(label, path.stem)
            self.assertEqual(validate_commercial_jpg(path, size), ())
            with Image.open(path) as image:
                self.assertEqual(image.size, size)
                self.assertEqual(image.mode, "RGB")
        preview = self.output_dir / "lifestyle_preview.jpg"
        self.assertTrue(preview.exists())
        self.assertEqual(validate_commercial_jpg(preview, (1800, 1200)), ())
        self.assertFalse((self.output_dir / "stale_square.png").exists())

    def test_printable_wall_art_export_rejects_blurry_ratio_files(self) -> None:
        for index in range(1, 6):
            image = Image.new("RGBA", (256, 256), (230, 230, 220, 255))
            image.save(self.source_dir / f"source_{index:02d}.png", format="PNG")

        result = CommercialImageExporter(
            source_dir=self.source_dir,
            output_dir=self.output_dir,
            required_count=5,
            category="Printable Wall Art",
        ).export()

        self.assertEqual(result.status, "FAILED")
        self.assertTrue(any("too blurry" in error for error in result.errors))
        self.assertGreater(WALL_ART_MIN_SHARPNESS, 0)

    def test_printable_wall_art_ratio_export_preserves_full_artwork(self) -> None:
        for index in range(1, 6):
            write_sharp_pattern_png(
                self.source_dir / f"source_{index:02d}.png",
            )

        result = CommercialImageExporter(
            source_dir=self.source_dir,
            output_dir=self.output_dir,
            required_count=5,
            category="Printable Wall Art",
        ).export()

        self.assertEqual(result.status, "SUCCESS")
        first_ratio_path = self.output_dir / "printable_wall_art_2x3.jpg"
        with Image.open(first_ratio_path) as image:
            self.assertEqual(image.size, WALL_ART_RATIOS[0][1])
            self.assertEqual(image.getpixel((image.width // 2, 20)), (255, 255, 255))
            self.assertEqual(
                image.getpixel((image.width // 2, image.height - 20)),
                (255, 255, 255),
            )
            self.assertNotEqual(
                image.getpixel((image.width // 2, image.height // 2)),
                (255, 255, 255),
            )

    def test_exports_digital_paper_jpgs_and_collage_preview(self) -> None:
        for index in range(1, 13):
            write_sharp_pattern_png(self.source_dir / f"source_{index:02d}.png")

        result = CommercialImageExporter(
            source_dir=self.source_dir,
            output_dir=self.output_dir,
            required_count=12,
            category="Digital Paper",
        ).export()

        self.assertEqual(result.status, "SUCCESS")
        self.assertEqual(len(result.exported_files), 12)
        for index, exported_file in enumerate(result.exported_files, start=1):
            path = Path(exported_file)
            self.assertEqual(path.name, f"digital_paper_{index:02d}.jpg")
            self.assertEqual(validate_commercial_jpg(path, DIGITAL_PAPER_IMAGE_SIZE), ())
        preview = self.output_dir / "collage_preview.jpg"
        self.assertTrue(preview.exists())
        self.assertEqual(validate_commercial_jpg(preview, DIGITAL_PAPER_PREVIEW_SIZE), ())
        self.assertLessEqual(DIGITAL_PAPER_JPEG_QUALITY, 90)

    def test_digital_paper_export_rejects_blurry_customer_files(self) -> None:
        for index in range(1, 13):
            path = self.source_dir / f"source_{index:02d}.png"
            image = Image.new("RGBA", (256, 256), (250, 210, 90, 255))
            image.save(path, format="PNG")

        result = CommercialImageExporter(
            source_dir=self.source_dir,
            output_dir=self.output_dir,
            required_count=12,
            category="Digital Paper",
        ).export()

        self.assertEqual(result.status, "FAILED")
        self.assertTrue(any("too blurry" in error for error in result.errors))
        self.assertGreater(DIGITAL_PAPER_MIN_SHARPNESS, 0)

    def test_exports_party_printable_jpgs_and_bundle_preview(self) -> None:
        self.write_valid_source_count(4)

        result = CommercialImageExporter(
            source_dir=self.source_dir,
            output_dir=self.output_dir,
            required_count=4,
            category="Party Printables",
        ).export()

        self.assertEqual(result.status, "SUCCESS")
        self.assertEqual(len(result.exported_files), 4)
        for index, exported_file in enumerate(result.exported_files, start=1):
            path = Path(exported_file)
            self.assertEqual(path.name, f"party_printable_{index:02d}.jpg")
            self.assertEqual(validate_commercial_jpg(path, PARTY_PRINTABLE_IMAGE_SIZE), ())
        preview = self.output_dir / "bundle_preview.jpg"
        self.assertTrue(preview.exists())
        self.assertEqual(validate_commercial_jpg(preview, PARTY_PRINTABLE_PREVIEW_SIZE), ())

    def test_exports_sticker_sheet_pngs_and_preview(self) -> None:
        for index in range(1, 9):
            path = self.source_dir / f"source_{index:02d}.png"
            image = Image.new("RGBA", (64, 64), (255, 255, 255, 255))
            for x in range(16, 48):
                for y in range(16, 48):
                    image.putpixel((x, y), (40, 160, 90, 255))
            image.save(path, format="PNG")

        result = CommercialImageExporter(
            source_dir=self.source_dir,
            output_dir=self.output_dir,
            required_count=8,
            category="Stickers",
        ).export()

        self.assertEqual(result.status, "SUCCESS", result.errors)
        self.assertEqual(len(result.exported_files), 8)
        for index, exported_file in enumerate(result.exported_files, start=1):
            path = Path(exported_file)
            self.assertEqual(path.name, f"sticker_{index:02d}.png")
            self.assertEqual(validate_commercial_png(path), ())
            with Image.open(path) as image:
                self.assertEqual(image.size, STICKER_IMAGE_SIZE)
                self.assertEqual(image.mode, "RGBA")
                self.assertEqual(image.getchannel("A").getextrema()[0], 0)
                self.assertEqual(image.getchannel("A").getextrema()[1], 255)
        preview = self.output_dir / "sticker_sheet_preview.png"
        self.assertTrue(preview.exists())
        with Image.open(preview) as image:
            self.assertEqual(image.size, STICKER_PREVIEW_SIZE)

    def test_rejects_invalid_and_blank_sources(self) -> None:
        write_png(self.source_dir / "valid_01.png", (255, 0, 0, 255))
        write_png(self.source_dir / "transparent.png", (255, 0, 0, 0))
        write_png(self.source_dir / "white.png", (255, 255, 255, 255))
        (self.source_dir / "invalid.png").write_bytes(b"not-a-png")

        result = CommercialImageExporter(
            source_dir=self.source_dir,
            output_dir=self.output_dir,
        ).export()

        self.assertEqual(result.status, "FAILED")
        self.assertIn("found 1", result.errors[0])


if __name__ == "__main__":
    unittest.main()
