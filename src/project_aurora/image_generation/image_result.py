"""Provider-neutral image generation result model."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class ImageResult:
    """Result returned by an image generation provider."""

    status: str
    provider: str
    generated_files: tuple[str, ...]
    generation_time: float
    cost_estimate: float
    warnings: tuple[str, ...] = field(default_factory=tuple)
    errors: tuple[str, ...] = field(default_factory=tuple)
    metadata: dict[str, Any] = field(default_factory=dict)
    estimated_cost: float | None = None
    image_paths: tuple[str, ...] = field(default_factory=tuple)
    prompt_version: str = "v1"

    def __post_init__(self) -> None:
        if not self.status.strip():
            raise ValueError("Status cannot be empty.")
        if not self.provider.strip():
            raise ValueError("Provider cannot be empty.")
        if self.generation_time < 0:
            raise ValueError("Generation time cannot be negative.")
        if self.cost_estimate < 0:
            raise ValueError("Cost estimate cannot be negative.")
        if self.estimated_cost is not None and self.estimated_cost < 0:
            raise ValueError("Estimated cost cannot be negative.")

        object.__setattr__(self, "status", self.status.strip().upper())
        object.__setattr__(self, "provider", self.provider.strip())
        object.__setattr__(self, "generated_files", tuple(self.generated_files))
        object.__setattr__(self, "warnings", tuple(self.warnings))
        object.__setattr__(self, "errors", tuple(self.errors))
        object.__setattr__(self, "metadata", dict(self.metadata))
        if self.estimated_cost is None:
            object.__setattr__(self, "estimated_cost", self.cost_estimate)
        if not self.image_paths:
            object.__setattr__(self, "image_paths", tuple(self.generated_files))
        else:
            object.__setattr__(self, "image_paths", tuple(self.image_paths))
