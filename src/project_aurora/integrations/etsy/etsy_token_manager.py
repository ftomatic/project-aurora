"""Etsy OAuth token refresh support for scheduled Aurora runs."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable
from urllib import parse, request
from urllib.error import HTTPError, URLError

from project_aurora.integrations.etsy.etsy_auth import load_local_env_values


@dataclass(frozen=True, slots=True)
class EtsyTokenRefreshResult:
    """Token refresh result without exposing token values."""

    status: str
    refreshed: bool
    requires_oauth: bool
    message: str


class EtsyTokenManager:
    """Refresh Etsy access tokens using ETSY_REFRESH_TOKEN."""

    def __init__(
        self,
        credential_path: Path,
        token_url: str = "https://api.etsy.com/v3/public/oauth/token",
        urlopen: Callable[..., Any] = request.urlopen,
        now: Callable[[], datetime] = datetime.now,
    ) -> None:
        self._credential_path = credential_path
        self._token_url = token_url
        self._urlopen = urlopen
        self._now = now

    def refresh_if_needed(self, force: bool = False) -> EtsyTokenRefreshResult:
        """Refresh access token when forced or expiry is near."""
        local_values = load_local_env_values(self._credential_path)
        expires_at = _parse_expiry(
            _credential_value(
                "ETSY_ACCESS_TOKEN_EXPIRES_AT",
                local_values,
            )
        )
        if not force and expires_at and expires_at > self._now() + timedelta(minutes=10):
            return EtsyTokenRefreshResult("SKIPPED", False, False, "Token still valid.")

        client_id = _credential_value("ETSY_CLIENT_ID", local_values) or _credential_value(
            "ETSY_KEYSTRING",
            local_values,
        )
        refresh_token = _credential_value("ETSY_REFRESH_TOKEN", local_values)
        if not client_id or not refresh_token:
            return EtsyTokenRefreshResult(
                "OAUTH_REQUIRED",
                False,
                True,
                "ETSY_CLIENT_ID and ETSY_REFRESH_TOKEN are required.",
            )
        os.environ["ETSY_CLIENT_ID"] = client_id
        os.environ["ETSY_REFRESH_TOKEN"] = refresh_token

        body = parse.urlencode(
            {
                "grant_type": "refresh_token",
                "client_id": client_id,
                "refresh_token": refresh_token,
            }
        ).encode("utf-8")
        api_request = request.Request(
            self._token_url,
            data=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        try:
            with self._urlopen(api_request, timeout=30) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            try:
                detail = error.read().decode("utf-8", errors="replace")
            finally:
                error.close()
            return EtsyTokenRefreshResult(
                "FAILED",
                False,
                False,
                f"Etsy token refresh failed with HTTP {error.code}: {detail}",
            )
        except URLError as error:
            return EtsyTokenRefreshResult(
                "FAILED",
                False,
                False,
                f"Etsy token refresh failed: {error.reason}",
            )
        access_token = payload.get("access_token")
        new_refresh = payload.get("refresh_token", refresh_token)
        expires_in = int(payload.get("expires_in", 3600))
        if not access_token:
            return EtsyTokenRefreshResult(
                "OAUTH_REQUIRED",
                False,
                True,
                "Etsy did not return an access token.",
            )
        expires_at_new = self._now() + timedelta(seconds=expires_in)
        os.environ["ETSY_ACCESS_TOKEN"] = str(access_token)
        os.environ["ETSY_REFRESH_TOKEN"] = str(new_refresh)
        os.environ["ETSY_ACCESS_TOKEN_EXPIRES_AT"] = expires_at_new.isoformat()
        self._save_local_credentials(expires_at_new, local_values)
        return EtsyTokenRefreshResult("REFRESHED", True, False, "Token refreshed.")

    def _save_local_credentials(
        self,
        expires_at: datetime,
        local_values: dict[str, object] | None = None,
    ) -> None:
        self._credential_path.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            f"{key}={_credential_value_for_save(key, local_values or {}) or ''}"
            for key in (
                "OPENAI_API_KEY",
                "ETSY_CLIENT_ID",
                "ETSY_SHARED_SECRET",
                "ETSY_ACCESS_TOKEN",
                "ETSY_REFRESH_TOKEN",
                "ETSY_SHOP_ID",
                "ETSY_REDIRECT_URI",
            )
        ]
        lines.append(f"ETSY_ACCESS_TOKEN_EXPIRES_AT={expires_at.isoformat()}")
        self._credential_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _parse_expiry(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _credential_value(key: str, local_values: dict[str, object]) -> str | None:
    value = local_values.get(key)
    normalized = getattr(value, "value", None)
    if isinstance(normalized, str) and normalized:
        return normalized
    env_value = os.getenv(key)
    return env_value if env_value else None


def _credential_value_for_save(
    key: str,
    local_values: dict[str, object],
) -> str | None:
    env_value = os.getenv(key)
    if env_value:
        return env_value
    value = local_values.get(key)
    normalized = getattr(value, "value", None)
    return normalized if isinstance(normalized, str) and normalized else None
