"""Provider registry for Aurora image generation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from project_aurora.image_generation.image_provider import ImageProvider
from project_aurora.image_generation.mock_provider import MockImageProvider
from project_aurora.image_generation.openai_provider import OpenAIImageProvider


@dataclass(frozen=True, slots=True)
class ImageProviderConfig:
    """Image provider runtime configuration."""

    provider: str = "mock"
    model: str = "gpt-image-1"
    size: str = "1024x1024"
    quality: str = "standard"
    background: str = "transparent"
    output_format: str = "png"
    number_of_images: int = 4
    prompt_version: str = "v1"

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
            quality=values.get("quality", "standard"),
            background=values.get("background", "transparent"),
            output_format=values.get("output_format", "png"),
            number_of_images=int(values.get("number_of_images", "8")),
            prompt_version=values.get("prompt_version", "v1"),
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
