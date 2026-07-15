"""Look up the authenticated Etsy user's shop id."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from urllib import request

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_PATH))

from project_aurora.integrations.etsy.etsy_client import EtsyClient  # noqa: E402
from project_aurora.integrations.etsy.etsy_config import EtsyConfig  # noqa: E402

API_BASE_URL = "https://openapi.etsy.com/v3/application"


@dataclass(frozen=True, slots=True)
class EtsyShop:
    """Minimal Etsy shop identity."""

    shop_name: str
    shop_id: int


def load_credentials() -> EtsyConfig:
    """Load Etsy credentials from environment variables."""
    config = EtsyConfig.from_environment()
    missing = []
    if not config.client_id:
        missing.append("ETSY_CLIENT_ID")
    if not config.shared_secret:
        missing.append("ETSY_SHARED_SECRET")
    if not config.access_token:
        missing.append("ETSY_ACCESS_TOKEN")
    if missing:
        raise RuntimeError(
            "Missing required environment variables: " + ", ".join(missing)
        )
    return config


def get_authenticated_shop(
    client_id: str,
    shared_secret: str,
    access_token: str,
    api_base_url: str = API_BASE_URL,
    urlopen: Callable[..., Any] = request.urlopen,
) -> EtsyShop:
    """Return the shop owned by the authenticated Etsy user."""
    config = EtsyConfig(
        mode="live",
        client_id=client_id,
        shared_secret=shared_secret,
        access_token=access_token,
        api_base_url=api_base_url,
    )
    client = EtsyClient(config=config, urlopen=urlopen)
    me = client.get_json("/users/me")
    direct_shop = _shop_from_payload(me)
    if direct_shop is not None:
        return direct_shop

    user_id = me.get("user_id") or me.get("userId")
    if user_id is None:
        raise RuntimeError("Etsy user response did not include user_id.")

    shop_payload = client.get_json(f"/users/{user_id}/shops")
    shop = _shop_from_payload(shop_payload)
    if shop is None:
        raise RuntimeError("Etsy shop response did not include a shop.")
    return shop


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
        config = load_credentials()
        client = EtsyClient(config=config)
        me = client.get_json("/users/me")
        shop = _shop_from_payload(me)
        if shop is None:
            user_id = me.get("user_id") or me.get("userId")
            if user_id is None:
                raise RuntimeError(
                    "Etsy user response did not include user_id."
                )
            shop_payload = client.get_json(f"/users/{user_id}/shops")
            shop = _shop_from_payload(shop_payload)
        if shop is None:
            raise RuntimeError("Etsy shop response did not include a shop.")
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
