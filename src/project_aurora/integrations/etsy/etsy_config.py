"""Etsy integration configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from project_aurora.integrations.etsy.etsy_auth import (
    build_x_api_key,
    load_local_env_values,
    normalize_credential,
    safe_last_four,
)


PROJECT_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_LOCAL_ENV_PATH = PROJECT_ROOT / "config" / "aurora.local.env"


@dataclass(frozen=True, slots=True)
class EtsyConfig:
    """Runtime configuration for Etsy draft creation."""

    mode: str = "mock"
    shop_id: str | None = None
    client_id: str | None = None
    shared_secret: str | None = None
    access_token: str | None = None
    api_base_url: str = "https://openapi.etsy.com/v3/application"
    default_price: float = 0.0
    default_quantity: int = 999
    taxonomy_id: int | None = None
    processing_profile_id: int | None = None
    shipping_profile_id: int | None = None
    normalized_credentials: tuple[str, ...] = ()

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
            mode=_normalized_value(os.getenv("AURORA_ETSY_MODE"))
            or values.get("mode", "mock"),
            shop_id=_normalized_value(os.getenv("ETSY_SHOP_ID"))
            or _normalized_value(values.get("shop_id")),
            client_id=_normalized_value(os.getenv("ETSY_CLIENT_ID"))
            or _normalized_value(values.get("client_id")),
            shared_secret=_normalized_value(os.getenv("ETSY_SHARED_SECRET"))
            or _normalized_value(values.get("shared_secret")),
            access_token=_normalized_value(os.getenv("ETSY_ACCESS_TOKEN"))
            or _normalized_value(values.get("access_token")),
            api_base_url=values.get(
                "api_base_url",
                "https://openapi.etsy.com/v3/application",
            ),
            default_price=_optional_float(values.get("default_price")),
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

    @classmethod
    def from_environment(
        cls,
        config_path: Path | None = None,
        local_env_path: Path | None = None,
    ) -> "EtsyConfig":
        """Load live Etsy credentials from environment with optional YAML defaults."""
        base_config = cls.from_file(config_path) if config_path is not None else cls()
        local_values = load_local_env_values(local_env_path) if local_env_path else {}
        changed = tuple(
            key for key, value in local_values.items() if value.changed
        )
        local = {
            key: value.value
            for key, value in local_values.items()
            if value.value is not None
        }
        return cls(
            mode=_first_present(
                local.get("AURORA_ETSY_MODE"),
                os.getenv("AURORA_ETSY_MODE"),
                "live",
            ),
            shop_id=_first_present(
                local.get("ETSY_SHOP_ID"),
                os.getenv("ETSY_SHOP_ID"),
                base_config.shop_id,
            ),
            client_id=_first_present(
                local.get("ETSY_CLIENT_ID"),
                local.get("ETSY_KEYSTRING"),
                os.getenv("ETSY_CLIENT_ID"),
                os.getenv("ETSY_KEYSTRING"),
                base_config.client_id,
            ),
            shared_secret=_first_present(
                local.get("ETSY_SHARED_SECRET"),
                os.getenv("ETSY_SHARED_SECRET"),
                base_config.shared_secret,
            ),
            access_token=_first_present(
                local.get("ETSY_ACCESS_TOKEN"),
                os.getenv("ETSY_ACCESS_TOKEN"),
                base_config.access_token,
            ),
            api_base_url=base_config.api_base_url,
            default_price=base_config.default_price,
            default_quantity=base_config.default_quantity,
            taxonomy_id=_optional_int(
                _first_present(local.get("ETSY_TAXONOMY_ID"), os.getenv("ETSY_TAXONOMY_ID"))
            )
            or base_config.taxonomy_id,
            processing_profile_id=_optional_int(
                _first_present(
                    local.get("ETSY_PROCESSING_PROFILE_ID"),
                    os.getenv("ETSY_PROCESSING_PROFILE_ID"),
                )
            )
            or base_config.processing_profile_id,
            shipping_profile_id=_optional_int(
                _first_present(
                    local.get("ETSY_SHIPPING_PROFILE_ID"),
                    os.getenv("ETSY_SHIPPING_PROFILE_ID"),
                )
            )
            or base_config.shipping_profile_id,
            normalized_credentials=changed,
        )

    def credential_diagnostics(self) -> dict[str, object]:
        """Return credential presence and header-shape diagnostics without secrets."""
        try:
            x_api_key = build_x_api_key(self.client_id, self.shared_secret)
        except RuntimeError:
            x_api_key = ""
        return {
            "client_id_present": bool(self.client_id),
            "shared_secret_present": bool(self.shared_secret),
            "access_token_present": bool(self.access_token),
            "shop_id_present": bool(self.shop_id),
            "client_id_length": len(self.client_id or ""),
            "shared_secret_length": len(self.shared_secret or ""),
            "client_id_last_four": safe_last_four(self.client_id),
            "shared_secret_last_four": safe_last_four(self.shared_secret),
            "access_token_last_four": safe_last_four(self.access_token),
            "shop_id_last_four": safe_last_four(self.shop_id),
            "x_api_key_colon_count": x_api_key.count(":"),
            "normalized_credentials": self.normalized_credentials,
        }

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


def _optional_float(value: str | None) -> float:
    if value is None or not value.strip():
        return 0.0
    return float(value)


def _normalized_value(value: str | None) -> str | None:
    return normalize_credential(value).value


def _first_present(*values: str | None) -> str | None:
    for value in values:
        normalized = _normalized_value(value)
        if normalized:
            return normalized
    return None
