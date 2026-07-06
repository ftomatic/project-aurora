"""Load Aurora project profiles from local YAML files."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from project_aurora.config.project_profile import ProjectProfile


class ProjectProfileLoader:
    """Load project profile YAML without external dependencies."""

    def load(self, path: Path) -> ProjectProfile:
        """Load and validate a project profile."""
        if not path.exists():
            raise FileNotFoundError(f"Project profile not found: {path}.")
        data = self._parse_yaml(path)
        return ProjectProfile(
            project_id=self._required_str(data, "project_id"),
            brand_name=self._required_str(data, "brand_name"),
            marketplace=self._required_str(data, "marketplace"),
            shop_url=self._required_str(data, "shop_url"),
            language=self._required_str(data, "language"),
            currency=self._required_str(data, "currency"),
            target_customer=self._required_str(data, "target_customer"),
            brand_style=self._required_str(data, "brand_style"),
            default_ai_provider=self._required_str(
                data,
                "default_ai_provider",
            ),
            default_image_size=self._required_str(data, "default_image_size"),
            default_price=float(data["default_price"]),
            allowed_product_types=tuple(data["allowed_product_types"]),
            allowed_platforms=tuple(data["allowed_platforms"]),
            retention_policy=dict(data["retention_policy"]),
        )

    @staticmethod
    def _required_str(data: dict[str, Any], key: str) -> str:
        value = data.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"Missing project profile value: {key}.")
        return value

    @staticmethod
    def _parse_yaml(path: Path) -> dict[str, Any]:
        data: dict[str, Any] = {}
        current_key: str | None = None

        for raw_line in path.read_text(encoding="utf-8").splitlines():
            if not raw_line.strip() or raw_line.lstrip().startswith("#"):
                continue

            indent = len(raw_line) - len(raw_line.lstrip(" "))
            line = raw_line.strip()

            if indent == 0 and line.endswith(":"):
                current_key = line[:-1]
                data[current_key] = {}
                continue

            if indent == 0 and ":" in line:
                key, value = line.split(":", maxsplit=1)
                data[key.strip()] = _parse_scalar(value.strip())
                current_key = key.strip()
                continue

            if current_key is None:
                raise ValueError(f"Invalid YAML line: {raw_line}.")

            if line.startswith("- "):
                existing = data.get(current_key)
                if not isinstance(existing, list):
                    existing = []
                    data[current_key] = existing
                existing.append(_parse_scalar(line[2:].strip()))
                continue

            if ":" in line:
                existing = data.get(current_key)
                if not isinstance(existing, dict):
                    existing = {}
                    data[current_key] = existing
                key, value = line.split(":", maxsplit=1)
                existing[key.strip()] = _parse_scalar(value.strip())
                continue

            raise ValueError(f"Invalid YAML line: {raw_line}.")

        return data


def _parse_scalar(value: str) -> str | float:
    cleaned = value.strip().strip("\"'")
    try:
        return float(cleaned)
    except ValueError:
        return cleaned
