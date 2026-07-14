"""Tests for generated PNG inspection and OpenAI provider validation."""

from __future__ import annotations

import base64
from io import BytesIO
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_PATH))

from project_aurora.image_generation.image_generation_engine import (  # noqa: E402
    ImageGenerationEngine,
)
from project_aurora.image_generation.image_inspector import inspect_png  # noqa: E402
from project_aurora.image_generation.openai_provider import (  # noqa: E402
    OpenAIImageProvider,
)


def make_png_bytes(color: tuple[int, int, int, int]) -> bytes:
    output = BytesIO()
    Image.new("RGBA", (3, 3), color).save(output, format="PNG")
    return output.getvalue()


def make_request() -> object:
    return ImageGenerationEngine.create_request(
        prompt_package={
            "product_name": "Summer Strawberry Birthday",
            "collection": "Summer Strawberry Birthday Collection",
            "style": "Storybook Watercolor",
            "image_prompt": "A visible strawberry party printable.",
        },
        provider_name="OpenAI GPT Image",
        image_type="product_asset",
        width=1024,
        height=1024,
        dpi=300,
        transparent_background=True,
        size="1024x1024",
        quality="medium",
        background="transparent",
        output_format="png",
        number_of_images=1,
    )


class FakeImagesClient:
    def __init__(self, b64_json: str) -> None:
        self._b64_json = b64_json

    def generate(self, **kwargs: object) -> object:
        return type(
            "FakeResponse",
            (),
            {"data": [{"b64_json": self._b64_json}]},
        )()


class FakeOpenAIClient:
    def __init__(self, b64_json: str) -> None:
        self.images = FakeImagesClient(b64_json)


class GeneratedImageInspectionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base_path = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_inspector_classifies_valid_visible_png(self) -> None:
        path = self.base_path / "visible.png"
        path.write_bytes(make_png_bytes((255, 0, 0, 255)))

        inspection = inspect_png(path)

        self.assertEqual(inspection.classification, "VALID")
        self.assertEqual(inspection.dimensions, (3, 3))
        self.assertEqual(inspection.image_mode, "RGBA")
        self.assertEqual(inspection.alpha_minimum, 255)
        self.assertEqual(inspection.alpha_maximum, 255)
        self.assertEqual(inspection.visible_pixels, 9)
        self.assertFalse(inspection.all_visible_pixels_white)

    def test_inspector_classifies_fully_transparent_png(self) -> None:
        path = self.base_path / "transparent.png"
        path.write_bytes(make_png_bytes((255, 0, 0, 0)))

        inspection = inspect_png(path)

        self.assertEqual(inspection.classification, "FULLY_TRANSPARENT")
        self.assertEqual(inspection.alpha_minimum, 0)
        self.assertEqual(inspection.alpha_maximum, 0)
        self.assertEqual(inspection.visible_pixels, 0)

    def test_inspector_classifies_all_white_png(self) -> None:
        path = self.base_path / "white.png"
        path.write_bytes(make_png_bytes((255, 255, 255, 255)))

        inspection = inspect_png(path)

        self.assertEqual(inspection.classification, "ALL_WHITE")
        self.assertTrue(inspection.all_visible_pixels_white)

    def test_inspector_classifies_invalid_and_empty_files(self) -> None:
        invalid_path = self.base_path / "invalid.png"
        invalid_path.write_bytes(b"not-a-png")
        empty_path = self.base_path / "empty.png"
        empty_path.write_bytes(b"")

        self.assertEqual(inspect_png(invalid_path).classification, "INVALID_IMAGE")
        self.assertEqual(inspect_png(empty_path).classification, "EMPTY_FILE")

    def test_openai_provider_accepts_valid_visible_png(self) -> None:
        image_data = base64.b64encode(
            make_png_bytes((255, 0, 0, 255))
        ).decode("ascii")
        result = OpenAIImageProvider(
            output_dir=self.base_path,
            client=FakeOpenAIClient(image_data),
        ).generate_image(make_request())

        self.assertEqual(result.status, "SUCCESS")
        self.assertEqual(result.errors, ())

    def test_openai_provider_fails_fully_transparent_png(self) -> None:
        image_data = base64.b64encode(
            make_png_bytes((255, 0, 0, 0))
        ).decode("ascii")
        result = OpenAIImageProvider(
            output_dir=self.base_path,
            client=FakeOpenAIClient(image_data),
        ).generate_image(make_request())

        self.assertEqual(result.status, "FAILED")
        self.assertIn("FULLY_TRANSPARENT", result.errors[0])

    def test_openai_provider_fails_all_white_png(self) -> None:
        image_data = base64.b64encode(
            make_png_bytes((255, 255, 255, 255))
        ).decode("ascii")
        result = OpenAIImageProvider(
            output_dir=self.base_path,
            client=FakeOpenAIClient(image_data),
        ).generate_image(make_request())

        self.assertEqual(result.status, "FAILED")
        self.assertIn("ALL_WHITE", result.errors[0])

    def test_openai_provider_fails_invalid_base64(self) -> None:
        result = OpenAIImageProvider(
            output_dir=self.base_path,
            client=FakeOpenAIClient("not valid base64"),
        ).generate_image(make_request())

        self.assertEqual(result.status, "FAILED")
        self.assertIn("invalid base64", result.errors[0])


if __name__ == "__main__":
    unittest.main()
