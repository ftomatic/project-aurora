"""Upload generated Aurora images to an existing Etsy draft listing."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from project_aurora.integrations.etsy.etsy_client import EtsyClient
from project_aurora.integrations.etsy.etsy_config import EtsyConfig
from project_aurora.integrations.etsy.etsy_result import (
    EtsyImageUploadAttempt,
    EtsyImageUploadResult,
)
from project_aurora.image_generation.image_inspector import inspect_png
from project_aurora.storage.memory_manager import MemoryManager


class EtsyImageUploadService:
    """Coordinate local generated PNGs into Etsy listing image uploads."""

    def __init__(
        self,
        config: EtsyConfig,
        memory: MemoryManager,
        images_dir: Path,
        client: EtsyClient | None = None,
        max_images: int = 10,
    ) -> None:
        self._config = config
        self._memory = memory
        self._images_dir = images_dir
        self._client = client or EtsyClient(config)
        self._max_images = max_images

    def upload_latest_draft_images(self) -> EtsyImageUploadResult:
        """Upload generated PNG images to the latest stored Etsy draft."""
        draft = self._load_latest_draft()
        listing_id = self._listing_id_from_draft(draft)
        image_files = self._find_images()
        invalid_images = self._invalid_images(image_files[: self._max_images])
        missing = self._missing_config()
        errors: list[str] = []
        if missing:
            errors.append(
                "Missing Etsy configuration: " + ", ".join(missing) + "."
            )
        if not self._is_successful_draft(draft):
            errors.append("Latest Etsy draft result is not successful.")
        if not listing_id:
            errors.append("Latest Etsy draft does not include etsy_listing_id.")
        if not image_files:
            errors.append("No non-empty PNG image files found.")
        if invalid_images:
            errors.extend(invalid_images)
        if errors:
            result = EtsyImageUploadResult(
                status="CONFIGURATION_REQUIRED",
                etsy_listing_id=listing_id,
                images_found=len(image_files),
                images_uploaded=0,
                failed=0,
                errors=tuple(errors),
                metadata={"api_called": False, "missing": missing},
            )
            self._save_result(result)
            return result

        attempts: list[EtsyImageUploadAttempt] = []
        for rank, image_path in enumerate(image_files[: self._max_images], start=1):
            attempts.append(self._upload_one(str(listing_id), image_path, rank))

        uploaded = sum(1 for attempt in attempts if attempt.status == "SUCCESS")
        failed = sum(1 for attempt in attempts if attempt.status != "SUCCESS")
        result = EtsyImageUploadResult(
            status="SUCCESS" if failed == 0 else "PARTIAL_FAILURE",
            etsy_listing_id=str(listing_id),
            images_found=len(image_files),
            images_uploaded=uploaded,
            failed=failed,
            attempts=tuple(attempts),
            metadata={"api_called": bool(attempts), "max_images": self._max_images},
        )
        self._save_result(result)
        return result

    def _upload_one(
        self,
        listing_id: str,
        image_path: Path,
        rank: int,
    ) -> EtsyImageUploadAttempt:
        try:
            response = self._client.upload_listing_image(
                listing_id=listing_id,
                image_path=image_path,
                rank=rank,
            )
        except RuntimeError as error:
            return EtsyImageUploadAttempt(
                image_path=str(image_path),
                rank=rank,
                status="FAILED",
                errors=(str(error),),
            )

        image_id = response.get("listing_image_id") or response.get("image_id")
        return EtsyImageUploadAttempt(
            image_path=str(image_path),
            rank=rank,
            status="SUCCESS",
            etsy_image_id=str(image_id) if image_id is not None else None,
            metadata={"response": response},
        )

    def _load_latest_draft(self) -> dict[str, Any]:
        try:
            return self._memory.load_etsy_draft_result()
        except FileNotFoundError as error:
            raise RuntimeError("No latest Etsy draft result found.") from error

    @staticmethod
    def _listing_id_from_draft(draft: dict[str, Any]) -> str | None:
        listing_id = draft.get("etsy_listing_id")
        if isinstance(listing_id, str) and listing_id.strip():
            return listing_id.strip()
        return None

    @staticmethod
    def _is_successful_draft(draft: dict[str, Any]) -> bool:
        status = draft.get("status")
        return isinstance(status, str) and status.strip().upper() == "DRAFT_CREATED"

    def _find_images(self) -> list[Path]:
        if not self._images_dir.exists():
            return []
        return [
            path
            for path in sorted(self._images_dir.glob("*.png"), key=lambda p: p.name)
            if path.is_file() and path.stat().st_size > 0
        ]

    @staticmethod
    def _invalid_images(image_files: list[Path]) -> tuple[str, ...]:
        errors: list[str] = []
        for image_path in image_files:
            inspection = inspect_png(image_path)
            if not inspection.is_valid:
                errors.append(
                    "Generated image is not a valid visible PNG: "
                    f"{image_path.name} ({inspection.classification})."
                )
        return tuple(errors)

    def _missing_config(self) -> tuple[str, ...]:
        missing: list[str] = []
        if not self._config.shop_id:
            missing.append("ETSY_SHOP_ID")
        if not self._config.client_id:
            missing.append("ETSY_CLIENT_ID")
        if not self._config.shared_secret:
            missing.append("ETSY_SHARED_SECRET")
        if not self._config.access_token:
            missing.append("ETSY_ACCESS_TOKEN")
        return tuple(missing)

    def _save_result(self, result: EtsyImageUploadResult) -> None:
        self._memory.save_etsy_image_upload_result(result)
