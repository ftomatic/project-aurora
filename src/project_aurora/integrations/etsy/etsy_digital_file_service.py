"""Upload customer digital PNG files to Etsy draft listings."""

from __future__ import annotations

from pathlib import Path

from project_aurora.image_generation.commercial_image_exporter import (
    validate_commercial_png,
)
from project_aurora.integrations.etsy.etsy_client import EtsyClient
from project_aurora.integrations.etsy.etsy_config import EtsyConfig
from project_aurora.integrations.etsy.etsy_result import (
    EtsyDigitalFileUploadAttempt,
    EtsyDigitalFileUploadResult,
)
from project_aurora.storage.memory_manager import MemoryManager


MAX_DIGITAL_FILE_SIZE_BYTES = 20 * 1024 * 1024
REQUIRED_DIGITAL_FILE_COUNT = 4


class EtsyDigitalFileService:
    """Validate and upload four final PNG files to an Etsy draft listing."""

    def __init__(
        self,
        config: EtsyConfig,
        memory: MemoryManager | None = None,
        client: EtsyClient | None = None,
        required_count: int = REQUIRED_DIGITAL_FILE_COUNT,
    ) -> None:
        self._config = config
        self._memory = memory
        self._client = client or EtsyClient(config)
        self._required_count = required_count

    def upload_digital_files(
        self,
        listing_id: str | None,
        final_images_dir: Path,
    ) -> EtsyDigitalFileUploadResult:
        """Upload exactly four final commercial PNGs to an existing draft."""
        files = self._find_pngs(final_images_dir)
        errors = list(self._preflight_errors(listing_id, final_images_dir, files))
        if errors:
            result = EtsyDigitalFileUploadResult(
                status="CONFIGURATION_REQUIRED",
                etsy_listing_id=listing_id,
                digital_file_path=str(final_images_dir),
                uploaded=False,
                files_found=len(files),
                files_uploaded=0,
                failed=0,
                errors=tuple(errors),
                metadata={"api_called": False},
            )
            self._save_result(result)
            return result

        attempts: list[EtsyDigitalFileUploadAttempt] = []
        for rank, file_path in enumerate(files, start=1):
            attempts.append(self._upload_one(str(listing_id), file_path, rank))

        uploaded = sum(1 for attempt in attempts if attempt.status == "SUCCESS")
        failed = len(attempts) - uploaded
        result = EtsyDigitalFileUploadResult(
            status="SUCCESS" if failed == 0 else "PARTIAL_FAILURE",
            etsy_listing_id=listing_id,
            digital_file_path=str(final_images_dir),
            uploaded=failed == 0,
            files_found=len(files),
            files_uploaded=uploaded,
            failed=failed,
            attempts=tuple(attempts),
            metadata={"api_called": bool(attempts)},
        )
        self._save_result(result)
        return result

    def upload_digital_file(
        self,
        listing_id: str | None,
        file_path: Path,
    ) -> EtsyDigitalFileUploadResult:
        """Backward-compatible wrapper for a single file upload."""
        directory = file_path.parent
        return self.upload_digital_files(listing_id=listing_id, final_images_dir=directory)

    def _upload_one(
        self,
        listing_id: str,
        file_path: Path,
        rank: int,
    ) -> EtsyDigitalFileUploadAttempt:
        try:
            response = self._client.upload_listing_digital_file(
                listing_id=listing_id,
                file_path=file_path,
                rank=rank,
            )
        except RuntimeError as error:
            return EtsyDigitalFileUploadAttempt(
                filename=file_path.name,
                rank=rank,
                status="FAILED",
                errors=(str(error),),
            )

        file_id = (
            response.get("listing_file_id")
            or response.get("file_id")
            or response.get("digital_file_id")
        )
        return EtsyDigitalFileUploadAttempt(
            filename=file_path.name,
            rank=rank,
            status="SUCCESS",
            etsy_file_id=str(file_id) if file_id is not None else None,
            metadata={"response": response},
        )

    def _preflight_errors(
        self,
        listing_id: str | None,
        final_images_dir: Path,
        files: tuple[Path, ...],
    ) -> tuple[str, ...]:
        errors: list[str] = []
        missing = self._missing_config()
        if missing:
            errors.append(
                "Missing Etsy configuration: " + ", ".join(missing) + "."
            )
        if not listing_id:
            errors.append("etsy_listing_id is required.")
        if final_images_dir.name != "final_product_images":
            errors.append("Digital file upload must use final_product_images only.")
        if len(files) != self._required_count:
            errors.append(
                f"Exactly {self._required_count} final PNG files are required, "
                f"found {len(files)}."
            )
        for file_path in files:
            if file_path.stat().st_size >= MAX_DIGITAL_FILE_SIZE_BYTES:
                errors.append(
                    f"{file_path.name} exceeds Etsy's 20 MB digital file limit."
                )
            errors.extend(
                f"{file_path.name}: {error}"
                for error in validate_commercial_png(file_path)
            )
        return tuple(errors)

    @staticmethod
    def _find_pngs(final_images_dir: Path) -> tuple[Path, ...]:
        if not final_images_dir.exists():
            return ()
        return tuple(sorted(final_images_dir.glob("*.png"), key=lambda path: path.name))

    def _missing_config(self) -> tuple[str, ...]:
        missing: list[str] = []
        if self._config.is_mock_mode:
            missing.append("AURORA_ETSY_MODE=live")
        if not self._config.shop_id:
            missing.append("ETSY_SHOP_ID")
        if not self._config.client_id:
            missing.append("ETSY_CLIENT_ID")
        if not self._config.shared_secret:
            missing.append("ETSY_SHARED_SECRET")
        if not self._config.access_token:
            missing.append("ETSY_ACCESS_TOKEN")
        return tuple(missing)

    def _save_result(self, result: EtsyDigitalFileUploadResult) -> None:
        if self._memory is not None:
            self._memory.save_etsy_digital_file_upload_result(result)
