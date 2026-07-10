"""Look up the authenticated Etsy user's shop id."""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from typing import Any, Callable
from urllib import request
from urllib.error import HTTPError, URLError


API_BASE_URL = "https://openapi.etsy.com/v3/application"


@dataclass(frozen=True, slots=True)
class EtsyShop:
    """Minimal Etsy shop identity."""

    shop_name: str
    shop_id: int


def load_credentials() -> tuple[str, str]:
    """Load Etsy credentials from environment variables."""
    client_id = os.getenv("ETSY_CLIENT_ID")
    access_token = os.getenv("ETSY_ACCESS_TOKEN")
    missing = []
    if not client_id:
        missing.append("ETSY_CLIENT_ID")
    if not access_token:
        missing.append("ETSY_ACCESS_TOKEN")
    if missing:
        raise RuntimeError(
            "Missing required environment variables: " + ", ".join(missing)
        )
    return str(client_id), str(access_token)


def get_authenticated_shop(
    client_id: str,
    access_token: str,
    api_base_url: str = API_BASE_URL,
    urlopen: Callable[..., Any] = request.urlopen,
) -> EtsyShop:
    """Return the shop owned by the authenticated Etsy user."""
    me = _get_json(
        url=f"{api_base_url}/users/me",
        client_id=client_id,
        access_token=access_token,
        urlopen=urlopen,
    )
    direct_shop = _shop_from_payload(me)
    if direct_shop is not None:
        return direct_shop

    user_id = me.get("user_id") or me.get("userId")
    if user_id is None:
        raise RuntimeError("Etsy user response did not include user_id.")

    shop_payload = _get_json(
        url=f"{api_base_url}/users/{user_id}/shops",
        client_id=client_id,
        access_token=access_token,
        urlopen=urlopen,
    )
    shop = _shop_from_payload(shop_payload)
    if shop is None:
        raise RuntimeError("Etsy shop response did not include a shop.")
    return shop


def _get_json(
    url: str,
    client_id: str,
    access_token: str,
    urlopen: Callable[..., Any],
) -> dict[str, Any]:
    api_request = request.Request(
        url,
        headers={
            "x-api-key": client_id,
            "Authorization": f"Bearer {access_token}",
        },
        method="GET",
    )
    try:
        with urlopen(api_request, timeout=30) as response:
            raw_body = response.read().decode("utf-8")
    except HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"Etsy API request failed with HTTP {error.code}: {detail}"
        ) from error
    except URLError as error:
        raise RuntimeError(f"Etsy API request failed: {error.reason}") from error

    payload = json.loads(raw_body)
    if not isinstance(payload, dict):
        raise RuntimeError("Etsy API response was not a JSON object.")
    return payload


def _shop_from_payload(payload: dict[str, Any]) -> EtsyShop | None:
    candidates: list[Any] = []
    if "results" in payload:
        results = payload["results"]
        if isinstance(results, list):
            candidates.extend(results)
        else:
            candidates.append(results)
    candidates.append(payload)

    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        shop_id = candidate.get("shop_id") or candidate.get("shopId")
        shop_name = candidate.get("shop_name") or candidate.get("shopName")
        if shop_id is not None and shop_name:
            return EtsyShop(shop_name=str(shop_name), shop_id=int(shop_id))
    return None


def main() -> None:
    """Print the authenticated user's Etsy shop name and id."""
    try:
        client_id, access_token = load_credentials()
        shop = get_authenticated_shop(
            client_id=client_id,
            access_token=access_token,
        )
    except RuntimeError as error:
        print("Error")
        print(error)
        raise SystemExit(1) from error

    print("Shop Name")
    print(shop.shop_name)
    print("Shop ID")
    print(shop.shop_id)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Cancelled.")
        sys.exit(130)
