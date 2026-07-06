"""Provider-neutral Aurora image generation engine."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from project_aurora.image_generation.image_provider import ImageProvider
from project_aurora.image_generation.image_request import ImageRequest
from project_aurora.image_generation.image_result import ImageResult
from project_aurora.image_generation.mock_provider import MockImageProvider
from project_aurora.image_generation.openai_provider import OpenAIImageProvider
from project_aurora.storage.memory_manager import MemoryManager


class ImageGenerationEngine:
    """Load prompt packages, select providers, and save image results."""

    def __init__(
        self,
        memory: MemoryManager,
        providers: tuple[ImageProvider, ...] | None = None,
        output_dir: Path | None = None,
    ) -> None:
        self._memory = memory
        self._output_dir = output_dir or Path("data") / "aurora" / "generated_images"
        provider_list = providers or (
            MockImageProvider(output_dir=self._output_dir),
            OpenAIImageProvider(),
        )
        self._providers = {
            self._provider_key(provider.provider_name()): provider
            for provider in provider_list
        }

    def run(
        self,
        prompt_package_id: str = "latest",
        provider: str = "mock",
        image_type: str = "product_asset",
        width: int = 3000,
        height: int = 3000,
        dpi: int = 300,
        transparent_background: bool = True,
    ) -> ImageResult:
        """Generate images from a stored prompt package."""
        prompt_package = self._memory.load_prompt_package(prompt_package_id)
        image_provider = self.select_provider(provider)
        request = self.create_request(
            prompt_package=prompt_package,
            provider_name=image_provider.provider_name(),
            image_type=image_type,
            width=width,
            height=height,
            dpi=dpi,
            transparent_background=transparent_background,
        )
        result = image_provider.generate_image(request)
        self._memory.save_image_result(result)
        return result

    def select_provider(self, provider: str) -> ImageProvider:
        """Return a configured image provider by name."""
        provider_key = self._provider_key(provider)
        aliases = {
            "mock": "mock_provider",
            "mockimageprovider": "mock_provider",
            "openai": "openai_image_provider",
            "openaiimageprovider": "openai_image_provider",
        }
        provider_key = aliases.get(provider_key, provider_key)
        try:
            return self._providers[provider_key]
        except KeyError as error:
            raise ValueError(f"Unknown image provider: {provider}.") from error

    @staticmethod
    def create_request(
        prompt_package: dict[str, Any],
        provider_name: str,
        image_type: str,
        width: int,
        height: int,
        dpi: int,
        transparent_background: bool,
    ) -> ImageRequest:
        """Create an ImageRequest from a stored prompt package."""
        product_name = str(prompt_package.get("product_name", "Unknown Product"))
        image_style = str(prompt_package.get("style", "Unspecified"))
        return ImageRequest(
            project_name="Project Aurora",
            product_name=product_name,
            prompt_package=prompt_package,
            image_style=image_style,
            image_type=image_type,
            width=width,
            height=height,
            dpi=dpi,
            transparent_background=transparent_background,
            provider=provider_name,
            created_at=datetime.now(),
        )

    @staticmethod
    def _provider_key(provider: str) -> str:
        return provider.casefold().strip().replace(" ", "_")
