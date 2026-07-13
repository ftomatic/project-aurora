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
    CommercialImageExporter,
    validate_commercial_png,
)
from project_aurora.image_generation.image_inspector import inspect_png  # noqa: E402


def write_png(
    path: Path,
    color: tuple[int, int, int, int],
    size: tuple[int, int] = (32, 32),
) -> None:
    Image.new("RGBA", size, color).save(path, format="PNG")


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

    def test_exports_exactly_four_3600_pngs_with_300_dpi(self) -> None:
        self.write_valid_sources()

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
