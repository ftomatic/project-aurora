"""Centralized Etsy Open API authentication helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from project_aurora.integrations.etsy.etsy_config import EtsyConfig


@dataclass(frozen=True, slots=True)
class NormalizedCredential:
    """A normalized credential value and whether cleanup was applied."""

    value: str | None
    changed: bool = False


def normalize_credential(value: str | None) -> NormalizedCredential:
    """Strip accidental whitespace and matching outer quotes from a credential."""
    if value is None:
        return NormalizedCredential(value=None, changed=False)
    original = value
    cleaned = value.strip()
    if (
        len(cleaned) >= 2
        and cleaned[0] == cleaned[-1]
        and cleaned[0] in {"'", '"'}
    ):
        cleaned = cleaned[1:-1].strip()
    return NormalizedCredential(
        value=cleaned or None,
        changed=cleaned != original,
    )


def load_local_env_values(path: Path) -> dict[str, NormalizedCredential]:
    """Load normalized KEY=VALUE credentials from a local env file."""
    if not path.exists():
        return {}
    values: dict[str, NormalizedCredential] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line.removeprefix("export ").strip()
        key, raw_value = line.split("=", maxsplit=1)
        values[key.strip()] = normalize_credential(raw_value)
    return values


def build_x_api_key(keystring: str | None, shared_secret: str | None) -> str:
    """Build Etsy's required keystring:shared_secret x-api-key value."""
    key = normalize_credential(keystring).value
    secret = normalize_credential(shared_secret).value
    if not key:
        raise RuntimeError("ETSY_CLIENT_ID is required.")
    if not secret:
        raise RuntimeError("ETSY_SHARED_SECRET is required.")
    return f"{key}:{secret}"


def build_etsy_auth_headers(
    config: "EtsyConfig",
    *,
    include_json: bool = False,
) -> dict[str, str]:
    """Build all Etsy Open API auth headers in one authoritative place."""
    access_token = normalize_credential(config.access_token).value
    if not access_token:
        raise RuntimeError("ETSY_ACCESS_TOKEN is required.")
    headers = {
        "x-api-key": build_x_api_key(config.client_id, config.shared_secret),
        "Authorization": f"Bearer {access_token}",
    }
    if include_json:
        headers["Content-Type"] = "application/json"
    return headers


def safe_last_four(value: str | None) -> str:
    """Return a non-secret suffix for diagnostics."""
    normalized = normalize_credential(value).value
    if not normalized:
        return ""
    return normalized[-4:]
