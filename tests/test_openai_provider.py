"""Tests for Aurora OpenAI image provider integration."""

from __future__ import annotations

import base64
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_PATH))

from project_aurora.image_generation.image_cost_estimator import (  # noqa: E402
    ImageCostEstimator,
)
from project_aurora.image_generation.image_generation_engine import (  # noqa: E402
    ImageGenerationEngine,
)
from project_aurora.image_generation.mock_provider import (  # noqa: E402
    PLACEHOLDER_PNG_BYTES,
)
from project_aurora.image_generation.openai_provider import (  # noqa: E402
    OpenAIImageProvider,
)
from project_aurora.image_generation.provider_registry import (  # noqa: E402
    ImageProviderConfig,
    ProviderRegistry,
)
from project_aurora.storage.csv_storage import CSVStorage  # noqa: E402
from project_aurora.storage.memory_manager import MemoryManager  # noqa: E402


def make_prompt_package() -> dict[str, object]:
    return {
        "product_name": "Summer Strawberry Birthday",
        "collection": "Summer Strawberry Birthday Collection",
        "style": "Storybook Watercolor",
        "image_prompt": "A whimsical strawberry birthday printable.",
    }


class FakeImagesClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def generate(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        image_data = base64.b64encode(PLACEHOLDER_PNG_BYTES).decode("ascii")
        count = int(kwargs["n"])
        return type(
            "FakeResponse",
            (),
            {"data": [{"b64_json": image_data} for _ in range(count)]},
        )()


class FakeOpenAIClient:
    def __init__(self) -> None:
        self.images = FakeImagesClient()


class OpenAIProviderTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base_path = Path(self.temp_dir.name)
        self.output_dir = self.base_path / "generated_images"
        self.memory = MemoryManager(storage=CSVStorage(base_path=self.base_path))

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_cost_estimator(self) -> None:
        estimate = ImageCostEstimator().estimate(
            provider="openai",
            quality="standard",
            number_of_images=8,
        )

        self.assertEqual(estimate.total_cost, 0.32)
        self.assertEqual(estimate.render(), "$0.32")

    def test_provider_registry_selects_openai(self) -> None:
        registry = ProviderRegistry.default(
            output_dir=self.output_dir,
            config=ImageProviderConfig(provider="openai"),
            openai_client=FakeOpenAIClient(),
        )

        self.assertIsInstance(registry.select("openai"), OpenAIImageProvider)

    def test_openai_provider_requires_api_key_or_client(self) -> None:
        provider = OpenAIImageProvider(output_dir=self.output_dir, api_key=None)

        self.assertFalse(provider.health_check())

    def test_openai_provider_uses_mocked_client(self) -> None:
        fake_client = FakeOpenAIClient()
        provider = OpenAIImageProvider(
            output_dir=self.output_dir,
            client=fake_client,
        )
        request = ImageGenerationEngine.create_request(
            prompt_package=make_prompt_package(),
            provider_name=provider.provider_name(),
            image_type="product_asset",
            width=1024,
            height=1024,
            dpi=300,
            transparent_background=True,
            size="1024x1024",
            quality="standard",
            background="transparent",
            output_format="png",
            number_of_images=2,
        )

        result = provider.generate_image(request)

        self.assertEqual(result.status, "SUCCESS")
        self.assertEqual(result.provider, "OpenAI GPT Image")
        self.assertEqual(len(result.image_paths), 2)
        self.assertEqual(fake_client.images.calls[0]["model"], "gpt-image-1")
        self.assertEqual(fake_client.images.calls[0]["n"], 2)
        for image_path in result.image_paths:
            self.assertTrue(Path(image_path).exists())

    def test_engine_saves_openai_result_to_memory(self) -> None:
        self.memory.save_prompt_package(make_prompt_package())
        config = ImageProviderConfig(
            provider="openai",
            quality="standard",
            number_of_images=2,
            prompt_version="openai-gpt-image-v1",
        )
        registry = ProviderRegistry.default(
            output_dir=self.output_dir,
            config=config,
            openai_client=FakeOpenAIClient(),
        )
        engine = ImageGenerationEngine(
            memory=self.memory,
            provider_registry=registry,
            provider_config=config,
            output_dir=self.output_dir,
        )

        result = engine.run(provider="openai")
        saved = self.memory.load_image_result()

        self.assertEqual(result.estimated_cost, 0.08)
        self.assertEqual(saved["provider"], "OpenAI GPT Image")
        self.assertEqual(saved["estimated_cost"], 0.08)
        self.assertEqual(saved["prompt_version"], "openai-gpt-image-v1")
        self.assertEqual(len(saved["image_paths"]), 2)


if __name__ == "__main__":
    unittest.main()
