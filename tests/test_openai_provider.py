"""Tests for Aurora OpenAI image provider integration."""

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

from project_aurora.image_generation.image_cost_estimator import (  # noqa: E402
    ImageCostEstimator,
)
from project_aurora.image_generation.image_generation_engine import (  # noqa: E402
    ImageGenerationEngine,
)
from project_aurora.image_generation.openai_provider import (  # noqa: E402
    OpenAIImageProvider,
)
from project_aurora.image_generation.provider_registry import (  # noqa: E402
    ImageProviderConfig,
    ProviderRegistry,
)
from project_aurora.image_generation.rate_limit import (  # noqa: E402
    OpenAIRateLimitConfig,
    retry_after_seconds,
)
from project_aurora.image_generation.image_quality import (  # noqa: E402
    validate_image_quality,
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


def make_visible_png_bytes() -> bytes:
    output = BytesIO()
    Image.new("RGBA", (2, 2), (255, 0, 0, 255)).save(output, format="PNG")
    return output.getvalue()


class FakeImagesClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def generate(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        image_data = base64.b64encode(make_visible_png_bytes()).decode("ascii")
        count = int(kwargs["n"])
        return type(
            "FakeResponse",
            (),
            {"data": [{"b64_json": image_data} for _ in range(count)]},
        )()


class FakeOpenAIClient:
    def __init__(self) -> None:
        self.images = FakeImagesClient()


class RateLimitError(Exception):
    status_code = 429


class FlakyImagesClient:
    def __init__(self, failures: int) -> None:
        self.failures = failures
        self.calls = 0

    def generate(self, **kwargs: object) -> object:
        self.calls += 1
        if self.calls <= self.failures:
            raise RateLimitError("rate_limit_exceeded. Please try again in 12s.")
        image_data = base64.b64encode(make_visible_png_bytes()).decode("ascii")
        return type("FakeResponse", (), {"data": [{"b64_json": image_data}]})()


class FlakyOpenAIClient:
    def __init__(self, failures: int) -> None:
        self.images = FlakyImagesClient(failures)


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
            quality="medium",
            number_of_images=8,
        )

        self.assertEqual(estimate.total_cost, 0.32)
        self.assertEqual(estimate.render(), "$0.32")

    def test_standard_quality_is_rejected_before_api_call(self) -> None:
        with self.assertRaises(ValueError):
            validate_image_quality("standard")

        with self.assertRaises(ValueError):
            ImageProviderConfig(provider="openai", quality="standard")

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
            quality="medium",
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
            quality="medium",
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

    def test_openai_429_followed_by_success(self) -> None:
        sleeps: list[float] = []
        fake_client = FlakyOpenAIClient(failures=1)
        provider = OpenAIImageProvider(
            output_dir=self.output_dir,
            client=fake_client,
            rate_limit_config=OpenAIRateLimitConfig(max_retries=3, safety_seconds=3),
            sleeper=sleeps.append,
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
            quality="medium",
            background="transparent",
            output_format="png",
            number_of_images=1,
        )

        result = provider.generate_image(request)

        self.assertEqual(result.status, "SUCCESS")
        self.assertEqual(fake_client.images.calls, 2)
        self.assertEqual(sleeps, [15.0])

    def test_retry_delay_parsed_from_error(self) -> None:
        self.assertEqual(
            retry_after_seconds("rate_limit_exceeded. Please try again in 12s."),
            12.0,
        )

    def test_openai_429_retries_exhausted(self) -> None:
        fake_client = FlakyOpenAIClient(failures=4)
        provider = OpenAIImageProvider(
            output_dir=self.output_dir,
            client=fake_client,
            rate_limit_config=OpenAIRateLimitConfig(max_retries=3, safety_seconds=0),
            sleeper=lambda _seconds: None,
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
            quality="medium",
            background="transparent",
            output_format="png",
            number_of_images=1,
        )

        with self.assertRaises(RateLimitError):
            provider.generate_image(request)

        self.assertEqual(fake_client.images.calls, 4)


if __name__ == "__main__":
    unittest.main()
