"""Muse style settings loader."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class StyleSettings:
    """Configurable Muse style scoring settings."""

    minimum_style_confidence: int = 70
    maximum_style_reuse: int = 2
    preferred_style_diversity: str = "high"
    style_rotation_weight: int = 18
    season_weight: int = 10
    trend_weight: int = 12

    @classmethod
    def from_file(cls, path: Path) -> "StyleSettings":
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
            minimum_style_confidence=int(values.get("minimum_style_confidence", "70")),
            maximum_style_reuse=int(values.get("maximum_style_reuse", "2")),
            preferred_style_diversity=values.get("preferred_style_diversity", "high"),
            style_rotation_weight=int(values.get("style_rotation_weight", "18")),
            season_weight=int(values.get("season_weight", "10")),
            trend_weight=int(values.get("trend_weight", "12")),
        )
