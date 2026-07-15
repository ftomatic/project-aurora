"""Provider registry for Aurora image generation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from project_aurora.image_generation.image_provider import ImageProvider
from project_aurora.image_generation.image_quality import (
    DEFAULT_OPENAI_IMAGE_QUALITY,
    validate_image_quality,
)
from project_aurora.image_generation.mock_provider import MockImageProvider
from project_aurora.image_generation.openai_provider import OpenAIImageProvider
from project_aurora.image_generation.rate_limit import OpenAIRateLimitConfig


@dataclass(frozen=True, slots=True)
class ImageProviderConfig:
    """Image provider runtime configuration."""

    provider: str = "mock"
    model: str = "gpt-image-1"
    size: str = "1024x1024"
    quality: str = DEFAULT_OPENAI_IMAGE_QUALITY
    background: str = "transparent"
    output_format: str = "png"
    number_of_images: int = 4
    prompt_version: str = "v1"
    rate_limit_max_retries: int = 3
    rate_limit_safety_seconds: float = 3.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "quality", validate_image_quality(self.quality))

    @classmethod
    def from_file(cls, path: Path) -> "ImageProviderConfig":
        """Load minimal YAML config without external parser dependencies."""
        values: dict[str, str] = {}
        if path.exists():
            for raw_line in path.read_text(encoding="utf-8").splitlines():
                line = raw_line.strip()
                if not line or line.startswith("#") or ":" not in line:
                    continue
                key, value = line.split(":", maxsplit=1)
                values[key.strip()] = value.strip().strip("\"'")
        return cls(
            provider=values.get("provider", "mock"),
            model=values.get("model", "gpt-image-1"),
            size=values.get("size", "1024x1024"),
            quality=values.get("quality", DEFAULT_OPENAI_IMAGE_QUALITY),
            background=values.get("background", "transparent"),
            output_format=values.get("output_format", "png"),
            number_of_images=int(values.get("number_of_images", "8")),
            prompt_version=values.get("prompt_version", "v1"),
            rate_limit_max_retries=int(values.get("rate_limit_max_retries", "3")),
            rate_limit_safety_seconds=float(values.get("rate_limit_safety_seconds", "3")),
        )

    def openai_rate_limit_config(self) -> OpenAIRateLimitConfig:
        """Return OpenAI provider retry configuration."""
        return OpenAIRateLimitConfig(
            max_retries=self.rate_limit_max_retries,
            safety_seconds=self.rate_limit_safety_seconds,
        )


class ProviderRegistry:
    """Register and select image providers without engine changes."""

    def __init__(self, providers: tuple[ImageProvider, ...]) -> None:
        self._providers = {
            self.provider_key(provider.provider_name()): provider
            for provider in providers
        }
        self._aliases = {
            "mock": "mock_provider",
            "mockimageprovider": "mock_provider",
            "openai": "openai_gpt_image",
            "openaiimageprovider": "openai_gpt_image",
            "openaigptimage": "openai_gpt_image",
            "gpt_image": "openai_gpt_image",
        }

    @classmethod
    def default(
        cls,
        output_dir: Path | None = None,
        config: ImageProviderConfig | None = None,
        openai_client: Any | None = None,
    ) -> "ProviderRegistry":
        """Return the default Aurora provider registry."""
        resolved_config = config or ImageProviderConfig()
        return cls(
            providers=(
                MockImageProvider(
                    output_dir=output_dir,
                    image_count=resolved_config.number_of_images,
                ),
                OpenAIImageProvider(
                    output_dir=output_dir,
                    model=resolved_config.model,
                    client=openai_client,
                    rate_limit_config=resolved_config.openai_rate_limit_config(),
                ),
            )
        )

    def select(self, provider: str) -> ImageProvider:
        """Select a provider by config name or display name."""
        provider_key = self.provider_key(provider)
        provider_key = self._aliases.get(provider_key, provider_key)
        try:
            return self._providers[provider_key]
        except KeyError as error:
            raise ValueError(f"Unknown image provider: {provider}.") from error

    @staticmethod
    def provider_key(provider: str) -> str:
        """Return normalized provider key."""
        return provider.casefold().strip().replace(" ", "_")
