"""Tests for Etsy seller taxonomy lookup helper."""

from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.search_etsy_taxonomy import (  # noqa: E402
    TaxonomyMatch,
    fetch_taxonomy_nodes,
    find_best_match,
    load_config_from_environment,
    search_taxonomy,
)
from project_aurora.integrations.etsy.etsy_client import EtsyClient  # noqa: E402
from project_aurora.integrations.etsy.etsy_config import EtsyConfig  # noqa: E402


class FakeResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")


class EtsyTaxonomyTest(unittest.TestCase):
    def test_load_config_from_environment(self) -> None:
        with patch.dict(
            os.environ,
            {
                "ETSY_CLIENT_ID": "fake_keystring",
                "ETSY_SHARED_SECRET": "fake_shared_secret",
                "ETSY_ACCESS_TOKEN": "fake_token",
            },
            clear=True,
        ):
            config = load_config_from_environment()

        self.assertEqual(config.client_id, "fake_keystring")
        self.assertEqual(config.shared_secret, "fake_shared_secret")
        self.assertEqual(config.access_token, "fake_token")

    def test_missing_credentials_raise_clear_error(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(RuntimeError) as context:
                load_config_from_environment()

        message = str(context.exception)
        self.assertIn("ETSY_CLIENT_ID", message)
        self.assertIn("ETSY_SHARED_SECRET", message)
        self.assertIn("ETSY_ACCESS_TOKEN", message)

    def test_search_taxonomy_ranks_best_name_and_path_match(self) -> None:
        nodes = [
            {
                "id": 100,
                "name": "Paper & Party Supplies",
                "children": [
                    {
                        "id": 200,
                        "name": "Party Supplies",
                        "children": [
                            {
                                "id": 300,
                                "name": "Party Printable Templates",
                            }
                        ],
                    }
                ],
            },
            {
                "id": 400,
                "name": "Wall Decor",
                "path": ["Home & Living", "Wall Decor"],
            },
        ]

        matches = search_taxonomy("party printable", nodes)

        self.assertEqual(
            matches[0],
            TaxonomyMatch(
                taxonomy_name="Party Printable Templates",
                full_taxonomy_path=(
                    "Paper & Party Supplies > Party Supplies > "
                    "Party Printable Templates"
                ),
                taxonomy_id=300,
                score=153,
            ),
        )

    def test_fetch_taxonomy_uses_etsy_client_authenticated_request(self) -> None:
        calls = []

        def fake_urlopen(api_request, timeout: int):  # type: ignore[no-untyped-def]
            calls.append((api_request, timeout))
            return FakeResponse(
                {
                    "results": [
                        {
                            "seller_taxonomy_id": 123,
                            "name": "Party Supplies",
                        }
                    ]
                }
            )

        client = EtsyClient(
            config=EtsyConfig(
                mode="live",
                client_id="fake_keystring",
                shared_secret="fake_shared_secret",
                access_token="fake_token",
                api_base_url="https://example.test/v3/application",
            ),
            urlopen=fake_urlopen,
        )

        nodes = fetch_taxonomy_nodes(client)

        self.assertEqual(nodes[0]["name"], "Party Supplies")
        self.assertEqual(len(calls), 1)
        self.assertIn("/seller-taxonomy/nodes", calls[0][0].full_url)
        self.assertEqual(
            calls[0][0].headers["X-api-key"],
            "fake_keystring:fake_shared_secret",
        )
        self.assertEqual(
            calls[0][0].headers["Authorization"],
            "Bearer fake_token",
        )

    def test_find_best_match_from_mocked_etsy_response(self) -> None:
        def fake_urlopen(api_request, timeout: int):  # type: ignore[no-untyped-def]
            return FakeResponse(
                {
                    "results": [
                        {
                            "taxonomy_id": 500,
                            "name": "Invitations",
                            "path": [
                                "Paper & Party Supplies",
                                "Paper",
                                "Invitations",
                            ],
                        },
                        {
                            "taxonomy_id": 600,
                            "name": "Printable Party Games",
                            "path": [
                                "Paper & Party Supplies",
                                "Party Supplies",
                                "Printable Party Games",
                            ],
                        },
                    ]
                }
            )

        client = EtsyClient(
            config=EtsyConfig(
                mode="live",
                client_id="fake_keystring",
                shared_secret="fake_shared_secret",
                access_token="fake_token",
            ),
            urlopen=fake_urlopen,
        )

        match = find_best_match("party printable", client)

        self.assertEqual(match.taxonomy_name, "Printable Party Games")
        self.assertEqual(match.taxonomy_id, 600)


if __name__ == "__main__":
    unittest.main()
