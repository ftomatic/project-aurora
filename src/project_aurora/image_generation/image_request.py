"""Provider-neutral image generation request model."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class ImageRequest:
    """A provider-neutral request for image generation."""

    project_name: str
    product_name: str
    prompt_package: dict[str, Any]
    image_style: str
    image_type: str
    width: int
    height: int
    dpi: int
    transparent_background: bool
    provider: str
    created_at: datetime

    def __post_init__(self) -> None:
        self._require_text("project_name", self.project_name)
        self._require_text("product_name", self.product_name)
        self._require_text("image_style", self.image_style)
        self._require_text("image_type", self.image_type)
        self._require_text("provider", self.provider)
        if self.width <= 0:
            raise ValueError("Width must be greater than zero.")
        if self.height <= 0:
            raise ValueError("Height must be greater than zero.")
        if self.dpi <= 0:
            raise ValueError("DPI must be greater than zero.")

    @staticmethod
    def _require_text(field_name: str, value: str) -> None:
        if not value.strip():
            raise ValueError(f"{field_name} cannot be empty.")
