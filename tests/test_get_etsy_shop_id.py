"""Tests for Etsy shop id lookup helper."""

from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.get_etsy_shop_id import (  # noqa: E402
    EtsyShop,
    get_authenticated_shop,
    load_credentials,
)


class FakeResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")


class EtsyShopLookupTest(unittest.TestCase):
    def test_load_credentials_from_environment(self) -> None:
        with patch.dict(
            os.environ,
            {
                "ETSY_CLIENT_ID": "client",
                "ETSY_ACCESS_TOKEN": "token",
            },
            clear=True,
        ):
            self.assertEqual(load_credentials(), ("client", "token"))

    def test_missing_credentials_raise_clear_error(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(RuntimeError) as context:
                load_credentials()

        self.assertIn("ETSY_CLIENT_ID", str(context.exception))
        self.assertIn("ETSY_ACCESS_TOKEN", str(context.exception))

    def test_get_authenticated_shop_from_user_then_shop_endpoint(self) -> None:
        calls = []
        responses = [
            FakeResponse({"user_id": 123}),
            FakeResponse(
                {
                    "results": [
                        {
                            "shop_id": 456,
                            "shop_name": "RainbowMilkStudio",
                        }
                    ]
                }
            ),
        ]

        def fake_urlopen(api_request, timeout: int):  # type: ignore[no-untyped-def]
            calls.append((api_request, timeout))
            return responses.pop(0)

        shop = get_authenticated_shop(
            client_id="client",
            access_token="token",
            api_base_url="https://example.test/v3/application",
            urlopen=fake_urlopen,
        )

        self.assertEqual(
            shop,
            EtsyShop(shop_name="RainbowMilkStudio", shop_id=456),
        )
        self.assertEqual(len(calls), 2)
        self.assertIn("/users/me", calls[0][0].full_url)
        self.assertIn("/users/123/shops", calls[1][0].full_url)
        self.assertEqual(calls[0][0].headers["X-api-key"], "client")
        self.assertEqual(calls[0][0].headers["Authorization"], "Bearer token")

    def test_get_authenticated_shop_direct_payload(self) -> None:
        def fake_urlopen(api_request, timeout: int):  # type: ignore[no-untyped-def]
            return FakeResponse(
                {
                    "shop_id": 456,
                    "shop_name": "RainbowMilkStudio",
                }
            )

        shop = get_authenticated_shop(
            client_id="client",
            access_token="token",
            urlopen=fake_urlopen,
        )

        self.assertEqual(shop.shop_id, 456)
        self.assertEqual(shop.shop_name, "RainbowMilkStudio")


if __name__ == "__main__":
    unittest.main()
