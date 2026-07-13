"""Upload customer digital download files to Etsy draft listings."""

from __future__ import annotations

from pathlib import Path

from project_aurora.integrations.etsy.etsy_client import EtsyClient
from project_aurora.integrations.etsy.etsy_config import EtsyConfig
from project_aurora.integrations.etsy.etsy_result import EtsyDigitalFileUploadResult
from project_aurora.storage.memory_manager import MemoryManager


class EtsyDigitalFileService:
    """Validate and upload a customer ZIP to an Etsy draft listing."""

    def __init__(
        self,
        config: EtsyConfig,
        memory: MemoryManager | None = None,
        client: EtsyClient | None = None,
    ) -> None:
        self._config = config
        self._memory = memory
        self._client = client or EtsyClient(config)

    def upload_digital_file(
        self,
        listing_id: str | None,
        file_path: Path,
    ) -> EtsyDigitalFileUploadResult:
        """Upload one customer ZIP file to the existing draft listing."""
        errors: list[str] = []
        missing = self._missing_config()
        if missing:
            errors.append(
                "Missing Etsy configuration: " + ", ".join(missing) + "."
            )
        if not listing_id:
            errors.append("etsy_listing_id is required.")
        if not file_path.exists():
            errors.append(f"Digital file does not exist: {file_path}.")
        elif file_path.stat().st_size <= 0:
            errors.append(f"Digital file is empty: {file_path}.")
        if errors:
            result = EtsyDigitalFileUploadResult(
                status="CONFIGURATION_REQUIRED",
                etsy_listing_id=listing_id,
                digital_file_path=str(file_path),
                uploaded=False,
                errors=tuple(errors),
                metadata={"api_called": False, "missing": missing},
            )
            self._save_result(result)
            return result

        try:
            response = self._client.upload_listing_digital_file(
                listing_id=str(listing_id),
                file_path=file_path,
            )
        except RuntimeError as error:
            result = EtsyDigitalFileUploadResult(
                status="FAILED",
                etsy_listing_id=listing_id,
                digital_file_path=str(file_path),
                uploaded=False,
                errors=(str(error),),
                metadata={"api_called": True},
            )
            self._save_result(result)
            return result

        result = EtsyDigitalFileUploadResult(
            status="SUCCESS",
            etsy_listing_id=listing_id,
            digital_file_path=str(file_path),
            uploaded=True,
            metadata={"api_called": True, "response": response},
        )
        self._save_result(result)
        return result

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
