"""Resume failed Aurora Product Factory jobs safely."""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from time import sleep
from types import SimpleNamespace
from typing import Callable

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(SRC_PATH))

from project_aurora.integrations.etsy.etsy_config import EtsyConfig  # noqa: E402
from project_aurora.image_generation.provider_registry import (  # noqa: E402
    ImageProviderConfig,
)
from project_aurora.planning.production_queue_manager import (  # noqa: E402
    FAILED,
    ProductionJob,
    ProductionQueueManager,
)
from project_aurora.production.product_factory import (  # noqa: E402
    DefaultProductFactoryStageRunner,
    ProductFactory,
)
from project_aurora.production.production_report import ProductionReport  # noqa: E402
from project_aurora.storage.csv_storage import CSVStorage  # noqa: E402
from project_aurora.storage.memory_manager import MemoryManager  # noqa: E402
from scripts.run_batch_factory import (  # noqa: E402
    DAILY_FACTORY_CONFIG_PATH,
    REAL_QUEUE_PATH,
    BatchRuntimeConfig,
    load_batch_runtime_config,
)
from scripts.run_product_factory import print_etsy_config_diagnostics  # noqa: E402
from scripts.resume_product_factory_job import ProductFactoryResumeService  # noqa: E402


@dataclass(frozen=True, slots=True)
class FailedBatchRecoveryReport:
    """Summary of one failed-batch recovery run."""

    jobs_found: int
    jobs_verified_complete: int
    jobs_still_incomplete: int
    drafts_repaired: int
    existing_drafts_reused: int
    new_drafts_created: int
    images_present_before: int
    missing_images_detected: int
    images_uploaded_during_repair: int
    images_present_after: int
    digital_files_present_after: int
    missing_digital_files_uploaded: int
    verified_complete: int
    still_incomplete: int
    status: str
    reports: tuple[ProductionReport, ...] = field(default_factory=tuple)
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, object]:
        """Return JSON-safe recovery report data."""
        return {
            "jobs_found": self.jobs_found,
            "jobs_verified_complete": self.jobs_verified_complete,
            "jobs_still_incomplete": self.jobs_still_incomplete,
            "drafts_repaired": self.drafts_repaired,
            "existing_drafts_reused": self.existing_drafts_reused,
            "new_drafts_created": self.new_drafts_created,
            "images_present_before": self.images_present_before,
            "missing_images_detected": self.missing_images_detected,
            "images_uploaded_during_repair": self.images_uploaded_during_repair,
            "images_present_after": self.images_present_after,
            "digital_files_present_after": self.digital_files_present_after,
            "missing_digital_files_uploaded": self.missing_digital_files_uploaded,
            "verified_complete": self.verified_complete,
            "still_incomplete": self.still_incomplete,
            "status": self.status,
            "reports": [report.to_dict() for report in self.reports],
            "created_at": self.created_at.isoformat(),
        }


