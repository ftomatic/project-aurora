"""Resume a Product Factory job after Etsy listing-image upload failure."""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(SRC_PATH))

from project_aurora.image_generation.commercial_image_exporter import (  # noqa: E402
    COMMERCIAL_IMAGE_COUNT,
    validate_commercial_png,
)
from project_aurora.integrations.etsy.etsy_client import EtsyClient  # noqa: E402
from project_aurora.integrations.etsy.etsy_config import EtsyConfig  # noqa: E402
from project_aurora.integrations.etsy.etsy_digital_file_service import (  # noqa: E402
    EtsyDigitalFileService,
)
from project_aurora.integrations.etsy.etsy_result import (  # noqa: E402
    EtsyImageUploadAttempt,
)
from project_aurora.planning.production_queue_manager import (  # noqa: E402
    ProductionQueueManager,
)
from project_aurora.production.product_factory import REPORT_COLLECTION  # noqa: E402
from project_aurora.production.production_report import ProductionReport  # noqa: E402
from project_aurora.storage.csv_storage import CSVStorage  # noqa: E402
from project_aurora.storage.memory_manager import MemoryManager  # noqa: E402


QUEUE_PATH = PROJECT_ROOT / "data" / "aurora" / "production_queue" / "queue.json"


@dataclass(frozen=True, slots=True)
class ResumeResult:
    """Result of resuming one Product Factory job."""

    job_id: str
    etsy_listing_id: str
    resumed_from_stage: str
    images_already_present: int
    images_uploaded_now: int
    downloads_uploaded: int
    final_status: str
    image_attempts: tuple[EtsyImageUploadAttempt, ...] = field(default_factory=tuple)
    errors: tuple[str, ...] = field(default_factory=tuple)


