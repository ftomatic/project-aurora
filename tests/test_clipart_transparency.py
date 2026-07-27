"""Tests for true transparent clipart output validation and repair."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

from PIL import Image, ImageDraw

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_PATH))

from project_aurora.image_generation.clipart_transparency import (  # noqa: E402
    TRANSPARENCY_REQUIRED,
    ensure_clipart_transparency,
    validate_clipart_file,
)
from project_aurora.image_generation.commercial_image_exporter import (  # noqa: E402
    CommercialImageExporter,
    validate_commercial_png,
)
from project_aurora.production.digital_download_builder import (  # noqa: E402
    DigitalDownloadBuilder,
)
from project_aurora.production.product_image_family import (  # noqa: E402
    CLIPART,
    STORYBOOK_SCENE,
)


class ClipartTransparencyTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base_path = Path(self.temp_dir.name)
        self.source_dir = self.base_path / "source"
        self.final_dir = self.base_path / "final"
        self.zip_dir = self.base_path / "zip"
        self.source_dir.mkdir()
        self.final_dir.mkdir()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_opaque_cream_background_is_repaired_to_true_alpha(self) -> None:
        image = Image.new("RGBA", (128, 128), (240, 232, 214, 255))
        for x in range(44, 84):
            for y in range(44, 84):
                image.putpixel((x, y), (120, 70, 40, 255))

        repaired, result = ensure_clipart_transparency(image)

        self.assertEqual(result.status, "PASS")
        self.assertTrue(result.background_removal_attempted)
        self.assertLess(repaired.getpixel((0, 0))[3], 32)
        self.assertEqual(repaired.getpixel((64, 64))[3], 255)

    def test_grid_background_is_not_accepted_as_transparency(self) -> None:
        path = self.final_dir / "grid.png"
        image = Image.new("RGBA", (4000, 4000), (244, 238, 222, 255))
        draw = ImageDraw.Draw(image)
        for index in range(0, 4000, 200):
            draw.line((0, index, 3999, index), fill=(220, 214, 200, 255))
            draw.line((index, 0, index, 3999), fill=(220, 214, 200, 255))
        image.save(path, format="PNG", dpi=(300, 300))

        errors = validate_commercial_png(path, product_family=CLIPART)

        self.assertTrue(any(TRANSPARENCY_REQUIRED in error for error in errors))

    def test_fake_checkerboard_background_is_not_transparency(self) -> None:
        path = self.final_dir / "checker.png"
        image = Image.new("RGBA", (4000, 4000), (255, 255, 255, 255))
        draw = ImageDraw.Draw(image)
        for x in range(0, 4000, 80):
            for y in range(0, 4000, 80):
                color = (230, 230, 230, 255) if (x // 80 + y // 80) % 2 else (255, 255, 255, 255)
                draw.rectangle((x, y, min(x + 79, 3999), min(y + 79, 3999)), fill=color)
        image.save(path, format="PNG", dpi=(300, 300))

        result = validate_clipart_file(path)

        self.assertEqual(result.status, "FAIL")
        self.assertEqual(result.final_validation_result, TRANSPARENCY_REQUIRED)

    def test_true_transparent_png_passes(self) -> None:
        path = self.final_dir / "transparent.png"
        image = Image.new("RGBA", (4000, 4000), (255, 0, 0, 0))
        ImageDraw.Draw(image).rectangle((1200, 1200, 2800, 2800), fill=(120, 60, 40, 255))
        image.save(path, format="PNG", dpi=(300, 300))

        self.assertEqual(validate_commercial_png(path, product_family=CLIPART), ())

    def test_white_fur_inside_artwork_is_preserved(self) -> None:
        image = Image.new("RGBA", (128, 128), (242, 236, 220, 255))
        for x in range(40, 88):
            for y in range(40, 88):
                image.putpixel((x, y), (250, 248, 240, 255))
        for x in range(58, 70):
            for y in range(58, 70):
                image.putpixel((x, y), (80, 50, 35, 255))

        repaired, result = ensure_clipart_transparency(image)

        self.assertEqual(result.status, "PASS")
        self.assertEqual(repaired.getpixel((50, 50))[3], 255)
        self.assertEqual(repaired.getpixel((64, 64))[3], 255)
        self.assertLess(repaired.getpixel((0, 0))[3], 32)

    def test_pale_watercolor_edges_are_preserved_when_not_edge_connected(self) -> None:
        image = Image.new("RGBA", (128, 128), (242, 236, 220, 255))
        for x in range(36, 92):
            for y in range(36, 92):
                image.putpixel((x, y), (210, 190, 170, 255))
        for x in range(44, 84):
            for y in range(44, 84):
                image.putpixel((x, y), (245, 238, 220, 255))

        repaired, result = ensure_clipart_transparency(image)

        self.assertEqual(result.status, "PASS")
        self.assertEqual(repaired.getpixel((44, 44))[3], 255)
        self.assertLess(repaired.getpixel((0, 0))[3], 32)

    def test_clipart_zip_contains_only_transparent_png_files(self) -> None:
        for index in range(1, 5):
            path = self.final_dir / f"clipart_{index:02d}.png"
            image = Image.new("RGBA", (4000, 4000), (255, 0, 0, 0))
            ImageDraw.Draw(image).rectangle((1200, 1200, 2800, 2800), fill=(120, 60, 40, 255))
            image.save(path, format="PNG", dpi=(300, 300))

        result = DigitalDownloadBuilder(
            final_images_dir=self.final_dir,
            output_dir=self.zip_dir,
            product_family=CLIPART,
        ).build()

        self.assertEqual(result.status, "SUCCESS")
        with ZipFile(result.zip_path or "", "r") as archive:
            self.assertEqual(len(archive.namelist()), 4)

    def test_storybook_scene_is_not_sent_through_background_removal(self) -> None:
        for index in range(1, 5):
            Image.new("RGBA", (1024, 1024), (90, 120, 140, 255)).save(
                self.source_dir / f"scene_{index:02d}.png",
                format="PNG",
            )

        result = CommercialImageExporter(
            source_dir=self.source_dir,
            output_dir=self.final_dir,
            product_family=STORYBOOK_SCENE,
        ).export()

        self.assertEqual(result.status, "SUCCESS")
        with Image.open(result.exported_files[0]) as image:
            self.assertEqual(image.convert("RGBA").getpixel((0, 0))[3], 255)


if __name__ == "__main__":
    unittest.main()
