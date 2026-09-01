"""Tests for final commercial image export."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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
from project_aurora.production.product_image_family import (  # noqa: E402
    STORYBOOK_SCENE,
    resolve_product_image_family,
)
from project_aurora.production.generation_strategy import (  # noqa: E402
    GENERATION_MODE_CHARACTERS,
    GENERATION_MODE_DIGITAL_PAPER,
    GENERATION_MODE_WEDDING,
)


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
            path = self.source_dir / f"source_{index:02d}.png"
            image = Image.new("RGBA", (32, 32), (255, 0, 0, 0))
            for x in range(8, 24):
                for y in range(8, 24):
                    image.putpixel((x, y), (255, index * 20, 0, 255))
            image.save(path, format="PNG")

    def test_exports_exactly_four_4000_pngs_with_300_dpi(self) -> None:
        self.write_valid_sources()

        result = CommercialImageExporter(
            source_dir=self.source_dir,
            output_dir=self.output_dir,
        ).export()

        self.assertEqual(result.status, "SUCCESS")
        self.assertEqual(len(result.exported_files), 4)
        self.assertEqual(
            Path(result.exported_files[0]).name,
            "aurora_watercolor_clipart_01.png",
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
            for x in range(8, 24):
                for y in range(8, 24):
                    image.putpixel((x, y), (255, 0, 0, 255))
            image.save(path, format="PNG")

        result = CommercialImageExporter(
            source_dir=self.source_dir,
            output_dir=self.output_dir,
        ).export()

        self.assertEqual(result.status, "SUCCESS")
        inspection = inspect_png(Path(result.exported_files[0]))
        self.assertEqual(inspection.alpha_minimum, 0)
        self.assertEqual(inspection.alpha_maximum, 255)

    def test_source_artwork_is_upscaled_inside_4000_canvas(self) -> None:
        for index in range(1, 5):
            path = self.source_dir / f"small_{index:02d}.png"
            image = Image.new("RGBA", (1024, 1024), (255, 0, 0, 0))
            for x in range(400, 624):
                for y in range(400, 624):
                    image.putpixel((x, y), (255, 0, 0, 255))
            image.save(path, format="PNG")

        result = CommercialImageExporter(
            source_dir=self.source_dir,
            output_dir=self.output_dir,
        ).export()

        self.assertEqual(result.status, "SUCCESS")
        with Image.open(result.exported_files[0]) as image:
            bbox = image.convert("RGBA").getchannel("A").getbbox()
        self.assertIsNotNone(bbox)
        assert bbox is not None
        self.assertGreaterEqual(bbox[2] - bbox[0], 3300)

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

    def test_storybook_scene_exports_opaque_full_background(self) -> None:
        for index in range(1, 5):
            write_png(
                self.source_dir / f"scene_{index:02d}.png",
                (80, 120, 160, 255),
                size=(1024, 1024),
            )

        result = CommercialImageExporter(
            source_dir=self.source_dir,
            output_dir=self.output_dir,
            product_family=STORYBOOK_SCENE,
        ).export()

        self.assertEqual(result.status, "SUCCESS")
        inspection = inspect_png(Path(result.exported_files[0]))
        self.assertEqual(inspection.dimensions, COMMERCIAL_IMAGE_SIZE)
        self.assertEqual(inspection.alpha_minimum, 255)
        self.assertEqual(inspection.alpha_maximum, 255)
        self.assertEqual(
            validate_commercial_png(
                Path(result.exported_files[0]),
                product_family=STORYBOOK_SCENE,
            ),
            (),
        )

    def test_character_family_requires_transparent_png(self) -> None:
        for index in range(1, 5):
            write_png(
                self.source_dir / f"character_{index:02d}.png",
                (80, 120, 160, 255),
                size=(1024, 1024),
            )

        result = CommercialImageExporter(
            source_dir=self.source_dir,
            output_dir=self.output_dir,
            product_family=GENERATION_MODE_CHARACTERS,
        ).export()

        self.assertEqual(result.status, "FAILED")
        self.assertTrue(any("TRANSPARENCY_REQUIRED" in error for error in result.errors))

    def test_digital_paper_exports_as_opaque_without_clipart_transparency_rule(self) -> None:
        for index in range(1, 5):
            write_png(
                self.source_dir / f"paper_{index:02d}.png",
                (80, 120, 160, 255),
                size=(1024, 1024),
            )

        result = CommercialImageExporter(
            source_dir=self.source_dir,
            output_dir=self.output_dir,
            product_family=GENERATION_MODE_DIGITAL_PAPER,
        ).export()

        self.assertEqual(result.status, "SUCCESS")
        self.assertEqual(validate_commercial_png(Path(result.exported_files[0]), product_family=GENERATION_MODE_DIGITAL_PAPER), ())

    def test_optimized_digital_paper_does_not_reintroduce_palette_alpha(self) -> None:
        for index in range(1, 5):
            write_png(
                self.source_dir / f"paper_{index:02d}.png",
                (80, 120, 160, 255),
                size=(64, 64),
            )

        with patch(
            "project_aurora.image_generation.commercial_image_exporter.MAX_SINGLE_PNG_SIZE_BYTES",
            1,
        ):
            result = CommercialImageExporter(
                source_dir=self.source_dir,
                output_dir=self.output_dir,
                product_family=GENERATION_MODE_DIGITAL_PAPER,
            ).export()

        self.assertEqual(result.status, "SUCCESS")
        output = Path(result.exported_files[0])
        with Image.open(output) as image:
            self.assertNotIn("transparency", image.info)
        self.assertEqual(
            validate_commercial_png(
                output,
                product_family=GENERATION_MODE_DIGITAL_PAPER,
            ),
            (),
        )

    def test_wedding_exports_as_transparent_separated_assets(self) -> None:
        self.write_valid_sources()

        result = CommercialImageExporter(
            source_dir=self.source_dir,
            output_dir=self.output_dir,
            product_family=GENERATION_MODE_WEDDING,
        ).export()

        self.assertEqual(result.status, "SUCCESS")
        output = Path(result.exported_files[0])
        self.assertLess(inspect_png(output).alpha_minimum, 255)
        self.assertEqual(
            validate_commercial_png(output, product_family=GENERATION_MODE_WEDDING),
            (),
        )

    def test_wedding_rejects_opaque_stationery_page(self) -> None:
        for index in range(1, 5):
            write_png(
                self.source_dir / f"wedding_{index:02d}.png",
                (245, 238, 224, 255),
                size=(1024, 1024),
            )

        result = CommercialImageExporter(
            source_dir=self.source_dir,
            output_dir=self.output_dir,
            product_family=GENERATION_MODE_WEDDING,
        ).export()

        self.assertEqual(result.status, "FAILED")
        self.assertTrue(result.errors)

    def test_product_family_resolves_clipart_storybook_scene_and_digital_paper(self) -> None:
        clipart = resolve_product_image_family(
            "Woodland Animal Clipart",
            "clipart collection",
        )
        scene = resolve_product_image_family(
            "Woodland Tea Party",
            "storybook scene collection",
        )
        digital_paper = resolve_product_image_family(
            "Sage Botanical Digital Paper",
            "digital_paper",
        )

        self.assertTrue(clipart.transparent_background)
        self.assertEqual(clipart.openai_background, "transparent")
        self.assertFalse(scene.transparent_background)
        self.assertEqual(scene.openai_background, "opaque")
        self.assertEqual(digital_paper.family, GENERATION_MODE_DIGITAL_PAPER)
        self.assertFalse(digital_paper.transparent_background)
        self.assertEqual(digital_paper.openai_background, "opaque")


if __name__ == "__main__":
    unittest.main()
