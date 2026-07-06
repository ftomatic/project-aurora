"""Production queue item models for Aurora content tasks."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any


SUPPORTED_PLATFORMS: frozenset[str] = frozenset(
    {
        "Etsy",
        "TikTok",
        "Instagram",
        "Pinterest",
        "Shopify",
    }
)

SUPPORTED_CONTENT_TYPES: frozenset[str] = frozenset(
    {
        "product_listing",
        "seo_description",
        "social_caption",
        "short_video_script",
        "image_prompt",
        "pin_description",
        "email_promo",
    }
)

SUPPORTED_STATUSES: frozenset[str] = frozenset(
    {
        "pending",
        "in_progress",
        "completed",
        "skipped",
        "failed",
    }
)


@dataclass(frozen=True, slots=True)
class ProductionQueueItem:
    """A structured content task derived from product strategy output."""

    id: str
    product_name: str
    product_category: str
    platform: str
    content_type: str
    priority: str
    status: str
    prompt: str
    notes: str
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        self._require_text("id", self.id)
        self._require_text("product_name", self.product_name)
        self._require_text("product_category", self.product_category)
        self._require_text("priority", self.priority)
        self._require_text("prompt", self.prompt)

        if self.platform not in SUPPORTED_PLATFORMS:
            raise ValueError(f"Unsupported platform: {self.platform}.")
        if self.content_type not in SUPPORTED_CONTENT_TYPES:
            raise ValueError(
                f"Unsupported content type: {self.content_type}."
            )
        if self.status not in SUPPORTED_STATUSES:
            raise ValueError(f"Unsupported status: {self.status}.")

    def with_status(
        self,
        status: str,
        updated_at: datetime | None = None,
    ) -> "ProductionQueueItem":
        """Return a copy of the item with an updated status."""
        if status not in SUPPORTED_STATUSES:
            raise ValueError(f"Unsupported status: {status}.")
        return replace(self, status=status, updated_at=updated_at or datetime.now())

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation of the item."""
        return {
            "id": self.id,
            "product_name": self.product_name,
            "product_category": self.product_category,
            "platform": self.platform,
            "content_type": self.content_type,
            "priority": self.priority,
            "status": self.status,
            "prompt": self.prompt,
            "notes": self.notes,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProductionQueueItem":
        """Create an item from a stored JSON dictionary."""
        return cls(
            id=str(data["id"]),
            product_name=str(data["product_name"]),
            product_category=str(data["product_category"]),
            platform=str(data["platform"]),
            content_type=str(data["content_type"]),
            priority=str(data["priority"]),
            status=str(data["status"]),
            prompt=str(data["prompt"]),
            notes=str(data.get("notes", "")),
            created_at=datetime.fromisoformat(str(data["created_at"])),
            updated_at=datetime.fromisoformat(str(data["updated_at"])),
        )

    @staticmethod
    def _require_text(field_name: str, value: str) -> None:
        if not value.strip():
            raise ValueError(f"{field_name} cannot be empty.")
