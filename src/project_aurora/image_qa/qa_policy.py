"""Image QA policy configuration."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


SEMANTIC_QA_MODES = frozenset({"off", "advisory", "strict"})


@dataclass(frozen=True, slots=True)
class ImageQAPolicy:
    """Runtime policy for technical and semantic image QA."""

    semantic_style_qa_mode: str = "advisory"

    def __post_init__(self) -> None:
        if self.semantic_style_qa_mode not in SEMANTIC_QA_MODES:
            raise ValueError(
                "semantic_style_qa_mode must be one of: "
                + ", ".join(sorted(SEMANTIC_QA_MODES))
            )

    @classmethod
    def from_file(cls, path: Path) -> "ImageQAPolicy":
        """Load policy from a tiny YAML-style key/value file."""
        if not path.exists():
            return cls()
        values: dict[str, str] = {}
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or ":" not in stripped:
                continue
            key, value = stripped.split(":", maxsplit=1)
            values[key.strip()] = value.strip()
        return cls(
            semantic_style_qa_mode=values.get("semantic_style_qa_mode", "advisory")
        )
