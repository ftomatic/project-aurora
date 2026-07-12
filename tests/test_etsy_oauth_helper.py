"""Tests for the Etsy OAuth PKCE helper."""

from __future__ import annotations

import json
import sys
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from urllib import parse

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.etsy_oauth_helper import (  # noqa: E402
    EtsyOAuthConfig,
    build_authorization_url,
    exchange_code_for_token,
    generate_pkce_pair,
    print_export_commands,
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


class EtsyOAuthHelperTest(unittest.TestCase):
    def test_generate_pkce_pair(self) -> None:
        pkce = generate_pkce_pair()

        self.assertGreaterEqual(len(pkce.code_verifier), 43)
        self.assertGreaterEqual(len(pkce.code_challenge), 43)
        self.assertNotIn("=", pkce.code_challenge)

    def test_build_authorization_url(self) -> None:
        config = EtsyOAuthConfig(
            client_id="client-id",
            redirect_uri="http://localhost:8080/callback",
            scopes="listings_w shops_r",
            state="state",
        )

        url = build_authorization_url(config, code_challenge="challenge")
        parsed = parse.urlparse(url)
        query = parse.parse_qs(parsed.query)

        self.assertEqual(parsed.netloc, "www.etsy.com")
        self.assertEqual(query["response_type"], ["code"])
        self.assertEqual(query["client_id"], ["client-id"])
        self.assertEqual(query["code_challenge"], ["challenge"])
        self.assertEqual(query["code_challenge_method"], ["S256"])

    def test_exchange_code_for_token(self) -> None:
        calls = []

        def fake_urlopen(token_request, timeout: int):  # type: ignore[no-untyped-def]
            calls.append((token_request, timeout))
            return FakeResponse({"access_token": "token", "refresh_token": "refresh"})

        token_data = exchange_code_for_token(
            config=EtsyOAuthConfig(
                client_id="client-id",
                redirect_uri="http://localhost:8080/callback",
            ),
            code="auth-code",
            code_verifier="verifier",
            urlopen=fake_urlopen,
        )

        self.assertEqual(token_data["access_token"], "token")
        self.assertEqual(token_data["refresh_token"], "refresh")
        self.assertEqual(len(calls), 1)
        request_body = calls[0][0].data.decode("utf-8")
        parsed_body = parse.parse_qs(request_body)
        self.assertEqual(parsed_body["grant_type"], ["authorization_code"])
        self.assertEqual(parsed_body["code"], ["auth-code"])
        self.assertEqual(parsed_body["code_verifier"], ["verifier"])

    def test_exchange_requires_access_token(self) -> None:
        def fake_urlopen(token_request, timeout: int):  # type: ignore[no-untyped-def]
            return FakeResponse({"refresh_token": "refresh"})

        with self.assertRaises(RuntimeError):
            exchange_code_for_token(
                config=EtsyOAuthConfig(
                    client_id="client-id",
                    redirect_uri="http://localhost:8080/callback",
                ),
                code="auth-code",
                code_verifier="verifier",
                urlopen=fake_urlopen,
            )

    def test_exchange_requires_refresh_token(self) -> None:
        def fake_urlopen(token_request, timeout: int):  # type: ignore[no-untyped-def]
            return FakeResponse({"access_token": "token"})

        with self.assertRaises(RuntimeError) as context:
            exchange_code_for_token(
                config=EtsyOAuthConfig(
                    client_id="client-id",
                    redirect_uri="http://localhost:8080/callback",
                ),
                code="auth-code",
                code_verifier="verifier",
                urlopen=fake_urlopen,
            )

        self.assertIn("refresh_token", str(context.exception))

    def test_print_export_commands_includes_refresh_token(self) -> None:
        output = StringIO()

        with redirect_stdout(output):
            print_export_commands(
                client_id="client-id",
                access_token="access-token",
                refresh_token="refresh-token",
            )

        lines = output.getvalue().splitlines()
        self.assertIn('export ETSY_ACCESS_TOKEN="access-token"', lines)
        self.assertIn('export ETSY_REFRESH_TOKEN="refresh-token"', lines)
        self.assertIn('export ETSY_CLIENT_ID="client-id"', lines)


if __name__ == "__main__":
    unittest.main()
