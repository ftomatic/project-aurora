"""Proven winner memory for revenue-informed style scoring."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True, slots=True)
class ProvenWinnerRecord:
    """Historical Etsy listing evidence."""

    etsy_listing_id: str
    product_name: str
    category: str
    style: str
    visits: int
    favorites: int
    sales: int
    revenue: float
    conversion_estimate: float
    last_updated: date


class ProvenWinnerMemory:
    """Read proven winner evidence from configurable local data."""

    def __init__(self, records: tuple[ProvenWinnerRecord, ...] = ()) -> None:
        self._records = records

    @classmethod
    def from_config(cls, path: Path | None = None) -> "ProvenWinnerMemory":
        """Load proven winner evidence from config/styles/proven_winners.json."""
        path = path or PROJECT_ROOT / "config" / "styles" / "proven_winners.json"
        if not path.exists():
            return cls(())
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(tuple(_record_from_data(record) for record in data.get("records", ())))

    @property
    def records(self) -> tuple[ProvenWinnerRecord, ...]:
        """Return records."""
        return self._records

    def influence_for(self, category: str, style_id: str) -> tuple[int, str]:
        """Return score boost and explanation for related proven winners."""
        normalized_category = _normalize(category)
        normalized_style = style_id.casefold()
        best_boost = 0
        best_reason = "none"
        for record in self._records:
            style_match = record.style.casefold() == normalized_style
            related_category = _normalize(record.category) in normalized_category or normalized_category in _normalize(record.category)
            if not style_match:
                continue
            if related_category:
                boost = min(18, 6 + record.sales // 30 + int(record.revenue // 100))
                reason = (
                    f"{record.product_name}: {record.sales} sales, "
                    f"${record.revenue:.0f} revenue, {record.visits} recent visits"
                )
            else:
                boost = 0
                reason = "none"
            if boost > best_boost:
                best_boost = boost
                best_reason = reason
        return best_boost, best_reason


def _record_from_data(data: dict[str, object]) -> ProvenWinnerRecord:
    return ProvenWinnerRecord(
        etsy_listing_id=str(data["etsy_listing_id"]),
        product_name=str(data["product_name"]),
        category=str(data["category"]),
        style=str(data["style"]),
        visits=int(data["visits"]),
        favorites=int(data["favorites"]),
        sales=int(data["sales"]),
        revenue=float(data["revenue"]),
        conversion_estimate=float(data["conversion_estimate"]),
        last_updated=date.fromisoformat(str(data["last_updated"])),
    )


def _normalize(value: str) -> str:
    return " ".join(value.casefold().replace("-", " ").split())
