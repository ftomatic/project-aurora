"""Aurora content production queue service."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4

from project_aurora.production.queue_item import (
    ProductionQueueItem,
    SUPPORTED_CONTENT_TYPES,
    SUPPORTED_PLATFORMS,
    SUPPORTED_STATUSES,
)


@dataclass(frozen=True, slots=True)
class QueueSaveResult:
    """Metadata returned after saving a production queue."""

    path: Path
    item_count: int


class ProductionQueue:
    """Create, persist, load, and update Aurora production queue items."""

    def __init__(self, queue_dir: Path | None = None) -> None:
        self._queue_dir = queue_dir or Path("data") / "aurora" / "production_queue"

    @property
    def queue_dir(self) -> Path:
        """Return the production queue runtime directory."""
        return self._queue_dir

    def create_queue_item(
        self,
        product_name: str,
        product_category: str,
        platform: str,
        content_type: str,
        priority: str,
        prompt: str,
        notes: str = "",
        status: str = "pending",
        item_id: str | None = None,
    ) -> ProductionQueueItem:
        """Create a validated production queue item."""
        now = datetime.now()
        return ProductionQueueItem(
            id=item_id or self._new_item_id(platform, content_type),
            product_name=product_name,
            product_category=product_category,
            platform=platform,
            content_type=content_type,
            priority=priority,
            status=status,
            prompt=prompt,
            notes=notes,
            created_at=now,
            updated_at=now,
        )

    def create_queue_from_strategy(
        self,
        strategy: Any,
    ) -> tuple[ProductionQueueItem, ...]:
        """Create content tasks from product strategy output."""
        product_name = self._get_strategy_value(strategy, "selected_product")
        product_category = self._get_strategy_value(strategy, "product_type")
        collection_name = self._get_strategy_value(strategy, "collection_name")
        priority = self._get_strategy_value(
            strategy,
            "production_priority",
            default="Medium",
        )
        positioning = self._get_strategy_value(
            strategy,
            "positioning",
            default=f"{product_name} content package",
        )

        task_specs = (
            ("Etsy", "product_listing"),
            ("Etsy", "seo_description"),
            ("Instagram", "social_caption"),
            ("TikTok", "short_video_script"),
            ("Pinterest", "pin_description"),
            ("Shopify", "product_listing"),
            ("Shopify", "email_promo"),
            ("Instagram", "image_prompt"),
        )

        return tuple(
            self.create_queue_item(
                product_name=product_name,
                product_category=product_category,
                platform=platform,
                content_type=content_type,
                priority=priority,
                prompt=self._build_prompt(
                    product_name=product_name,
                    product_category=product_category,
                    collection_name=collection_name,
                    positioning=positioning,
                    platform=platform,
                    content_type=content_type,
                ),
                notes=f"Generated from strategy plan for {collection_name}.",
            )
            for platform, content_type in task_specs
        )

    def save_queue(
        self,
        items: tuple[ProductionQueueItem, ...] | list[ProductionQueueItem],
        queue_name: str = "latest",
    ) -> QueueSaveResult:
        """Save queue items to a runtime JSON file."""
        self._queue_dir.mkdir(parents=True, exist_ok=True)
        path = self._queue_path(queue_name)
        payload = {
            "saved_at": datetime.now().isoformat(),
            "item_count": len(items),
            "items": [item.to_dict() for item in items],
        }
        with path.open("w", encoding="utf-8") as output_file:
            json.dump(payload, output_file, indent=2, sort_keys=True)
        return QueueSaveResult(path=path, item_count=len(items))

    def load_queue(
        self,
        queue_name: str = "latest",
    ) -> tuple[ProductionQueueItem, ...]:
        """Load queue items from a runtime JSON file."""
        path = self._queue_path(queue_name)
        if not path.exists():
            raise FileNotFoundError(f"Production queue not found: {path}.")

        with path.open("r", encoding="utf-8") as input_file:
            payload = json.load(input_file)

        items = payload.get("items")
        if not isinstance(items, list):
            raise ValueError(f"Production queue is invalid: {path}.")
        return tuple(ProductionQueueItem.from_dict(item) for item in items)

    def update_status(
        self,
        items: tuple[ProductionQueueItem, ...] | list[ProductionQueueItem],
        item_id: str,
        status: str,
    ) -> tuple[ProductionQueueItem, ...]:
        """Return queue items with one item status updated."""
        if status not in SUPPORTED_STATUSES:
            raise ValueError(f"Unsupported status: {status}.")

        updated_items: list[ProductionQueueItem] = []
        found = False
        for item in items:
            if item.id == item_id:
                updated_items.append(item.with_status(status))
                found = True
            else:
                updated_items.append(item)

        if not found:
            raise ValueError(f"Queue item not found: {item_id}.")
        return tuple(updated_items)

    @staticmethod
    def list_pending(
        items: tuple[ProductionQueueItem, ...] | list[ProductionQueueItem],
    ) -> tuple[ProductionQueueItem, ...]:
        """Return queue items still waiting for production."""
        return tuple(item for item in items if item.status == "pending")

    def _queue_path(self, queue_name: str) -> Path:
        cleaned_name = self._clean_file_name(queue_name)
        return self._queue_dir / f"{cleaned_name}.json"

    @staticmethod
    def _new_item_id(platform: str, content_type: str) -> str:
        prefix = f"{platform}_{content_type}".casefold().replace(" ", "_")
        return f"{prefix}_{uuid4().hex[:10]}"

    @staticmethod
    def _clean_file_name(value: str) -> str:
        cleaned = value.strip().replace(" ", "_")
        if not cleaned:
            raise ValueError("Queue name cannot be empty.")
        if cleaned in {".", ".."} or "/" in cleaned or "\\" in cleaned:
            raise ValueError(f"Invalid queue name: {value!r}.")
        return cleaned

    @staticmethod
    def _get_strategy_value(
        strategy: Any,
        field_name: str,
        default: str | None = None,
    ) -> str:
        value: Any
        if isinstance(strategy, Mapping):
            value = strategy.get(field_name, default)
        else:
            value = getattr(strategy, field_name, default)

        if value is None:
            raise ValueError(f"Strategy field is required: {field_name}.")
        return str(value)

    @staticmethod
    def _build_prompt(
        product_name: str,
        product_category: str,
        collection_name: str,
        positioning: str,
        platform: str,
        content_type: str,
    ) -> str:
        if platform not in SUPPORTED_PLATFORMS:
            raise ValueError(f"Unsupported platform: {platform}.")
        if content_type not in SUPPORTED_CONTENT_TYPES:
            raise ValueError(f"Unsupported content type: {content_type}.")

        return (
            f"Create a {content_type} for {platform} for {product_name}. "
            f"Product category: {product_category}. "
            f"Collection: {collection_name}. "
            f"Positioning: {positioning}."
        )
