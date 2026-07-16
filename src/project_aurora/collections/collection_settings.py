"""Collection Intelligence settings."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class CollectionSettings:
    """Configurable collection planning settings."""

    collection_size: int = 5
    minimum_collection_score: int = 80
    allow_single_products: bool = False
    cross_sell_weight: int = 15

    @classmethod
    def from_file(cls, path: Path) -> "CollectionSettings":
        """Load simple key-value YAML settings."""
        values: dict[str, str] = {}
        if path.exists():
            for raw_line in path.read_text(encoding="utf-8").splitlines():
                line = raw_line.strip()
                if not line or line.startswith("#") or ":" not in line:
                    continue
                key, value = line.split(":", maxsplit=1)
                values[key.strip()] = value.strip().strip("\"'")
        return cls(
            collection_size=int(values.get("collection_size", "5")),
            minimum_collection_score=int(values.get("minimum_collection_score", "80")),
            allow_single_products=values.get("allow_single_products", "false").casefold() == "true",
            cross_sell_weight=int(values.get("cross_sell_weight", "15")),
        )
