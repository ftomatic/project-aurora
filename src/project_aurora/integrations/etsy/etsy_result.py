"""Etsy draft integration result models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class EtsyDraftResult:
    """Result returned after attempting Etsy draft creation."""

    status: str
    etsy_listing_id: str | None
    draft_url: str | None
    errors: tuple[str, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)
    created_at: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.status.strip():
            raise ValueError("Status cannot be empty.")
        object.__setattr__(self, "status", self.status.strip().upper())
        object.__setattr__(self, "errors", tuple(self.errors))
        object.__setattr__(self, "warnings", tuple(self.warnings))
        object.__setattr__(self, "metadata", dict(self.metadata))


@dataclass(frozen=True, slots=True)
class EtsyImageUploadAttempt:
    """Result for one attempted Etsy listing image upload."""

    image_path: str
    rank: int
    status: str
    etsy_image_id: str | None = None
    errors: tuple[str, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.rank < 1:
            raise ValueError("Image rank must start at 1.")
        object.__setattr__(self, "status", self.status.strip().upper())
        object.__setattr__(self, "errors", tuple(self.errors))
        object.__setattr__(self, "warnings", tuple(self.warnings))
        object.__setattr__(self, "metadata", dict(self.metadata))


@dataclass(frozen=True, slots=True)
class EtsyImageUploadResult:
    """Summary for uploading local images to an Etsy draft listing."""

    status: str
    etsy_listing_id: str | None
    images_found: int
    images_uploaded: int
    failed: int
    attempts: tuple[EtsyImageUploadAttempt, ...] = field(default_factory=tuple)
    errors: tuple[str, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)
    created_at: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "status", self.status.strip().upper())
        object.__setattr__(self, "attempts", tuple(self.attempts))
        object.__setattr__(self, "errors", tuple(self.errors))
        object.__setattr__(self, "warnings", tuple(self.warnings))
        object.__setattr__(self, "metadata", dict(self.metadata))


@dataclass(frozen=True, slots=True)
class EtsyDigitalFileUploadResult:
    """Result of uploading a customer ZIP file to an Etsy draft."""

    status: str
    etsy_listing_id: str | None
    digital_file_path: str | None
    uploaded: bool
    errors: tuple[str, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "status", self.status.strip().upper())
        object.__setattr__(self, "errors", tuple(self.errors))
        object.__setattr__(self, "warnings", tuple(self.warnings))
        object.__setattr__(self, "metadata", dict(self.metadata))


@dataclass(frozen=True, slots=True)
class EtsyCompleteDraftResult:
    """Complete Etsy draft production flow result."""

    etsy_listing_id: str | None
    draft_url: str | None
    draft_created: bool
    images_uploaded: int
    image_count: int
    digital_file_uploaded: bool
    digital_file_path: str | None
    price: float
    status: str
    completed_stages: tuple[str, ...] = field(default_factory=tuple)
    failed_stage: str | None = None
    warnings: tuple[str, ...] = field(default_factory=tuple)
    errors: tuple[str, ...] = field(default_factory=tuple)
    created_at: datetime = field(default_factory=datetime.now)

    def __post_init__(self) -> None:
        object.__setattr__(self, "status", self.status.strip().upper())
        object.__setattr__(self, "completed_stages", tuple(self.completed_stages))
        object.__setattr__(self, "warnings", tuple(self.warnings))
        object.__setattr__(self, "errors", tuple(self.errors))
