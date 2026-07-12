"""Interactive Etsy OAuth PKCE helper for Aurora."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import sys
from dataclasses import dataclass
from typing import Any, Callable
from urllib import parse, request
from urllib.error import HTTPError, URLError


AUTHORIZATION_URL = "https://www.etsy.com/oauth/connect"
TOKEN_URL = "https://api.etsy.com/v3/public/oauth/token"
DEFAULT_SCOPES = "listings_r listings_w shops_r profile_r"
DEFAULT_REDIRECT_URI = "http://localhost:8080/oauth/redirect"


@dataclass(frozen=True, slots=True)
class PKCEPair:
    """PKCE verifier/challenge pair."""

    code_verifier: str
    code_challenge: str


@dataclass(frozen=True, slots=True)
class EtsyOAuthConfig:
    """Etsy OAuth helper configuration."""

    client_id: str
    redirect_uri: str
    scopes: str = DEFAULT_SCOPES
    state: str = "aurora-oauth"


def generate_pkce_pair() -> PKCEPair:
    """Generate an Etsy-compatible PKCE verifier and challenge."""
    code_verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    code_challenge = (
        base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    )
    return PKCEPair(
        code_verifier=code_verifier,
        code_challenge=code_challenge,
    )


def build_authorization_url(
    config: EtsyOAuthConfig,
    code_challenge: str,
) -> str:
    """Build the Etsy authorization URL for PKCE OAuth."""
    query = parse.urlencode(
        {
            "response_type": "code",
            "redirect_uri": config.redirect_uri,
            "scope": config.scopes,
            "client_id": config.client_id,
            "state": config.state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }
    )
    return f"{AUTHORIZATION_URL}?{query}"


def exchange_code_for_token(
    config: EtsyOAuthConfig,
    code: str,
    code_verifier: str,
    urlopen: Callable[..., Any] = request.urlopen,
) -> dict[str, Any]:
    """Exchange an Etsy authorization code for an access token."""
    payload = parse.urlencode(
        {
            "grant_type": "authorization_code",
            "client_id": config.client_id,
            "redirect_uri": config.redirect_uri,
            "code": code,
            "code_verifier": code_verifier,
        }
    ).encode("utf-8")
    token_request = request.Request(
        TOKEN_URL,
        data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )

    try:
        with urlopen(token_request, timeout=30) as response:
            raw_body = response.read().decode("utf-8")
    except HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"Etsy token exchange failed with HTTP {error.code}: {detail}"
        ) from error
    except URLError as error:
        raise RuntimeError(f"Etsy token exchange failed: {error.reason}") from error

    token_data = json.loads(raw_body)
    access_token = token_data.get("access_token")
    if not isinstance(access_token, str) or not access_token:
        raise RuntimeError("Etsy token response did not include access_token.")
    refresh_token = token_data.get("refresh_token")
    if not isinstance(refresh_token, str) or not refresh_token:
        raise RuntimeError("Etsy token response did not include refresh_token.")
    return token_data


def print_export_commands(
    client_id: str,
    access_token: str,
    refresh_token: str,
) -> None:
    """Print shell export commands without writing secrets to disk."""
    print("")
    print("Environment exports")
    print("-------------------")
    print(f'export ETSY_ACCESS_TOKEN="{access_token}"')
    print(f'export ETSY_REFRESH_TOKEN="{refresh_token}"')
    print(f'export ETSY_CLIENT_ID="{client_id}"')


def _prompt_value(label: str, default: str | None = None) -> str:
    suffix = f" [{default}]" if default else ""
    value = input(f"{label}{suffix}: ").strip()
    if value:
        return value
    if default:
        return default
    raise RuntimeError(f"{label} is required.")


def main() -> None:
    """Run the interactive Etsy OAuth helper."""
    print("ETSY OAUTH PKCE HELPER")
    print("")
    print("This helper prints tokens only. It does not save secrets to disk.")
    print("")

    client_id = os.getenv("ETSY_CLIENT_ID") or _prompt_value("ETSY_CLIENT_ID")
    redirect_uri = os.getenv("ETSY_REDIRECT_URI") or _prompt_value(
        "Redirect URI",
        DEFAULT_REDIRECT_URI,
    )
    scopes = os.getenv("ETSY_SCOPES", DEFAULT_SCOPES)
    config = EtsyOAuthConfig(
        client_id=client_id,
        redirect_uri=redirect_uri,
        scopes=scopes,
        state=secrets.token_urlsafe(16),
    )
    pkce = generate_pkce_pair()
    authorization_url = build_authorization_url(config, pkce.code_challenge)

    print("Instructions")
    print("------------")
    print("1. Open this URL:")
    print(authorization_url)
    print("")
    print("2. Approve the app in Etsy.")
    print("3. Copy the redirected `code` query parameter.")
    print("4. Paste the code below.")
    print("")

    code = _prompt_value("Authorization code")
    try:
        token_data = exchange_code_for_token(
            config=config,
            code=code,
            code_verifier=pkce.code_verifier,
        )
    except RuntimeError as error:
        print("")
        print("Status")
        print("FAILED")
        print("")
        print("Reason")
        print(error)
        raise SystemExit(1) from error

    print("")
    print("Status")
    print("SUCCESS")
    print_export_commands(
        client_id=config.client_id,
        access_token=str(token_data["access_token"]),
        refresh_token=str(token_data["refresh_token"]),
    )


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("")
        print("Cancelled.")
        sys.exit(130)
