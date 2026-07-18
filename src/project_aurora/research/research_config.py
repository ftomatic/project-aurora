"""Research planner configuration loading."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ResearchPlannerConfig:
    """Configurable limits for research-first planning."""

    minimum_confidence: float = 85
    candidate_count: int = 50
    daily_products: int = 5
    minimum_portfolio_size: int = 3
    duplicate_threshold: float = 0.80
    max_per_style: int = 1
    max_per_category: int = 1
    max_per_audience: int = 1
    max_per_season: int = 1
    max_per_product_type: int = 1

    @classmethod
    def from_file(cls, path: Path) -> "ResearchPlannerConfig":
        """Load research planner config from a simple YAML file."""
        if not path.exists():
            return cls()
        values: dict[str, str] = {}
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or ":" not in line:
                continue
            key, value = line.split(":", maxsplit=1)
            values[key.strip()] = value.strip().strip("\"'")
        return cls(
            minimum_confidence=float(values.get("minimum_confidence", "85")),
            candidate_count=int(values.get("candidate_count", "50")),
            daily_products=int(values.get("daily_products", "5")),
            minimum_portfolio_size=int(values.get("minimum_portfolio_size", "3")),
            duplicate_threshold=float(values.get("duplicate_threshold", "0.80")),
            max_per_style=int(values.get("max_per_style", "1")),
            max_per_category=int(values.get("max_per_category", "1")),
            max_per_audience=int(values.get("max_per_audience", "1")),
            max_per_season=int(values.get("max_per_season", "1")),
            max_per_product_type=int(values.get("max_per_product_type", "1")),
        )