class ResumeProductFactoryStageRunner(DefaultProductFactoryStageRunner):
    """Recovery runner that never duplicates an already-created draft."""

    def __init__(self, *args: object, existing_draft_id: str | None = None, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self._existing_draft_id = existing_draft_id

    def create_etsy_draft(self, job: ProductionJob, seo_package: object) -> object:
        """Reuse an existing draft ID when one was already saved."""
        if self._existing_draft_id:
            return SimpleNamespace(
                status="DRAFT_CREATED",
                etsy_listing_id=self._existing_draft_id,
                warnings=("Reused existing Etsy draft during failed batch recovery.",),
                errors=(),
            )
        return super().create_etsy_draft(job, seo_package)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse recovery CLI arguments."""
    parser = argparse.ArgumentParser(description="Resume failed Aurora batch jobs.")
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--live", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    """Run failed batch recovery."""
    args = parse_args(argv)
    if not args.live:
        raise SystemExit("Use --live to resume failed production jobs.")
    report = run_failed_batch_recovery(limit=args.limit)
    print_recovery_report(report)


def run_failed_batch_recovery(
    limit: int,
    queue_path: Path = REAL_QUEUE_PATH,
    memory: MemoryManager | None = None,
    runtime_config: BatchRuntimeConfig | None = None,
    sleeper: Callable[[float], None] = sleep,
) -> FailedBatchRecoveryReport:
    """Resume up to limit failed jobs sequentially."""
    if limit <= 0:
        raise ValueError("limit must be greater than zero.")
    resolved_memory = memory or MemoryManager(
        storage=CSVStorage(base_path=PROJECT_ROOT / "data" / "aurora")
    )
    config = runtime_config or load_batch_runtime_config(DAILY_FACTORY_CONFIG_PATH)
    queue_manager = ProductionQueueManager(queue_path=queue_path)
    failed_jobs = tuple(job for job in queue_manager.list_jobs() if job.status == FAILED)[:limit]
    etsy_config = EtsyConfig.from_environment(PROJECT_ROOT / "config" / "etsy.yaml")
    image_config = _image_config_for_recovery(config)
    print_etsy_config_diagnostics(etsy_config)

    reports: list[ProductionReport] = []
    before_reports: dict[str, dict[str, object]] = {}
    previous_generated_images = False
    for job in failed_jobs:
        if previous_generated_images and config.openai_image_delay_seconds > 0:
            sleeper(config.openai_image_delay_seconds)
        before_reports[job.id] = _load_job_report(resolved_memory, job.id)
        service = ProductFactoryResumeService(
            memory=resolved_memory,
            queue_manager=queue_manager,
            config=etsy_config,
        )
        service.resume(job.id)
        report = _report_from_memory(resolved_memory, job.id)
        reports.append(report)
        previous_generated_images = _generated_images_now(report)

    verified = tuple(report for report in reports if _report_verified_complete(report))
    incomplete = tuple(report for report in reports if not _report_verified_complete(report))
    recovery = FailedBatchRecoveryReport(
        jobs_found=len(failed_jobs),
        jobs_verified_complete=len(verified),
        jobs_still_incomplete=len(incomplete),
        drafts_repaired=sum(1 for report in reports if _draft_id_from_saved_report(before_reports.get(report.job_id, {}))),
        existing_drafts_reused=sum(1 for report in reports if _draft_id_from_saved_report(before_reports.get(report.job_id, {}))),
        new_drafts_created=sum(
            1
            for report in reports
            if report.draft_id and not _draft_id_from_saved_report(before_reports.get(report.job_id, {}))
        ),
        images_present_before=sum(_listing_images_before(report) for report in reports),
        missing_images_detected=sum(max(0, 4 - _listing_images_before(report)) for report in reports),
        images_uploaded_during_repair=sum(_listing_images_uploaded_now(report) for report in reports),
        images_present_after=sum(_listing_images_after(report) for report in reports),
        digital_files_present_after=sum(_digital_files_after(report) for report in reports),
        missing_digital_files_uploaded=sum(_digital_files_uploaded_now(report) for report in reports),
        verified_complete=len(verified),
        still_incomplete=len(incomplete),
        status="SUCCESS" if reports and not incomplete else "PARTIAL_FAILURE",
        reports=tuple(reports),
    )
    key = f"failed_batch_recovery_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    resolved_memory.save_record("production_reports", "latest_failed_batch_recovery", recovery.to_dict())
    resolved_memory.save_record("production_reports", key, recovery.to_dict())
    return recovery


def _image_config_for_recovery(config: BatchRuntimeConfig) -> ImageProviderConfig:
    image_config = ImageProviderConfig.from_file(PROJECT_ROOT / "config" / "openai.yaml")
    return ImageProviderConfig(
        provider=image_config.provider,
        model=image_config.model,
        size=image_config.size,
        quality=image_config.quality,
        background=image_config.background,
        output_format=image_config.output_format,
        number_of_images=image_config.number_of_images,
        prompt_version=image_config.prompt_version,
        rate_limit_max_retries=config.openai_rate_limit_max_retries,
        rate_limit_safety_seconds=config.openai_rate_limit_safety_seconds,
    )


def _load_job_report(memory: MemoryManager, job_id: str) -> dict[str, object]:
    try:
        return memory.load_record("production_reports", job_id)
    except FileNotFoundError:
        return {}


def _report_from_memory(memory: MemoryManager, job_id: str) -> ProductionReport:
    data = memory.load_record("production_reports", job_id)
    return ProductionReport(
        job_id=str(data["job_id"]),
        product=str(data["product"]),
        style=str(data["style"]),
        draft_id=str(data["draft_id"]) if data.get("draft_id") else None,
        images=int(data.get("images") or 0),
        downloads=int(data.get("downloads") or 0),
        time=float(data.get("time") or 0),
        success=bool(data.get("success")),
        failed_stage=(
            str(data["failed_stage"]) if data.get("failed_stage") is not None else None
        ),
        warnings=tuple(str(item) for item in data.get("warnings", ())),
        errors=tuple(str(item) for item in data.get("errors", ())),
        job_paths=dict(data.get("job_paths") or {}),
        metadata=dict(data.get("metadata") or {}),
    )


def _draft_id_from_saved_report(report: dict[str, object]) -> str | None:
    draft_id = report.get("draft_id")
    if isinstance(draft_id, str) and draft_id.strip():
        return draft_id.strip()
    metadata = report.get("metadata")
    if isinstance(metadata, dict):
        etsy_draft = metadata.get("etsy_draft")
        if isinstance(etsy_draft, dict):
            value = etsy_draft.get("etsy_listing_id")
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


def _generated_images_now(report: ProductionReport) -> bool:
    return _image_count(report, reused=False) > 0


def _image_count(report: ProductionReport, reused: bool) -> int:
    image_generation = report.metadata.get("image_generation")
    if not isinstance(image_generation, dict):
        return 0
    if str(image_generation.get("status", "")).upper() != "SUCCESS":
        return 0
    warnings = image_generation.get("warnings", ())
    reused_report = isinstance(warnings, list | tuple) and any(
        "reused existing" in str(warning).casefold() for warning in warnings
    )
    if reused_report != reused:
        return 0
    return 4


def _report_verified_complete(report: ProductionReport) -> bool:
    return (
        report.success
        and _listing_images_after(report) == 4
        and _digital_files_after(report) == 4
    )


def _listing_upload_metadata(report: ProductionReport) -> dict[str, object]:
    value = report.metadata.get("listing_image_upload")
    return value if isinstance(value, dict) else {}


def _digital_upload_metadata(report: ProductionReport) -> dict[str, object]:
    value = report.metadata.get("customer_download_upload")
    return value if isinstance(value, dict) else {}


def _listing_images_before(report: ProductionReport) -> int:
    value = _listing_upload_metadata(report).get("images_already_present")
    return int(value) if isinstance(value, int) else 0


def _listing_images_uploaded_now(report: ProductionReport) -> int:
    value = _listing_upload_metadata(report).get("images_uploaded_now")
    if isinstance(value, int):
        return value
    fallback = _listing_upload_metadata(report).get("images_uploaded")
    return int(fallback) if isinstance(fallback, int) else 0


def _listing_images_after(report: ProductionReport) -> int:
    value = _listing_upload_metadata(report).get("images_present_after")
    if isinstance(value, int):
        return value
    return int(report.images)


def _digital_files_after(report: ProductionReport) -> int:
    value = _digital_upload_metadata(report).get("metadata")
    if isinstance(value, dict) and isinstance(value.get("total_present"), int):
        return int(value["total_present"])
    return int(report.downloads)


def _digital_files_uploaded_now(report: ProductionReport) -> int:
    value = _digital_upload_metadata(report).get("files_uploaded")
    if isinstance(value, int):
        return value
    return int(report.downloads)


def print_recovery_report(report: FailedBatchRecoveryReport) -> None:
    """Print failed batch recovery summary."""
    print("FAILED BATCH RECOVERY")
    print("")
    print("Jobs Found")
    print(report.jobs_found)
    print("")
    print("Jobs Verified Complete")
    print(report.jobs_verified_complete)
    print("")
    print("Jobs Still Incomplete")
    print(report.jobs_still_incomplete)
    print("")
    print("Drafts Repaired")
    print(report.drafts_repaired)
    print("")
    print("Existing Drafts Reused")
    print(report.existing_drafts_reused)
    print("")
    print("New Drafts Created")
    print(report.new_drafts_created)
    print("")
    print("Images Present Before")
    print(report.images_present_before)
    print("")
    print("Missing Images Detected")
    print(report.missing_images_detected)
    print("")
    print("Images Uploaded During Repair")
    print(report.images_uploaded_during_repair)
    print("")
    print("Images Present After")
    print(report.images_present_after)
    print("")
    print("Digital Files Present After")
    print(report.digital_files_present_after)
    print("")
    print("Missing Digital Files Uploaded")
    print(report.missing_digital_files_uploaded)
    print("")
    print("Verified Complete")
    print(report.verified_complete)
    print("")
    print("Still Incomplete")
    print(report.still_incomplete)
    for item in report.reports:
        print("")
        print(f"Draft ID: {item.draft_id or ''}")
        print(f"Product: {item.product}")
        print("Existing Draft Reused: yes" if item.draft_id else "Existing Draft Reused: no")
        print("Expected Images: 4")
        print(f"Images Before: {_listing_images_before(item)}")
        print(f"Missing Images Detected: {max(0, 4 - _listing_images_before(item))}")
        print(f"Images Uploaded: {_listing_images_uploaded_now(item)}")
        print(f"Images After: {_listing_images_after(item)}")
        print("Expected Digital Files: 4")
        print(f"Digital Files After: {_digital_files_after(item)}")
        passed = _report_verified_complete(item)
        print(f"Verification: {'PASS' if passed else 'FAIL'}")
        print(f"Status: {'COMPLETE' if passed else 'NEEDS_REPAIR'}")
        if not passed:
            reason = item.errors[0] if item.errors else "final Etsy verification did not pass"
            print(f"Reason: {reason}")
    print("")
    print("Overall Status")
    print(report.status)


if __name__ == "__main__":
    main()
