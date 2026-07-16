"""Collection memory."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from project_aurora.storage.memory_manager import MemoryManager


COLLECTION_MEMORY = "collection_memory"


@dataclass(frozen=True, slots=True)
class CollectionMemoryRecord:
    """One produced collection memory record."""

    collection_name: str
    products_inside: tuple[str, ...]
    reuse_score: int
    created_at: datetime = field(default_factory=datetime.now)
    sales: int = 0
    visits: int = 0
    favorites: int = 0


class CollectionMemory:
    """Track produced collections and duplicate risk."""

    def __init__(self, memory: MemoryManager | None = None) -> None:
        self._memory = memory
        self._records: list[CollectionMemoryRecord] = []

    @property
    def records(self) -> tuple[CollectionMemoryRecord, ...]:
        """Return records."""
        return tuple(self._records)

    def duplicate_score(self, collection_name: str) -> int:
        """Return 100 for exact duplicate, 0 for new collection."""
        normalized = _normalize(collection_name)
        for record in self._records:
            if _normalize(record.collection_name) == normalized:
                return 100
        return 0

    def remember(self, collection_name: str, products: tuple[str, ...]) -> CollectionMemoryRecord:
        """Record a planned collection."""
        record = CollectionMemoryRecord(
            collection_name=collection_name,
            products_inside=products,
            reuse_score=self.duplicate_score(collection_name),
        )
        self._records.append(record)
        if self._memory is not None:
            self._memory.save_record(
                COLLECTION_MEMORY,
                _slug(collection_name),
                {
                    "collection_name": record.collection_name,
                    "products_inside": list(record.products_inside),
                    "reuse_score": record.reuse_score,
                    "created_at": record.created_at.isoformat(),
                    "sales": record.sales,
                    "visits": record.visits,
                    "favorites": record.favorites,
                },
            )
        return record


def _normalize(value: str) -> str:
    return " ".join(value.casefold().replace("-", " ").split())


def _slug(value: str) -> str:
    return "_".join(_normalize(value).split())