class ProductFactoryResumeService:
    """Resume an existing draft without recreating prior production stages."""

    def __init__(
        self,
        memory: MemoryManager,
        queue_manager: ProductionQueueManager,
        config: EtsyConfig,
        client: EtsyClient | None = None,
    ) -> None:
        self._memory = memory
        self._queue_manager = queue_manager
        self._config = config
        self._client = client or EtsyClient(config)

    def resume(self, job_id: str) -> ResumeResult:
        """Resume a failed listing-image upload for one job."""
        report_data = self._memory.load_record(REPORT_COLLECTION, job_id)
        listing_id = _existing_draft_id(report_data)
        failed_stage = str(report_data.get("failed_stage") or "")
        if failed_stage != "listing_image_upload":
            raise RuntimeError(
                "Resume only supports jobs failed at listing_image_upload."
            )
        if not listing_id:
            raise RuntimeError("Existing Etsy draft ID is required for resume.")

        final_images_dir = _final_images_dir_from_report(report_data)
        final_files = _valid_final_image_files(final_images_dir)
        existing_images = self._client.list_listing_images(listing_id)
        existing_by_rank = _existing_listing_images_by_rank(existing_images)
        attempts: list[EtsyImageUploadAttempt] = []

        for rank, image_path in enumerate(final_files, start=1):
            if _image_already_present(existing_by_rank.get(rank), image_path, rank):
                continue
            attempts.append(self._upload_one(listing_id, image_path, rank))

        uploaded_now = sum(1 for attempt in attempts if attempt.status == "SUCCESS")
        failed_attempts = tuple(
            attempt for attempt in attempts if attempt.status != "SUCCESS"
        )
        total_images_present = len(existing_by_rank) + uploaded_now
        if failed_attempts or total_images_present != COMMERCIAL_IMAGE_COUNT:
            updated = _updated_report(
                report_data=report_data,
                success=False,
                failed_stage="listing_image_upload",
                images=min(total_images_present, COMMERCIAL_IMAGE_COUNT),
                downloads=int(report_data.get("downloads") or 0),
                metadata_update={
                    "listing_image_upload": {
                        "status": "PARTIAL_FAILURE",
                        "etsy_listing_id": listing_id,
                        "images_already_present": len(existing_by_rank),
                        "images_uploaded_now": uploaded_now,
                        "failed": len(failed_attempts),
                        "attempts": [_attempt_to_dict(attempt) for attempt in attempts],
                    }
                },
                errors=tuple(
                    error
                    for attempt in failed_attempts
                    for error in attempt.errors
                )
                or ("Listing image sync did not reach 4 images.",),
            )
            self._save_report(updated)
            return ResumeResult(
                job_id=job_id,
                etsy_listing_id=listing_id,
                resumed_from_stage=failed_stage,
                images_already_present=len(existing_by_rank),
                images_uploaded_now=uploaded_now,
                downloads_uploaded=0,
                final_status="FAILED",
                image_attempts=tuple(attempts),
                errors=updated.errors,
            )

        digital_result = EtsyDigitalFileService(
            config=self._config,
            memory=self._memory,
            client=self._client,
        ).sync_digital_files(
            listing_id=listing_id,
            final_images_dir=final_images_dir,
        )
        digital_total = _digital_total_present(digital_result)
        success = digital_result.status == "SUCCESS" and digital_total == 4
        final_status = "COMPLETED" if success else "FAILED"
        updated_report = _updated_report(
            report_data=report_data,
            success=success,
            failed_stage=None if success else "customer_download_upload",
            images=COMMERCIAL_IMAGE_COUNT,
            downloads=digital_total,
            metadata_update={
                "listing_image_upload": {
                    "status": "SUCCESS",
                    "etsy_listing_id": listing_id,
                    "images_already_present": len(existing_by_rank),
                    "images_uploaded_now": uploaded_now,
                    "total_present": COMMERCIAL_IMAGE_COUNT,
                    "attempts": [_attempt_to_dict(attempt) for attempt in attempts],
                },
                "customer_download_upload": digital_result,
            },
            errors=tuple(digital_result.errors) if not success else (),
        )
        self._save_report(updated_report)
        if success:
            self._queue_manager.mark_completed(job_id)
        else:
            self._queue_manager.mark_failed(job_id)

        return ResumeResult(
            job_id=job_id,
            etsy_listing_id=listing_id,
            resumed_from_stage=failed_stage,
            images_already_present=len(existing_by_rank),
            images_uploaded_now=uploaded_now,
            downloads_uploaded=int(digital_result.files_uploaded),
            final_status=final_status,
            image_attempts=tuple(attempts),
            errors=updated_report.errors,
        )

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

    def _save_report(self, report: ProductionReport) -> None:
        self._memory.save_record(REPORT_COLLECTION, "latest", report.to_dict())
        self._memory.save_record(REPORT_COLLECTION, report.job_id, report.to_dict())


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse resume CLI arguments."""
    parser = argparse.ArgumentParser(description="Resume one Product Factory job.")
    parser.add_argument("--job-id", required=True, help="Production queue job id.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    """Resume a failed Product Factory job safely."""
    args = parse_args(argv)
    memory = MemoryManager(storage=CSVStorage(base_path=PROJECT_ROOT / "data" / "aurora"))
    queue_manager = ProductionQueueManager(queue_path=QUEUE_PATH)
    config = EtsyConfig.from_environment(PROJECT_ROOT / "config" / "etsy.yaml")
    try:
        result = ProductFactoryResumeService(
            memory=memory,
            queue_manager=queue_manager,
            config=config,
        ).resume(args.job_id)
    except RuntimeError as error:
        print_resume_error(args.job_id, error)
        raise SystemExit(1) from error
    print_resume_result(result)
    if result.final_status != "COMPLETED":
        raise SystemExit(1)


def print_resume_result(result: ResumeResult) -> None:
    """Print the resume result."""
    print("PRODUCT FACTORY RESUME")
    print("")
    print("Existing Draft ID")
    print(result.etsy_listing_id)
    print("")
    print("Resuming From Stage")
    print(result.resumed_from_stage)
    print("")
    print("Images Already Present")
    print(result.images_already_present)
    print("")
    print("Images Uploaded Now")
    print(result.images_uploaded_now)
    print("")
    print("Downloads Uploaded")
    print(result.downloads_uploaded)
    print("")
    print("Final Status")
    print(result.final_status)
    if result.errors:
        print("")
        print("Errors")
        for error in result.errors:
            print(error)


def print_resume_error(job_id: str, error: RuntimeError) -> None:
    """Print a concise recovery summary for resume failures."""
    print("PRODUCT FACTORY RESUME")
    print("")
    print("Job ID")
    print(job_id)
    print("")
    print("Final Status")
    print("FAILED")
    print("")
    print("Recovery Summary")
    print(str(error))


def _existing_draft_id(report_data: dict[str, Any]) -> str | None:
    draft_id = report_data.get("draft_id")
    if isinstance(draft_id, str) and draft_id.strip():
        return draft_id.strip()
    etsy_draft = report_data.get("metadata", {}).get("etsy_draft")
    if isinstance(etsy_draft, dict):
        listing_id = etsy_draft.get("etsy_listing_id")
        if isinstance(listing_id, str) and listing_id.strip():
            return listing_id.strip()
    return None


def _final_images_dir_from_report(report_data: dict[str, Any]) -> Path:
    job_paths = report_data.get("job_paths")
    if not isinstance(job_paths, dict):
        raise RuntimeError("ProductionReport does not include job_paths.")
    value = job_paths.get("final_product_images_dir")
    if not isinstance(value, str) or not value.strip():
        raise RuntimeError("ProductionReport does not include final images path.")
    return Path(value)


def _valid_final_image_files(final_images_dir: Path) -> tuple[Path, ...]:
    if final_images_dir.name != "final_product_images":
        raise RuntimeError("Resume must use job final_product_images directory.")
    files = tuple(sorted(final_images_dir.glob("*.png"), key=lambda path: path.name))
    if len(files) != COMMERCIAL_IMAGE_COUNT:
        raise RuntimeError(
            f"Expected exactly {COMMERCIAL_IMAGE_COUNT} final PNG files, "
            f"found {len(files)}."
        )
    errors = tuple(
        f"{path.name}: {error}"
        for path in files
        for error in validate_commercial_png(path)
    )
    if errors:
        raise RuntimeError("Invalid final image files: " + "; ".join(errors))
    return files


def _existing_listing_images_by_rank(
    records: tuple[dict[str, Any], ...],
) -> dict[int, dict[str, Any]]:
    by_rank: dict[int, dict[str, Any]] = {}
    for record in records:
        rank = _rank_from_record(record)
        if rank is not None:
            by_rank[rank] = record
    return by_rank


def _image_already_present(
    record: dict[str, Any] | None,
    image_path: Path,
    rank: int,
) -> bool:
    if record is None:
        return False
    filename = _filename_from_record(record)
    if filename is None:
        return _rank_from_record(record) == rank
    return filename == image_path.name


def _rank_from_record(record: dict[str, Any]) -> int | None:
    for key in ("rank", "image_rank", "listing_image_rank"):
        value = record.get(key)
        if value is not None:
            try:
                return int(value)
            except (TypeError, ValueError):
                return None
    return None


def _filename_from_record(record: dict[str, Any]) -> str | None:
    for key in ("filename", "file_name", "name"):
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            return Path(value).name
    return None


def _digital_total_present(result: Any) -> int:
    total = result.metadata.get("total_present")
    if isinstance(total, int):
        return total
    already_present = result.metadata.get("already_present")
    if isinstance(already_present, list):
        return len(already_present) + int(result.files_uploaded)
    return int(result.files_uploaded)


def _updated_report(
    report_data: dict[str, Any],
    success: bool,
    failed_stage: str | None,
    images: int,
    downloads: int,
    metadata_update: dict[str, Any],
    errors: tuple[str, ...],
) -> ProductionReport:
    metadata = dict(report_data.get("metadata") or {})
    metadata.update(
        {
            key: _record_value(value)
            for key, value in metadata_update.items()
        }
    )
    return ProductionReport(
        job_id=str(report_data["job_id"]),
        product=str(report_data["product"]),
        style=str(report_data["style"]),
        draft_id=_existing_draft_id(report_data),
        images=images,
        downloads=downloads,
        time=float(report_data.get("time") or 0),
        success=success,
        failed_stage=failed_stage,
        warnings=tuple(str(item) for item in report_data.get("warnings", ())),
        errors=errors,
        job_paths=dict(report_data.get("job_paths") or {}),
        metadata=metadata,
        created_at=datetime.now(),
    )


def _record_value(value: Any) -> Any:
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        return to_dict()
    if hasattr(value, "__dataclass_fields__"):
        return {
            key: _record_value(getattr(value, key))
            for key in value.__dataclass_fields__
        }
    if isinstance(value, tuple):
        return [_record_value(item) for item in value]
    if isinstance(value, list):
        return [_record_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _record_value(item) for key, item in value.items()}
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _attempt_to_dict(attempt: EtsyImageUploadAttempt) -> dict[str, Any]:
    return {
        "image_path": attempt.image_path,
        "rank": attempt.rank,
        "status": attempt.status,
        "etsy_image_id": attempt.etsy_image_id,
        "errors": list(attempt.errors),
        "warnings": list(attempt.warnings),
        "metadata": attempt.metadata,
    }


if __name__ == "__main__":
    main()
