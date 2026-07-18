"""Tests for Aurora image generation engine architecture."""

from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_PATH))

from project_aurora.image_generation.image_generation_engine import (  # noqa: E402
    ImageGenerationEngine,
)
from project_aurora.image_generation.image_request import ImageRequest  # noqa: E402
from project_aurora.image_generation.image_result import ImageResult  # noqa: E402
from project_aurora.image_generation.mock_provider import (  # noqa: E402
    MockImageProvider,
)
from project_aurora.image_generation.openai_provider import (  # noqa: E402
    OpenAIImageProvider,
)
from project_aurora.storage.csv_storage import CSVStorage  # noqa: E402
from project_aurora.storage.memory_manager import MemoryManager  # noqa: E402


def make_prompt_package() -> dict[str, object]:
    return {
        "product_name": "Strawberry Birthday Party Printable",
        "collection": "Summer Strawberry Birthday Collection",
        "theme": "Strawberry Birthday",
        "style": "Storybook Watercolor",
        "image_prompt": "A whimsical strawberry birthday design.",
        "negative_prompt": "No text\nNo watermark",
        "keywords": ["strawberry birthday", "party printable"],
    }


class ImageGenerationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base_path = Path(self.temp_dir.name)
        self.memory = MemoryManager(storage=CSVStorage(base_path=self.base_path))
        self.output_dir = self.base_path / "generated_images"
        self.mock_output_dir = self.base_path / "mock_generated_images"

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_image_request_dataclass(self) -> None:
        request = ImageRequest(
            project_name="Project Aurora",
            product_name="Strawberry Birthday Party Printable",
            prompt_package=make_prompt_package(),
            image_style="Storybook Watercolor",
            image_type="product_asset",
            width=3000,
            height=3000,
            dpi=300,
            transparent_background=True,
            provider="Mock Provider",
            created_at=datetime.now(),
        )

        self.assertEqual(request.project_name, "Project Aurora")
        self.assertEqual(request.width, 3000)
        self.assertTrue(request.transparent_background)

    def test_image_result_dataclass(self) -> None:
        result = ImageResult(
            status="success",
            provider="Mock Provider",
            generated_files=("one.png",),
            generation_time=0.1,
            cost_estimate=0.0,
            metadata={"image_count": 1},
        )

        self.assertEqual(result.status, "SUCCESS")
        self.assertEqual(result.generated_files, ("one.png",))
        self.assertEqual(result.metadata["image_count"], 1)

    def test_mock_provider_generates_placeholder_files(self) -> None:
        provider = MockImageProvider(output_dir=self.output_dir, image_count=2)
        request = ImageGenerationEngine.create_request(
            prompt_package=make_prompt_package(),
            provider_name=provider.provider_name(),
            image_type="product_asset",
            width=3000,
            height=3000,
            dpi=300,
            transparent_background=True,
        )

        result = provider.generate_image(request)

        self.assertEqual(result.status, "SUCCESS")
        self.assertEqual(len(result.generated_files), 2)
        for generated_file in result.generated_files:
            self.assertTrue(Path(generated_file).exists())
            self.assertEqual(Path(generated_file).suffix, ".png")
            self.assertIn("mock_generated_images", generated_file)
        self.assertFalse(self.output_dir.exists())

    def test_provider_selection(self) -> None:
        engine = ImageGenerationEngine(
            memory=self.memory,
            output_dir=self.output_dir,
        )

        self.assertIsInstance(engine.select_provider("mock"), MockImageProvider)
        self.assertIsInstance(
            engine.select_provider("openai"),
            OpenAIImageProvider,
        )
        with self.assertRaises(ValueError):
            engine.select_provider("missing")

    def test_openai_provider_requires_configuration(self) -> None:
        with patch.dict("os.environ", {"OPENAI_API_KEY": ""}):
            provider = OpenAIImageProvider()
            request = ImageGenerationEngine.create_request(
                prompt_package=make_prompt_package(),
                provider_name=provider.provider_name(),
                image_type="product_asset",
                width=3000,
                height=3000,
                dpi=300,
                transparent_background=True,
            )

            self.assertFalse(provider.health_check())
            with self.assertRaises(RuntimeError):
                provider.generate_image(request)

    def test_image_generation_engine_saves_result_to_memory(self) -> None:
        self.memory.save_prompt_package(make_prompt_package())
        engine = ImageGenerationEngine(
            memory=self.memory,
            output_dir=self.output_dir,
        )

        result = engine.run(provider="mock")

        self.assertEqual(result.status, "SUCCESS")
        self.assertEqual(len(result.generated_files), 4)
        saved_result = self.memory.load_image_result()
        self.assertEqual(saved_result["status"], "SUCCESS")
        self.assertEqual(saved_result["provider"], "Mock Provider")

    def test_mock_provider_cannot_overwrite_real_production_paths(self) -> None:
        self.output_dir.mkdir()
        real_file = self.output_dir / "strawberry_birthday_party_printable_01.png"
        real_file.write_bytes(b"real-openai-image")
        provider = MockImageProvider(output_dir=self.output_dir, image_count=1)
        request = ImageGenerationEngine.create_request(
            prompt_package=make_prompt_package(),
            provider_name=provider.provider_name(),
            image_type="product_asset",
            width=3000,
            height=3000,
            dpi=300,
            transparent_background=True,
        )

        result = provider.generate_image(request)

        self.assertEqual(real_file.read_bytes(), b"real-openai-image")
        self.assertIn("mock_generated_images", result.generated_files[0])


if __name__ == "__main__":
    unittest.main()
