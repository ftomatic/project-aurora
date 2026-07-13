"""Etsy integration configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class EtsyConfig:
    """Runtime configuration for Etsy draft creation."""

    mode: str = "mock"
    shop_id: str | None = None
    client_id: str | None = None
    shared_secret: str | None = None
    access_token: str | None = None
    api_base_url: str = "https://openapi.etsy.com/v3/application"
    default_price: float = 1.99
    default_quantity: int = 999
    taxonomy_id: int | None = None
    processing_profile_id: int | None = None
    shipping_profile_id: int | None = None

    @classmethod
    def from_file(cls, path: Path) -> "EtsyConfig":
        """Load minimal YAML config and environment credentials."""
        values: dict[str, str] = {}
        if path.exists():
            for raw_line in path.read_text(encoding="utf-8").splitlines():
                line = raw_line.strip()
                if not line or line.startswith("#") or ":" not in line:
                    continue
                key, value = line.split(":", maxsplit=1)
                values[key.strip()] = value.strip().strip("\"'")

        return cls(
            mode=os.getenv("AURORA_ETSY_MODE", values.get("mode", "mock")),
            shop_id=os.getenv("ETSY_SHOP_ID") or values.get("shop_id") or None,
            client_id=os.getenv("ETSY_CLIENT_ID")
            or values.get("client_id")
            or None,
            shared_secret=os.getenv("ETSY_SHARED_SECRET")
            or values.get("shared_secret")
            or None,
            access_token=os.getenv("ETSY_ACCESS_TOKEN")
            or values.get("access_token")
            or None,
            api_base_url=values.get(
                "api_base_url",
                "https://openapi.etsy.com/v3/application",
            ),
            default_price=float(values.get("default_price", "1.99")),
            default_quantity=int(values.get("default_quantity", "999")),
            taxonomy_id=_optional_int(
                os.getenv("ETSY_TAXONOMY_ID") or values.get("taxonomy_id")
            ),
            processing_profile_id=_optional_int(
                os.getenv("ETSY_PROCESSING_PROFILE_ID")
                or values.get("processing_profile_id")
            ),
            shipping_profile_id=_optional_int(
                os.getenv("ETSY_SHIPPING_PROFILE_ID")
                or values.get("shipping_profile_id")
            ),
        )

    @property
    def is_mock_mode(self) -> bool:
        """Return whether Etsy API calls should be skipped."""
        return self.mode.casefold() in {"mock", "sandbox"}

    def validate_for_api(self, is_digital: bool = True) -> tuple[str, ...]:
        """Return missing configuration fields for real Etsy API calls."""
        missing: list[str] = []
        if not self.shop_id:
            missing.append("ETSY_SHOP_ID")
        if not self.client_id:
            missing.append("ETSY_CLIENT_ID")
        if not self.shared_secret:
            missing.append("ETSY_SHARED_SECRET")
        if not self.access_token:
            missing.append("ETSY_ACCESS_TOKEN")
        if self.taxonomy_id is None:
            missing.append("taxonomy_id")
        if not is_digital and self.processing_profile_id is None:
            missing.append("processing_profile_id")
        if not is_digital and self.shipping_profile_id is None:
            missing.append("shipping_profile_id")
        return tuple(missing)


def _optional_int(value: str | None) -> int | None:
    if value is None or not value.strip():
        return None
    return int(value)
