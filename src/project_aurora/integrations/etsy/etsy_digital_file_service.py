"""Upload customer digital PNG files to Etsy draft listings."""

from __future__ import annotations

from pathlib import Path

from project_aurora.image_generation.commercial_image_exporter import (
    DIGITAL_PAPER_IMAGE_SIZE,
    DIGITAL_PAPER_MIN_SHARPNESS,
    WALL_ART_MIN_SHARPNESS,
    WALL_ART_RATIOS,
    validate_commercial_jpg,
    validate_commercial_png,
)
from project_aurora.integrations.etsy.etsy_client import EtsyClient
from project_aurora.integrations.etsy.etsy_config import EtsyConfig
from project_aurora.integrations.etsy.etsy_result import (
    EtsyDigitalFileUploadAttempt,
    EtsyDigitalFileUploadResult,
)
from project_aurora.integrations.etsy.etsy_upload_manager import EtsyUploadManager
from project_aurora.storage.memory_manager import MemoryManager


MAX_DIGITAL_FILE_SIZE_BYTES = 20 * 1024 * 1024
REQUIRED_DIGITAL_FILE_COUNT = 4
ETSY_MAX_DIGITAL_FILES = 5


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
        manager = EtsyUploadManager(memory=self._memory)
        for rank, file_path in enumerate(files, start=1):
            attempts.append(self._upload_one(str(listing_id), file_path, rank, manager))
            manager.delay_between_files()

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

    def retry_failed_digital_files(
        self,
        listing_id: str | None,
        final_images_dir: Path,
        previous_result: EtsyDigitalFileUploadResult,
    ) -> EtsyDigitalFileUploadResult:
        """Retry only failed or missing digital files for an existing draft."""
        files = self._find_pngs(final_images_dir)
        file_by_name = {file_path.name: file_path for file_path in files}
        previous_uploaded = self._successful_attempts_by_filename(previous_result)
        previous_failed = self._failed_attempt_records(previous_result)
        errors = list(self._preflight_errors(listing_id, final_images_dir, files))
        if errors:
            retry_names = tuple(
                filename
                for filename in file_by_name
                if filename not in previous_uploaded
            )
            result = EtsyDigitalFileUploadResult(
                status="CONFIGURATION_REQUIRED",
                etsy_listing_id=listing_id,
                digital_file_path=str(final_images_dir),
                uploaded=False,
                files_found=len(files),
                files_uploaded=0,
                failed=0,
                errors=tuple(errors),
                metadata={
                    "api_called": False,
                    "already_uploaded": [
                        {"filename": filename, "etsy_file_id": file_id}
                        for filename, file_id in sorted(previous_uploaded.items())
                    ],
                    "retrying": list(retry_names),
                    "previous_failed": previous_failed,
                },
            )
            return result

        etsy_uploaded, query_warning = self._uploaded_files_from_listing(str(listing_id))
        already_uploaded = {**previous_uploaded, **etsy_uploaded}
        retry_names = tuple(
            filename
            for filename in file_by_name
            if filename not in already_uploaded
        )

        attempts: list[EtsyDigitalFileUploadAttempt] = []
        manager = EtsyUploadManager(memory=self._memory)
        for filename in retry_names:
            file_path = file_by_name[filename]
            attempts.append(
                self._upload_one(
                    listing_id=str(listing_id),
                    file_path=file_path,
                    rank=self._rank_for_filename(filename, files),
                    manager=manager,
                )
            )
            manager.delay_between_files()

        newly_uploaded = {
            attempt.filename: attempt.etsy_file_id
            for attempt in attempts
            if attempt.status == "SUCCESS"
        }
        all_uploaded = {**already_uploaded, **newly_uploaded}
        failed_attempts = tuple(
            attempt for attempt in attempts if attempt.status != "SUCCESS"
        )
        uploaded_complete = (
            len(all_uploaded) == self._required_count and not failed_attempts
        )
        warnings = (query_warning,) if query_warning else ()
        result = EtsyDigitalFileUploadResult(
            status="SUCCESS" if uploaded_complete else "PARTIAL_FAILURE",
            etsy_listing_id=listing_id,
            digital_file_path=str(final_images_dir),
            uploaded=uploaded_complete,
            files_found=len(files),
            files_uploaded=len(newly_uploaded),
            failed=len(failed_attempts),
            attempts=tuple(attempts),
            warnings=warnings,
            metadata={
                "api_called": bool(attempts),
                "already_uploaded": [
                    {"filename": filename, "etsy_file_id": file_id}
                    for filename, file_id in sorted(already_uploaded.items())
                ],
                "retrying": list(retry_names),
                "uploaded": [
                    {
                        "filename": attempt.filename,
                        "etsy_file_id": attempt.etsy_file_id,
                    }
                    for attempt in attempts
                    if attempt.status == "SUCCESS"
                ],
                "previous_failed": previous_failed,
            },
        )
        self._save_result(result)
        return result

    def sync_digital_files(
        self,
        listing_id: str | None,
        final_images_dir: Path,
    ) -> EtsyDigitalFileUploadResult:
        """Idempotently sync expected digital PNG files to an Etsy draft."""
        files = self._find_pngs(final_images_dir)
        file_by_name = {file_path.name: file_path for file_path in files}
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

        try:
            existing_records = self._client.list_listing_digital_files(
                str(listing_id)
            )
        except RuntimeError as error:
            result = EtsyDigitalFileUploadResult(
                status="FAILED",
                etsy_listing_id=listing_id,
                digital_file_path=str(final_images_dir),
                uploaded=False,
                files_found=len(files),
                files_uploaded=0,
                failed=0,
                errors=(f"Could not query Etsy digital files: {error}",),
                metadata={"api_called": True},
            )
            self._save_result(result)
            return result

        existing = self._records_by_filename(existing_records)
        missing_names = tuple(
            filename for filename in file_by_name if filename not in existing
        )
        total_after_sync = len(existing) + len(missing_names)
        if total_after_sync > ETSY_MAX_DIGITAL_FILES:
            result = EtsyDigitalFileUploadResult(
                status="FAILED",
                etsy_listing_id=listing_id,
                digital_file_path=str(final_images_dir),
                uploaded=False,
                files_found=len(files),
                files_uploaded=0,
                failed=0,
                errors=(
                    "Etsy allows a maximum of 5 digital files; "
                    f"sync would result in {total_after_sync}.",
                ),
                metadata={
                    "api_called": True,
                    "already_present": self._existing_file_records(existing),
                    "missing": list(missing_names),
                },
            )
            self._save_result(result)
            return result

        attempts: list[EtsyDigitalFileUploadAttempt] = []
        manager = EtsyUploadManager(memory=self._memory)
        for filename in missing_names:
            file_path = file_by_name[filename]
            attempts.append(
                self._upload_one(
                    listing_id=str(listing_id),
                    file_path=file_path,
                    rank=self._rank_for_filename(filename, files),
                    manager=manager,
                )
            )
            manager.delay_between_files()

        uploaded_now = {
            attempt.filename: attempt.etsy_file_id
            for attempt in attempts
            if attempt.status == "SUCCESS"
        }
        failed_attempts = tuple(
            attempt for attempt in attempts if attempt.status != "SUCCESS"
        )
        total_present = len(existing) + len(uploaded_now)
        uploaded_complete = (
            total_present == self._required_count and not failed_attempts
        )
        result = EtsyDigitalFileUploadResult(
            status="SUCCESS" if uploaded_complete else "PARTIAL_FAILURE",
            etsy_listing_id=listing_id,
            digital_file_path=str(final_images_dir),
            uploaded=uploaded_complete,
            files_found=len(files),
            files_uploaded=len(uploaded_now),
            failed=len(failed_attempts),
            attempts=tuple(attempts),
            metadata={
                "api_called": bool(attempts),
                "already_present": self._existing_file_records(existing),
                "missing": list(missing_names),
                "uploaded": [
                    {
                        "filename": attempt.filename,
                        "etsy_file_id": attempt.etsy_file_id,
                    }
                    for attempt in attempts
                    if attempt.status == "SUCCESS"
                ],
                "total_present": total_present,
            },
        )
        self._save_result(result)
        return result

    def sync_digital_package(
        self,
        listing_id: str | None,
        package_path: Path,
    ) -> EtsyDigitalFileUploadResult:
        """Idempotently sync one ZIP customer download package to an Etsy draft."""
        errors = list(self._package_preflight_errors(listing_id, package_path))
        if errors:
            result = EtsyDigitalFileUploadResult(
                status="CONFIGURATION_REQUIRED",
                etsy_listing_id=listing_id,
                digital_file_path=str(package_path),
                uploaded=False,
                files_found=1 if package_path.exists() else 0,
                files_uploaded=0,
                failed=0,
                errors=tuple(errors),
                metadata={"api_called": False},
            )
            self._save_result(result)
            return result

        try:
            existing_records = self._client.list_listing_digital_files(str(listing_id))
        except RuntimeError as error:
            result = EtsyDigitalFileUploadResult(
                status="FAILED",
                etsy_listing_id=listing_id,
                digital_file_path=str(package_path),
                uploaded=False,
                files_found=1,
                files_uploaded=0,
                failed=0,
                errors=(f"Could not query Etsy digital files: {error}",),
                metadata={"api_called": True},
            )
            self._save_result(result)
            return result

        existing = self._records_by_filename(existing_records)
        if package_path.name in existing:
            file_id = (
                existing[package_path.name].get("listing_file_id")
                or existing[package_path.name].get("file_id")
                or existing[package_path.name].get("digital_file_id")
            )
            result = EtsyDigitalFileUploadResult(
                status="SUCCESS",
                etsy_listing_id=listing_id,
                digital_file_path=str(package_path),
                uploaded=True,
                files_found=1,
                files_uploaded=0,
                failed=0,
                metadata={
                    "api_called": True,
                    "already_present": [
                        {
                            "filename": package_path.name,
                            "etsy_file_id": str(file_id) if file_id is not None else None,
                        }
                    ],
                    "total_present": 1,
                },
            )
            self._save_result(result)
            return result
        if len(existing) >= ETSY_MAX_DIGITAL_FILES:
            result = EtsyDigitalFileUploadResult(
                status="FAILED",
                etsy_listing_id=listing_id,
                digital_file_path=str(package_path),
                uploaded=False,
                files_found=1,
                files_uploaded=0,
                failed=0,
                errors=("Etsy allows a maximum of 5 digital files; no slot is available for the ZIP package.",),
                metadata={
                    "api_called": True,
                    "already_present": self._existing_file_records(existing),
                },
            )
            self._save_result(result)
            return result

        manager = EtsyUploadManager(memory=self._memory)
        attempt = self._upload_one(
            listing_id=str(listing_id),
            file_path=package_path,
            rank=1,
            manager=manager,
        )
        success = attempt.status == "SUCCESS"
        result = EtsyDigitalFileUploadResult(
            status="SUCCESS" if success else "PARTIAL_FAILURE",
            etsy_listing_id=listing_id,
            digital_file_path=str(package_path),
            uploaded=success,
            files_found=1,
            files_uploaded=1 if success else 0,
            failed=0 if success else 1,
            attempts=(attempt,),
            errors=attempt.errors if not success else (),
            metadata={
                "api_called": True,
                "uploaded": [
                    {
                        "filename": attempt.filename,
                        "etsy_file_id": attempt.etsy_file_id,
                    }
                ]
                if success
                else [],
                "total_present": 1 if success else len(existing),
            },
        )
        self._save_result(result)
        return result

    def _upload_one(
        self,
        listing_id: str,
        file_path: Path,
        rank: int,
        manager: EtsyUploadManager | None = None,
    ) -> EtsyDigitalFileUploadAttempt:
        resolved_manager = manager or EtsyUploadManager(memory=self._memory)
        checkpoint = resolved_manager.upload_one(
            listing_id=listing_id,
            job_id=file_path.parent.parent.name,
            upload_type="digital_file",
            file_path=file_path,
            rank=rank,
            uploader=lambda: self._client.upload_listing_digital_file(
                listing_id=listing_id,
                file_path=file_path,
                rank=rank,
            ),
        )
        if checkpoint.status != "SUCCESS":
            return EtsyDigitalFileUploadAttempt(
                filename=file_path.name,
                rank=rank,
                status="FAILED",
                errors=(checkpoint.error,),
            )
        return EtsyDigitalFileUploadAttempt(
            filename=file_path.name,
            rank=rank,
            status="SUCCESS",
            etsy_file_id=checkpoint.etsy_resource_id,
            metadata={"checkpoint": checkpoint.to_dict()},
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
                f"Exactly {self._required_count} final commercial files are required, "
                f"found {len(files)}."
            )
        for file_path in files:
            if file_path.stat().st_size >= MAX_DIGITAL_FILE_SIZE_BYTES:
                errors.append(
                    f"{file_path.name} exceeds Etsy's 20 MB digital file limit."
                )
            errors.extend(_validate_final_file(file_path))
        return tuple(errors)

    def _package_preflight_errors(
        self,
        listing_id: str | None,
        package_path: Path,
    ) -> tuple[str, ...]:
        errors: list[str] = []
        missing = self._missing_config()
        if missing:
            errors.append(
                "Missing Etsy configuration: " + ", ".join(missing) + "."
            )
        if not listing_id:
            errors.append("etsy_listing_id is required.")
        if package_path.parent.name != "final_product_images":
            errors.append("Digital package upload must use final_product_images only.")
        if not package_path.exists() or not package_path.is_file():
            errors.append(f"ZIP package does not exist: {package_path}.")
        elif package_path.suffix.casefold() != ".zip":
            errors.append(f"Digital package must be a ZIP file: {package_path.name}.")
        elif package_path.stat().st_size <= 0:
            errors.append(f"ZIP package is empty: {package_path.name}.")
        elif package_path.stat().st_size >= MAX_DIGITAL_FILE_SIZE_BYTES:
            errors.append(f"{package_path.name} exceeds Etsy's 20 MB digital file limit.")
        return tuple(errors)

    @staticmethod
    def _find_pngs(final_images_dir: Path) -> tuple[Path, ...]:
        if not final_images_dir.exists():
            return ()
        return tuple(
            path
            for path in sorted(final_images_dir.glob("*"), key=lambda path: path.name)
            if path.is_file()
            and path.suffix.casefold() in {".png", ".jpg", ".jpeg"}
            and "preview" not in path.stem.casefold()
        )

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

    @staticmethod
    def _successful_attempts_by_filename(
        result: EtsyDigitalFileUploadResult,
    ) -> dict[str, str | None]:
        return {
            attempt.filename: attempt.etsy_file_id
            for attempt in result.attempts
            if attempt.status == "SUCCESS"
        }

    @staticmethod
    def _failed_attempt_records(
        result: EtsyDigitalFileUploadResult,
    ) -> list[dict[str, object]]:
        return [
            {
                "filename": attempt.filename,
                "rank": attempt.rank,
                "errors": list(attempt.errors),
            }
            for attempt in result.attempts
            if attempt.status != "SUCCESS"
        ]

    def _uploaded_files_from_listing(
        self,
        listing_id: str,
    ) -> tuple[dict[str, str | None], str | None]:
        try:
            records = self._client.list_listing_digital_files(listing_id)
        except (AttributeError, RuntimeError) as error:
            return {}, (
                "Could not query Etsy listing digital files; "
                f"using saved upload history only. Reason: {error}"
            )

        uploaded: dict[str, str | None] = {}
        for record in records:
            filename = self._filename_from_record(record)
            if not filename:
                continue
            file_id = (
                record.get("listing_file_id")
                or record.get("file_id")
                or record.get("digital_file_id")
            )
            uploaded[filename] = str(file_id) if file_id is not None else None
        return uploaded, None

    def _records_by_filename(
        self,
        records: tuple[dict[str, object], ...],
    ) -> dict[str, dict[str, object]]:
        uploaded: dict[str, dict[str, object]] = {}
        for record in records:
            filename = self._filename_from_record(record)
            if filename:
                uploaded[filename] = dict(record)
        return uploaded

    def _existing_file_records(
        self,
        records_by_filename: dict[str, dict[str, object]],
    ) -> list[dict[str, str | None]]:
        existing: list[dict[str, str | None]] = []
        for filename, record in sorted(records_by_filename.items()):
            file_id = (
                record.get("listing_file_id")
                or record.get("file_id")
                or record.get("digital_file_id")
            )
            existing.append(
                {
                    "filename": filename,
                    "etsy_file_id": str(file_id) if file_id is not None else None,
                }
            )
        return existing

    @staticmethod
    def _filename_from_record(record: dict[str, object]) -> str | None:
        for key in ("filename", "name", "file_name"):
            value = record.get(key)
            if isinstance(value, str) and value:
                return Path(value).name
        return None

    @staticmethod
    def _rank_for_filename(filename: str, files: tuple[Path, ...]) -> int:
        for index, file_path in enumerate(files, start=1):
            if file_path.name == filename:
                return index
        raise ValueError(f"Unknown digital file: {filename}")


