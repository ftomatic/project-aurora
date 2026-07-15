"""Etsy OAuth token refresh support for scheduled Aurora runs."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable
from urllib import parse, request


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
        expires_at = _parse_expiry(os.getenv("ETSY_ACCESS_TOKEN_EXPIRES_AT"))
        if not force and expires_at and expires_at > self._now() + timedelta(minutes=10):
            return EtsyTokenRefreshResult("SKIPPED", False, False, "Token still valid.")

        client_id = os.getenv("ETSY_CLIENT_ID")
        refresh_token = os.getenv("ETSY_REFRESH_TOKEN")
        if not client_id or not refresh_token:
            return EtsyTokenRefreshResult(
                "OAUTH_REQUIRED",
                False,
                True,
                "ETSY_CLIENT_ID and ETSY_REFRESH_TOKEN are required.",
            )

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
        with self._urlopen(api_request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
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
        self._save_local_credentials(expires_at_new)
        return EtsyTokenRefreshResult("REFRESHED", True, False, "Token refreshed.")

    def _save_local_credentials(self, expires_at: datetime) -> None:
        self._credential_path.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            f"{key}={os.getenv(key, '')}"
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
