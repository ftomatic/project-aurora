"""Etsy API client boundary."""

from __future__ import annotations

import json
import mimetypes
import uuid
from pathlib import Path
from typing import Any, Callable
from urllib import request
from urllib.error import HTTPError, URLError

from project_aurora.integrations.etsy.etsy_config import EtsyConfig
from project_aurora.integrations.etsy.etsy_listing_mapper import (
    EtsyDraftListingPayload,
)
from project_aurora.integrations.etsy.etsy_result import EtsyDraftResult
from project_aurora.integrations.etsy.etsy_token_manager import EtsyTokenManager


PROJECT_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_LOCAL_CREDENTIAL_PATH = PROJECT_ROOT / "config" / "aurora.local.env"
DEFAULT_ETSY_CONFIG_PATH = PROJECT_ROOT / "config" / "etsy.yaml"


class EtsyClient:
    """Create Etsy draft listings through an isolated API boundary."""

    def __init__(
        self,
        config: EtsyConfig,
        urlopen: Callable[..., Any] = request.urlopen,
        token_manager: EtsyTokenManager | None = None,
    ) -> None:
        self._config = config
        self._urlopen = urlopen
        self._token_manager = token_manager

    def get_json(self, path: str) -> dict[str, Any]:
        """Execute an authenticated Etsy Open API v3 GET request."""
        return self._request_json(path=path, method="GET")

    def upload_listing_image(
        self,
        listing_id: str,
        image_path: Path,
        rank: int,
    ) -> dict[str, Any]:
        """Upload one image to an existing Etsy listing draft."""
        if not self._config.shop_id:
            raise RuntimeError("ETSY_SHOP_ID is required.")
        if rank < 1:
            raise RuntimeError("Image rank must start at 1.")
        if not image_path.exists() or not image_path.is_file():
            raise RuntimeError(f"Image file does not exist: {image_path}")
        if image_path.stat().st_size <= 0:
            raise RuntimeError(f"Image file is empty: {image_path}")

        body, content_type = self._build_multipart_body(
            fields={"rank": str(rank)},
            file_field="image",
            file_path=image_path,
        )
        api_request = request.Request(
            self._build_url(
                f"/shops/{self._config.shop_id}/listings/"
                f"{listing_id}/images"
            ),
            data=body,
            headers={
                **self._build_headers(),
                "Content-Type": content_type,
            },
            method="POST",
        )
        return self._open_json(api_request)

    def list_listing_images(
        self,
        listing_id: str,
    ) -> tuple[dict[str, Any], ...]:
        """Return listing images already attached to an Etsy listing."""
        response = self.get_json(f"/listings/{listing_id}/images")
        results = response.get("results", ())
        if isinstance(results, list):
            return tuple(item for item in results if isinstance(item, dict))
        return ()

    def upload_listing_digital_file(
        self,
        listing_id: str,
        file_path: Path,
        rank: int | None = None,
    ) -> dict[str, Any]:
        """Upload one customer digital file to an Etsy draft listing."""
        if not self._config.shop_id:
            raise RuntimeError("ETSY_SHOP_ID is required.")
        if not file_path.exists() or not file_path.is_file():
            raise RuntimeError(f"Digital file does not exist: {file_path}")
        if file_path.stat().st_size <= 0:
            raise RuntimeError(f"Digital file is empty: {file_path}")

        fields = {"name": file_path.name}
        if rank is not None:
            fields["rank"] = str(rank)
        body, content_type = self._build_multipart_body(
            fields=fields,
            file_field="file",
            file_path=file_path,
            file_content_type="image/png" if file_path.suffix == ".png" else None,
        )
        api_request = request.Request(
            self._build_url(
                f"/shops/{self._config.shop_id}/listings/"
                f"{listing_id}/files"
            ),
            data=body,
            headers={
                **self._build_headers(),
                "Content-Type": content_type,
            },
            method="POST",
        )
        return self._open_json(api_request)

    def list_listing_digital_files(
        self,
        listing_id: str,
    ) -> tuple[dict[str, Any], ...]:
        """Return digital files already attached to an Etsy listing."""
        if not self._config.shop_id:
            raise RuntimeError("ETSY_SHOP_ID is required.")
        response = self.get_json(
            f"/shops/{self._config.shop_id}/listings/{listing_id}/files"
        )
        results = response.get("results", ())
        if isinstance(results, list):
            return tuple(
                item for item in results if isinstance(item, dict)
            )
        return ()

    def list_shop_draft_listings(self) -> tuple[dict[str, Any], ...]:
        """Return current draft listings for the configured Etsy shop."""
        if not self._config.shop_id:
            raise RuntimeError("ETSY_SHOP_ID is required.")
        response = self.get_json(
            f"/shops/{self._config.shop_id}/listings?state=draft&limit=100"
        )
        results = response.get("results", ())
        if not isinstance(results, list):
            return ()
        return tuple(
            item
            for item in results
            if isinstance(item, dict)
            and str(item.get("state", "")).casefold() == "draft"
        )

    def update_listing_fields(
        self,
        listing_id: str,
        fields: dict[str, Any],
    ) -> dict[str, Any]:
        """Update selected Etsy listing fields without creating a listing."""
        if not self._config.shop_id:
            raise RuntimeError("ETSY_SHOP_ID is required.")
        if not fields:
            raise RuntimeError("At least one listing field is required.")
        return self._request_json(
            path=f"/shops/{self._config.shop_id}/listings/{listing_id}",
            method="PATCH",
            data=fields,
        )

    def update_listing_renewal_default(
        self,
        listing_id: str,
    ) -> dict[str, Any]:
        """Set an Etsy listing to automatic renewal."""
        return self.update_listing_fields(
            listing_id=listing_id,
            fields={"should_auto_renew": True},
        )

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
        return self._open_json(api_request)

    def _open_json(self, api_request: request.Request) -> dict[str, Any]:
        return self._open_json_once(api_request, retry_on_invalid_token=True)

    def _open_json_once(
        self,
        api_request: request.Request,
        retry_on_invalid_token: bool,
    ) -> dict[str, Any]:
        try:
            with self._urlopen(api_request, timeout=30) as response:
                raw_body = response.read().decode("utf-8")
        except HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            if (
                retry_on_invalid_token
                and error.code == 401
                and _is_invalid_token_response(detail)
                and self._refresh_access_token()
            ):
                retry_request = self._clone_request(api_request)
                return self._open_json_once(
                    retry_request,
                    retry_on_invalid_token=False,
                )
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

    def _refresh_access_token(self) -> bool:
        manager = self._token_manager or EtsyTokenManager(DEFAULT_LOCAL_CREDENTIAL_PATH)
        result = manager.refresh_if_needed(force=True)
        if not result.refreshed:
            return False
        self._config = EtsyConfig.from_environment(DEFAULT_ETSY_CONFIG_PATH)
        return True

    def _clone_request(self, api_request: request.Request) -> request.Request:
        headers = dict(api_request.header_items())
        headers.update(self._build_headers(include_json=_is_json_request(headers)))
        content_type = headers.get("Content-type") or headers.get("Content-Type")
        if content_type:
            headers["Content-Type"] = content_type
        return request.Request(
            api_request.full_url,
            data=api_request.data,
            headers=headers,
            method=api_request.get_method(),
        )

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

    def _build_multipart_body(
        self,
        fields: dict[str, str],
        file_field: str,
        file_path: Path,
        file_content_type: str | None = None,
    ) -> tuple[bytes, str]:
        boundary = f"aurora-{uuid.uuid4().hex}"
        lines: list[bytes] = []
        for name, value in fields.items():
            lines.extend(
                (
                    f"--{boundary}".encode("utf-8"),
                    (
                        f'Content-Disposition: form-data; name="{name}"'
                    ).encode("utf-8"),
                    b"",
                    value.encode("utf-8"),
                )
            )

        content_type = file_content_type or (
            mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
        )
        lines.extend(
            (
                f"--{boundary}".encode("utf-8"),
                (
                    "Content-Disposition: form-data; "
                    f'name="{file_field}"; filename="{file_path.name}"'
                ).encode("utf-8"),
                f"Content-Type: {content_type}".encode("utf-8"),
                b"",
                file_path.read_bytes(),
                f"--{boundary}--".encode("utf-8"),
                b"",
            )
        )
        return b"\r\n".join(lines), f"multipart/form-data; boundary={boundary}"


def _is_invalid_token_response(detail: str) -> bool:
    lowered = detail.casefold()
    return "invalid_token" in lowered or "access token expired" in lowered


def _is_json_request(headers: dict[str, str]) -> bool:
    content_type = (
        headers.get("Content-type")
        or headers.get("Content-Type")
        or ""
    )
    return "application/json" in content_type.casefold()
