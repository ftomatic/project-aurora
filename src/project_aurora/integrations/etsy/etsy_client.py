"""Etsy API client boundary."""

from __future__ import annotations

import json
from typing import Any, Callable
from urllib import request
from urllib.error import HTTPError, URLError

from project_aurora.integrations.etsy.etsy_config import EtsyConfig
from project_aurora.integrations.etsy.etsy_listing_mapper import (
    EtsyDraftListingPayload,
)
from project_aurora.integrations.etsy.etsy_result import EtsyDraftResult


class EtsyClient:
    """Create Etsy draft listings through an isolated API boundary."""

    def __init__(
        self,
        config: EtsyConfig,
        urlopen: Callable[..., Any] = request.urlopen,
    ) -> None:
        self._config = config
        self._urlopen = urlopen

    def get_json(self, path: str) -> dict[str, Any]:
        """Execute an authenticated Etsy Open API v3 GET request."""
        return self._request_json(path=path, method="GET")

    def create_draft_listing(
        self,
        payload: EtsyDraftListingPayload,
    ) -> EtsyDraftResult:
        """Create a draft listing or return a mock result."""
        if self._config.is_mock_mode:
            return EtsyDraftResult(
                status="READY_FOR_ETSY_DRAFT",
                etsy_listing_id=None,
                draft_url=None,
                warnings=("Mock mode active; Etsy API was not called.",),
                metadata={
                    "mode": self._config.mode,
                    "api_called": False,
                    "payload": payload.to_dict(),
                },
            )

        missing = self._config.validate_for_api(is_digital=payload.is_digital)
        if missing:
            return EtsyDraftResult(
                status="CONFIGURATION_REQUIRED",
                etsy_listing_id=None,
                draft_url=None,
                errors=(f"Missing Etsy configuration: {', '.join(missing)}.",),
                metadata={"api_called": False, "missing": missing},
            )

        return self._post_draft_listing(payload)

    def _post_draft_listing(
        self,
        payload: EtsyDraftListingPayload,
    ) -> EtsyDraftResult:
        response_data = self._request_json(
            path=f"/shops/{self._config.shop_id}/listings",
            method="POST",
            data=payload.to_dict(),
        )
        listing_id = str(response_data.get("listing_id", ""))
        return EtsyDraftResult(
            status="DRAFT_CREATED",
            etsy_listing_id=listing_id or None,
            draft_url=(
                f"https://www.etsy.com/listing/{listing_id}"
                if listing_id
                else None
            ),
            metadata={
                "api_called": True,
                "response": response_data,
                "state": "draft",
            },
        )

    def _request_json(
        self,
        path: str,
        method: str,
        data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        url = self._build_url(path)
        request_body = (
            json.dumps(data).encode("utf-8") if data is not None else None
        )
        api_request = request.Request(
            url,
            data=request_body,
            headers=self._build_headers(include_json=data is not None),
            method=method,
        )
        try:
            with self._urlopen(api_request, timeout=30) as response:
                raw_body = response.read().decode("utf-8")
        except HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"Etsy API request failed with HTTP {error.code}: {detail}"
            ) from error
        except URLError as error:
            raise RuntimeError(
                f"Etsy API request failed: {error.reason}"
            ) from error
        response_data = json.loads(raw_body)
        if not isinstance(response_data, dict):
            raise RuntimeError("Etsy API response was not a JSON object.")
        return response_data

    def _build_url(self, path: str) -> str:
        base_url = self._config.api_base_url.rstrip("/")
        normalized_path = path if path.startswith("/") else f"/{path}"
        return f"{base_url}{normalized_path}"

    def _build_headers(self, include_json: bool = False) -> dict[str, str]:
        if not self._config.client_id:
            raise RuntimeError("ETSY_CLIENT_ID is required.")
        if not self._config.shared_secret:
            raise RuntimeError("ETSY_SHARED_SECRET is required.")
        if not self._config.access_token:
            raise RuntimeError("ETSY_ACCESS_TOKEN is required.")

        headers = {
            "x-api-key": (
                f"{self._config.client_id}:{self._config.shared_secret}"
            ),
            "Authorization": f"Bearer {self._config.access_token}",
        }
        if include_json:
            headers["Content-Type"] = "application/json"
        return headers
