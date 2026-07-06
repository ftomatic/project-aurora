"""Abstract image provider interface."""

from __future__ import annotations

from abc import ABC, abstractmethod

from project_aurora.image_generation.image_request import ImageRequest
from project_aurora.image_generation.image_result import ImageResult


class ImageProvider(ABC):
    """Provider contract for Aurora image generation adapters."""

    @abstractmethod
    def generate_image(self, request: ImageRequest) -> ImageResult:
        """Generate image files for a request."""

    @abstractmethod
    def health_check(self) -> bool:
        """Return whether the provider is ready for use."""

    @abstractmethod
    def provider_name(self) -> str:
        """Return the display name for this provider."""
