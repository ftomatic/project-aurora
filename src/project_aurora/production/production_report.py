"""Production factory report model."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class ProductionReport:
    """Summary of one Product Factory execution."""

    job_id: str
    product: str
    style: str
    draft_id: str | None
    images: int
    downloads: int
    time: float
    success: bool
    failed_stage: str | None = None
    warnings: tuple[str, ...] = field(default_factory=tuple)
    errors: tuple[str, ...] = field(default_factory=tuple)
    job_paths: dict[str, str] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.job_id.strip():
            raise ValueError("job_id cannot be empty.")
        if not self.product.strip():
            raise ValueError("product cannot be empty.")
        if not self.style.strip():
            raise ValueError("style cannot be empty.")
        if self.images < 0:
            raise ValueError("images cannot be negative.")
        if self.downloads < 0:
            raise ValueError("downloads cannot be negative.")
        if self.time < 0:
            raise ValueError("time cannot be negative.")
        object.__setattr__(self, "warnings", tuple(self.warnings))
        object.__setattr__(self, "errors", tuple(self.errors))
        object.__setattr__(self, "job_paths", dict(self.job_paths))
        object.__setattr__(self, "metadata", dict(self.metadata))

    @property
    def queue_status(self) -> str:
        """Return queue status implied by this report."""
        return "COMPLETED" if self.success else "FAILED"

    def to_dict(self) -> dict[str, Any]:
        """Return JSON-safe report data."""
        return {
            "job_id": self.job_id,
            "product": self.product,
            "style": self.style,
            "draft_id": self.draft_id,
            "images": self.images,
            "downloads": self.downloads,
            "time": self.time,
            "success": self.success,
            "failed_stage": self.failed_stage,
            "warnings": list(self.warnings),
            "errors": list(self.errors),
            "job_paths": self.job_paths,
            "created_at": self.created_at.isoformat(),
            "metadata": self.metadata,
            "queue_status": self.queue_status,
        }
