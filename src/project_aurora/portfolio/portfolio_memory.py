"""Historical portfolio memory for Aurora planning."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from difflib import SequenceMatcher

from project_aurora.planning.production_queue_manager import ProductionQueueManager


@dataclass(frozen=True, slots=True)
class PortfolioMemoryRecord:
    """One remembered product or listing used to diversify the portfolio."""

    product_name: str
    market_category: str
    audience: str
    art_style: str
    product_type: str
    holiday: str
    keywords: tuple[str, ...]
    date_produced: date
    queue_status: str
    etsy_draft: str = ""
    published: bool = False
    sales: int = 0
    metadata: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.product_name.strip():
            raise ValueError("product_name cannot be empty.")
        object.__setattr__(self, "keywords", tuple(self.keywords))
        object.__setattr__(self, "metadata", dict(self.metadata))


class PortfolioMemory:
    """Read-only portfolio memory used by the AI Portfolio Manager."""

    def __init__(self, records: tuple[PortfolioMemoryRecord, ...] = ()) -> None:
        self._records = tuple(records)

    @classmethod
    def from_queue(cls, queue_manager: ProductionQueueManager) -> "PortfolioMemory":
        """Build memory from the current production queue."""
        from project_aurora.portfolio.market_segments import (
            classify_market_category,
            normalize_audience,
        )

        records = tuple(
            PortfolioMemoryRecord(
                product_name=job.product_name,
                market_category=classify_market_category(
                    job.product_name,
                    job.category,
                    job.keywords,
                ),
                audience=normalize_audience(job.target_customer),
                art_style=job.style,
                product_type=job.category,
                holiday=job.seasonal_theme,
                keywords=job.keywords,
                date_produced=job.created_at.date(),
                queue_status=job.status,
            )
            for job in queue_manager.list_jobs()
        )
        return cls(records)

    @property
    def records(self) -> tuple[PortfolioMemoryRecord, ...]:
        """Return portfolio memory records."""
        return self._records

    def max_similarity(self, product_name: str) -> float:
        """Return highest name similarity against remembered products."""
        if not self._records:
            return 0.0
        normalized = _normalize(product_name)
        return max(
            _similarity(normalized, _normalize(record.product_name))
            for record in self._records
        )

    def styles_for_category(self, category: str) -> tuple[str, ...]:
        """Return styles already used for a market category."""
        return tuple(
            record.art_style
            for record in self._records
            if record.market_category.casefold() == category.casefold()
        )

    def count_for_dimension(self, dimension: str, value: str) -> int:
        """Count remembered products for a portfolio dimension."""
        return sum(
            1
            for record in self._records
            if str(getattr(record, dimension)).casefold() == value.casefold()
        )


def _normalize(value: str) -> str:
    return " ".join(value.casefold().replace("-", " ").split())


def _similarity(left: str, right: str) -> float:
    if left == right:
        return 1.0
    left_tokens = set(left.split())
    right_tokens = set(right.split())
    if not left_tokens or not right_tokens:
        return 0.0
    jaccard = len(left_tokens & right_tokens) / len(left_tokens | right_tokens)
    sequence = SequenceMatcher(None, left, right).ratio()
    return round(jaccard * sequence, 3)
