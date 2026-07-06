"""Placeholder OpenAI image provider adapter."""

from __future__ import annotations

from project_aurora.image_generation.image_provider import ImageProvider
from project_aurora.image_generation.image_request import ImageRequest
from project_aurora.image_generation.image_result import ImageResult


class OpenAIImageProvider(ImageProvider):
    """Placeholder provider for a future OpenAI image integration."""

    def generate_image(self, request: ImageRequest) -> ImageResult:
        """Raise until the OpenAI integration sprint is approved."""
        raise NotImplementedError(
            "OpenAI image generation is not implemented in this sprint."
        )

    def health_check(self) -> bool:
        """Raise until the OpenAI integration sprint is approved."""
        raise NotImplementedError(
            "OpenAI image provider health checks are not implemented yet."
        )

    def provider_name(self) -> str:
        """Return the provider display name."""
        return "OpenAI Image Provider"
