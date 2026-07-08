"""Etsy API client boundary."""

from __future__ import annotations

import json
from typing import Any
from urllib import request

from project_aurora.integrations.etsy.etsy_config import EtsyConfig
from project_aurora.integrations.etsy.etsy_listing_mapper import (
    EtsyDraftListingPayload,
)
from project_aurora.integrations.etsy.etsy_result import EtsyDraftResult


class EtsyClient:
    """Create Etsy draft listings through an isolated API boundary."""

    def __init__(self, config: EtsyConfig) -> None:
        self._config = config

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
        if not self._config.shop_id:
            raise RuntimeError("Etsy shop id is required.")
        url = (
            f"{self._config.api_base_url}/shops/"
            f"{self._config.shop_id}/listings"
        )
        request_body = json.dumps(payload.to_dict()).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "x-api-key": str(self._config.client_id),
            "Authorization": f"Bearer {self._config.access_token}",
        }
        api_request = request.Request(
            url,
            data=request_body,
            headers=headers,
            method="POST",
        )
        with request.urlopen(api_request, timeout=30) as response:
            raw_body = response.read().decode("utf-8")
        response_data: dict[str, Any] = json.loads(raw_body)
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
