"""Provider-neutral Aurora image generation engine."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Any

from project_aurora.image_generation.image_provider import ImageProvider
from project_aurora.image_generation.image_quality import (
    DEFAULT_OPENAI_IMAGE_QUALITY,
    validate_image_quality,
)
from project_aurora.image_generation.image_request import ImageRequest
from project_aurora.image_generation.image_result import ImageResult
from project_aurora.image_generation.image_cost_estimator import ImageCostEstimator
from project_aurora.image_generation.mock_provider import MockImageProvider
from project_aurora.image_generation.openai_provider import OpenAIImageProvider
from project_aurora.image_generation.provider_registry import (
    ImageProviderConfig,
    ProviderRegistry,
)
from project_aurora.storage.memory_manager import MemoryManager


class ImageGenerationEngine:
    """Load prompt packages, select providers, and save image results."""

    def __init__(
        self,
        memory: MemoryManager,
        providers: tuple[ImageProvider, ...] | None = None,
        provider_registry: ProviderRegistry | None = None,
        provider_config: ImageProviderConfig | None = None,
        cost_estimator: ImageCostEstimator | None = None,
        output_dir: Path | None = None,
    ) -> None:
        self._memory = memory
        self._output_dir = output_dir or Path("data") / "aurora" / "generated_images"
        self._provider_config = provider_config or ImageProviderConfig()
        self._cost_estimator = cost_estimator or ImageCostEstimator()
        if provider_registry is not None:
            self._provider_registry = provider_registry
        elif providers is not None:
            self._provider_registry = ProviderRegistry(providers)
        else:
            self._provider_registry = ProviderRegistry.default(
                output_dir=self._output_dir,
                config=self._provider_config,
            )

    def run(
        self,
        prompt_package_id: str = "latest",
        provider: str = "mock",
        image_type: str = "product_asset",
        width: int = 3000,
        height: int = 3000,
        dpi: int = 300,
        transparent_background: bool = True,
        size: str | None = None,
        quality: str | None = None,
        background: str | None = None,
        output_format: str | None = None,
        number_of_images: int | None = None,
    ) -> ImageResult:
        """Generate images from a stored prompt package."""
        prompt_package = self._memory.load_prompt_package(prompt_package_id)
        provider_name = provider or self._provider_config.provider
        image_provider = self.select_provider(provider_name)
        resolved_quality = validate_image_quality(quality or self._provider_config.quality)
        resolved_number = number_of_images or self._provider_config.number_of_images
        request = self.create_request(
            prompt_package=prompt_package,
            provider_name=image_provider.provider_name(),
            image_type=image_type,
            width=width,
            height=height,
            dpi=dpi,
            transparent_background=transparent_background,
            size=size or self._provider_config.size,
            quality=resolved_quality,
            background=background or self._provider_config.background,
            output_format=output_format or self._provider_config.output_format,
            number_of_images=resolved_number,
        )
        estimate = self._cost_estimator.estimate(
            provider=provider_name,
            quality=resolved_quality,
            number_of_images=resolved_number,
        )
        result = image_provider.generate_image(request)
        enriched_result = replace(
            result,
            cost_estimate=estimate.total_cost,
            estimated_cost=estimate.total_cost,
            image_paths=result.image_paths or result.generated_files,
            prompt_version=self._provider_config.prompt_version,
            metadata={
                **result.metadata,
                "estimated_cost": estimate.total_cost,
                "cost_per_image": estimate.cost_per_image,
                "prompt_version": self._provider_config.prompt_version,
                "expected_style": prompt_package.get("style", ""),
                "expected_palette": prompt_package.get("palette", ""),
                "expected_composition": prompt_package.get("composition", ""),
                "expected_rendering": prompt_package.get("rendering_family")
                or prompt_package.get("rendering_method", ""),
                "expected_background_treatment": prompt_package.get("background_treatment", ""),
                "expected_product_type": prompt_package.get("product_type")
                or prompt_package.get("category", ""),
            },
        )
        self._memory.save_image_result(enriched_result)
        return enriched_result

    def select_provider(self, provider: str) -> ImageProvider:
        """Return a configured image provider by name."""
        return self._provider_registry.select(provider)

    @staticmethod
    def create_request(
        prompt_package: dict[str, Any],
        provider_name: str,
        image_type: str,
        width: int,
        height: int,
        dpi: int,
        transparent_background: bool,
        size: str | None = None,
        quality: str = DEFAULT_OPENAI_IMAGE_QUALITY,
        background: str = "transparent",
        output_format: str = "png",
        number_of_images: int = 1,
    ) -> ImageRequest:
        """Create an ImageRequest from a stored prompt package."""
        product_name = str(prompt_package.get("product_name", "Unknown Product"))
        image_style = str(prompt_package.get("style", "Unspecified"))
        prompt = str(prompt_package.get("image_prompt", ""))
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
            prompt=prompt,
            size=size or f"{width}x{height}",
            quality=validate_image_quality(quality),
            background=background,
            output_format=output_format,
            number_of_images=number_of_images,
        )
