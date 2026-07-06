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
