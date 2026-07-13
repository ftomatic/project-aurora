"""Tests for customer digital download ZIP packaging."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_PATH))

from project_aurora.production.digital_download_builder import (  # noqa: E402
    DIGITAL_DOWNLOAD_FILENAME,
    DigitalDownloadBuilder,
)


def write_final_png(path: Path, size: tuple[int, int] = (3600, 3600)) -> None:
    Image.new("RGBA", size, (255, 0, 0, 255)).save(
        path,
        format="PNG",
        dpi=(300, 300),
    )


class DigitalDownloadBuilderTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base_path = Path(self.temp_dir.name)
        self.final_images_dir = self.base_path / "final_product_images"
        self.output_dir = self.base_path / "digital_downloads"
        self.final_images_dir.mkdir()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def write_four_images(self) -> None:
        for index in range(1, 5):
            write_final_png(
                self.final_images_dir
                / f"strawberry_birthday_party_printable_{index:02d}.png"
            )

    def test_builds_zip_with_only_four_final_pngs(self) -> None:
        self.write_four_images()

        result = DigitalDownloadBuilder(
            final_images_dir=self.final_images_dir,
            output_dir=self.output_dir,
        ).build()

        self.assertEqual(result.status, "SUCCESS")
        self.assertEqual(Path(result.zip_path or "").name, DIGITAL_DOWNLOAD_FILENAME)
        self.assertTrue(Path(result.zip_path or "").stat().st_size > 0)
        with ZipFile(result.zip_path or "", "r") as archive:
            entries = archive.namelist()

        self.assertEqual(len(entries), 4)
        self.assertTrue(all(entry.endswith(".png") for entry in entries))
        self.assertFalse(any("/" in entry for entry in entries))
        self.assertFalse(any("metadata" in entry for entry in entries))

    def test_rejects_more_or_fewer_than_four_files(self) -> None:
        write_final_png(self.final_images_dir / "one.png")

        result = DigitalDownloadBuilder(
            final_images_dir=self.final_images_dir,
            output_dir=self.output_dir,
        ).build()

        self.assertEqual(result.status, "FAILED")
        self.assertIn("Expected exactly 4", result.errors[0])

    def test_rejects_source_sized_images(self) -> None:
        for index in range(1, 5):
            write_final_png(
                self.final_images_dir / f"image_{index}.png",
                size=(1024, 1024),
            )

        result = DigitalDownloadBuilder(
            final_images_dir=self.final_images_dir,
            output_dir=self.output_dir,
        ).build()

        self.assertEqual(result.status, "FAILED")
        self.assertTrue(any("3600x3600" in error for error in result.errors))


if __name__ == "__main__":
    unittest.main()
