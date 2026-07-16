"""Muse style memory."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from project_aurora.storage.memory_manager import MemoryManager


STYLE_MEMORY_COLLECTION = "style_memory"


@dataclass(frozen=True, slots=True)
class StyleMemoryRecord:
    """One style usage record."""

    product_name: str
    style_used: str
    created_at: datetime = field(default_factory=datetime.now)
    sales: int = 0
    favorites: int = 0
    clicks: int = 0
    visits: int = 0


class StyleMemory:
    """Track recent Muse style decisions."""

    def __init__(self, memory: MemoryManager | None = None, limit: int = 100) -> None:
        self._memory = memory
        self._limit = limit
        self._records: list[StyleMemoryRecord] = []

    @property
    def records(self) -> tuple[StyleMemoryRecord, ...]:
        """Return in-memory records."""
        return tuple(self._records[-self._limit :])

    def count_recent_style(self, style_name: str) -> int:
        """Return recent usage count for a style."""
        return sum(1 for record in self.records if record.style_used.casefold() == style_name.casefold())

    def remember(self, product_name: str, style_used: str) -> StyleMemoryRecord:
        """Record a style decision locally and in MemoryManager."""
        record = StyleMemoryRecord(product_name=product_name, style_used=style_used)
        self._records.append(record)
        if len(self._records) > self._limit:
            self._records = self._records[-self._limit :]
        if self._memory is not None:
            self._memory.save_record(
                STYLE_MEMORY_COLLECTION,
                f"{record.created_at.strftime('%Y%m%d_%H%M%S_%f')}_{_slug(product_name)}",
                {
                    "product_name": record.product_name,
                    "style_used": record.style_used,
                    "created_at": record.created_at.isoformat(),
                    "sales": record.sales,
                    "favorites": record.favorites,
                    "clicks": record.clicks,
                    "visits": record.visits,
                },
            )
        return record


def _slug(value: str) -> str:
    return "_".join(part for part in value.casefold().replace("-", " ").split() if part)