def _validate_final_file(file_path: Path) -> tuple[str, ...]:
    if file_path.suffix.casefold() == ".png":
        return tuple(
            f"{file_path.name}: {error}" for error in validate_commercial_png(file_path)
        )
    if file_path.suffix.casefold() in {".jpg", ".jpeg"}:
        if file_path.stem.casefold().startswith("digital_paper_"):
            return tuple(
                f"{file_path.name}: {error}"
                for error in validate_commercial_jpg(
                    file_path,
                    DIGITAL_PAPER_IMAGE_SIZE,
                    minimum_sharpness=DIGITAL_PAPER_MIN_SHARPNESS,
                )
            )
        expected_size = dict(WALL_ART_RATIOS).get(_ratio_label_from_name(file_path))
        if expected_size is None:
            return (f"{file_path.name}: Missing required wall art ratio label.",)
        return tuple(
            f"{file_path.name}: {error}"
            for error in validate_commercial_jpg(
                file_path,
                expected_size,
                minimum_sharpness=WALL_ART_MIN_SHARPNESS,
            )
        )
    return (f"{file_path.name}: Unsupported final file format.",)


def _ratio_label_from_name(path: Path) -> str:
    stem = path.stem.casefold().replace("_", "x").replace("-", "x")
    for label, _size in WALL_ART_RATIOS:
        if label in stem:
            return label
    return ""
