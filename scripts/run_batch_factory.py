"""Run Aurora Product Factory over multiple ready jobs sequentially."""

from __future__ import annotations

import argparse
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from time import sleep
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
    ProductionJob,
    ProductionQueueManager,
)
from project_aurora.production.product_factory import (  # noqa: E402
    REPORT_COLLECTION,
    DefaultProductFactoryStageRunner,
    DryRunProductFactoryStageRunner,
    ProductFactory,
    ProductFactoryStageRunner,
)
from project_aurora.production.production_report import (  # noqa: E402
    ProductionReport,
)
from project_aurora.storage.csv_storage import CSVStorage  # noqa: E402
from project_aurora.storage.memory_manager import MemoryManager  # noqa: E402
from scripts.run_product_factory import (  # noqa: E402
    print_etsy_config_diagnostics,
)


REAL_QUEUE_PATH = (
    PROJECT_ROOT
    / "data"
    / "aurora"
    / "production_queue"
    / "queue.json"
)
DAILY_FACTORY_CONFIG_PATH = PROJECT_ROOT / "config" / "daily_factory.yaml"


@dataclass(frozen=True, slots=True)
class BatchRuntimeConfig:
    """Runtime pacing and retry config for live batch execution."""

    openai_image_delay_seconds: float = 15.0
    openai_rate_limit_max_retries: int = 3
    openai_rate_limit_safety_seconds: float = 3.0


@dataclass(frozen=True, slots=True)
class BatchFactoryReport:
    """Summary of one sequential Product Factory batch."""

    requested: int
    attempted: int
    completed: int
    failed: int
    drafts_created: int
    draft_ids: tuple[str, ...]
    images_generated: int
    downloads_uploaded: int
    elapsed_time: float
    failure_summary: tuple[dict[str, object], ...] = field(default_factory=tuple)
    reports: tuple[ProductionReport, ...] = field(default_factory=tuple)
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, object]:
        """Return JSON-safe batch report data."""
        return {
            "requested": self.requested,
            "attempted": self.attempted,
            "completed": self.completed,
            "failed": self.failed,
            "drafts_created": self.drafts_created,
            "draft_ids": list(self.draft_ids),
            "images_generated": self.images_generated,
            "downloads_uploaded": self.downloads_uploaded,
            "elapsed_time": self.elapsed_time,
            "failure_summary": list(self.failure_summary),
            "reports": [report.to_dict() for report in self.reports],
            "created_at": self.created_at.isoformat(),
        }


class BatchProductionFactory:
    """Execute multiple ready production jobs one at a time."""

    def __init__(
        self,
        queue_manager: ProductionQueueManager,
        memory: MemoryManager,
        stage_runner_factory: Callable[[ProductionJob], ProductFactoryStageRunner],
        save_report: bool = True,
        image_delay_seconds: float = 0.0,
        sleeper: Callable[[float], None] = sleep,
    ) -> None:
        self._queue_manager = queue_manager
        self._memory = memory
        self._stage_runner_factory = stage_runner_factory
        self._save_report = save_report
        self._image_delay_seconds = image_delay_seconds
        self._sleeper = sleeper

    def run(self, count: int) -> BatchFactoryReport:
        """Run up to count ready jobs, continuing after individual failures."""
        if count <= 0:
            raise ValueError("count must be greater than zero.")

        reports: list[ProductionReport] = []
        completed = 0
        failed = 0
        draft_ids: list[str] = []
        images_generated = 0
        downloads_uploaded = 0
        elapsed_time = 0.0
        previous_generated_images = False
        for _ in range(count):
            job = self._queue_manager.next_ready_job()
            if job is None:
                break
            if previous_generated_images and self._image_delay_seconds > 0:
                self._sleeper(self._image_delay_seconds)
            factory = ProductFactory(
                queue_manager=self._queue_manager,
                memory=self._memory,
                stage_runner=self._stage_runner_factory(job),
                dry_run=False,
                save_report=self._save_report,
            )
            report = factory.execute(job)
            if not isinstance(report, ProductionReport):
                raise RuntimeError(
                    "ProductFactory.execute() did not return a ProductionReport."
                )
            print_report_diagnostics(report)
            reports.append(report)
            if report.success:
                completed += 1
            else:
                failed += 1
            draft_id = _draft_id_from_report(report)
            if draft_id:
                draft_ids.append(draft_id)
            images_generated += report.images
            downloads_uploaded += report.downloads
            elapsed_time += report.time
            previous_generated_images = _report_generated_images_now(report)

        batch_report = _build_batch_report_from_returned_reports(
            requested=count,
            reports=tuple(reports),
            completed=completed,
            failed=failed,
            draft_ids=tuple(draft_ids),
            images_generated=images_generated,
            downloads_uploaded=downloads_uploaded,
            elapsed_time=round(elapsed_time, 3),
        )
        if self._save_report:
            self._save_batch_report(batch_report)
        return batch_report

    def _save_batch_report(self, report: BatchFactoryReport) -> None:
        key = f"batch_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self._memory.save_record(REPORT_COLLECTION, "latest_batch", report.to_dict())
        self._memory.save_record(REPORT_COLLECTION, key, report.to_dict())


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse Batch Factory CLI arguments."""
    parser = argparse.ArgumentParser(description="Run Aurora Batch Factory.")
    parser.add_argument(
        "--count",
        type=int,
        default=1,
        help="Maximum number of ready jobs to process.",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="Process a temporary queue copy with no live services.",
    )
    mode.add_argument(
        "--live",
        action="store_true",
        help="Consume the real queue and call configured live services.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    """Run a sequential batch of ready Product Factory jobs."""
    args = parse_args(argv)
    dry_run = not args.live
    if dry_run:
        with tempfile.TemporaryDirectory() as temp_dir:
            report = _run_dry_batch(count=args.count, temp_dir=Path(temp_dir))
    else:
        report = _run_live_batch(count=args.count)
    print_batch_report(report)


def _run_dry_batch(count: int, temp_dir: Path) -> BatchFactoryReport:
    real_queue = ProductionQueueManager(queue_path=REAL_QUEUE_PATH)
    queue_manager = ProductionQueueManager(queue_path=temp_dir / "queue.json")
    for job in real_queue.list_jobs():
        queue_manager.add_existing_job(job)
    memory = MemoryManager(storage=CSVStorage(base_path=temp_dir / "memory"))
    return BatchProductionFactory(
        queue_manager=queue_manager,
        memory=memory,
        stage_runner_factory=lambda _job: DryRunProductFactoryStageRunner(),
        save_report=False,
    ).run(count)


def _run_live_batch(count: int) -> BatchFactoryReport:
    runtime_config = load_batch_runtime_config(DAILY_FACTORY_CONFIG_PATH)
    queue_manager = ProductionQueueManager(queue_path=REAL_QUEUE_PATH)
    memory = MemoryManager(
        storage=CSVStorage(base_path=PROJECT_ROOT / "data" / "aurora")
    )
    etsy_config = EtsyConfig.from_environment(PROJECT_ROOT / "config" / "etsy.yaml")
    image_config = ImageProviderConfig.from_file(PROJECT_ROOT / "config" / "openai.yaml")
    image_config = ImageProviderConfig(
        provider=image_config.provider,
        model=image_config.model,
        size=image_config.size,
        quality=image_config.quality,
        background=image_config.background,
        output_format=image_config.output_format,
        number_of_images=image_config.number_of_images,
        prompt_version=image_config.prompt_version,
        rate_limit_max_retries=runtime_config.openai_rate_limit_max_retries,
        rate_limit_safety_seconds=runtime_config.openai_rate_limit_safety_seconds,
    )
    print_etsy_config_diagnostics(etsy_config)
    return BatchProductionFactory(
        queue_manager=queue_manager,
        memory=memory,
        stage_runner_factory=lambda _job: DefaultProductFactoryStageRunner(
            memory=memory,
            etsy_config=etsy_config,
            image_config=image_config,
        ),
        save_report=True,
        image_delay_seconds=runtime_config.openai_image_delay_seconds,
    ).run(count)


def load_batch_runtime_config(path: Path) -> BatchRuntimeConfig:
    """Load batch pacing config from daily_factory.yaml."""
    values: dict[str, str] = {}
    if path.exists():
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or ":" not in line:
                continue
            key, value = line.split(":", maxsplit=1)
            values[key.strip()] = value.strip().strip("\"'")
    return BatchRuntimeConfig(
        openai_image_delay_seconds=float(
            values.get("openai_image_delay_seconds", "15")
        ),
        openai_rate_limit_max_retries=int(
            values.get("openai_rate_limit_max_retries", "3")
        ),
        openai_rate_limit_safety_seconds=float(
            values.get("openai_rate_limit_safety_seconds", "3")
        ),
    )


def _build_batch_report(
    requested: int,
    reports: tuple[ProductionReport, ...],
    elapsed_time: float,
) -> BatchFactoryReport:
    draft_ids = tuple(
        draft_id
        for report in reports
        if (draft_id := _draft_id_from_report(report)) is not None
    )
    report_time_total = round(sum(report.time for report in reports), 3)
    resolved_elapsed_time = report_time_total if report_time_total > 0 else elapsed_time
    failures = tuple(
        {
            "job_id": report.job_id,
            "product": report.product,
            "failed_stage": report.failed_stage,
            "errors": list(report.errors),
        }
        for report in reports
        if not report.success
    )
    return BatchFactoryReport(
        requested=requested,
        attempted=len(reports),
        completed=sum(1 for report in reports if report.success),
        failed=sum(1 for report in reports if not report.success),
        drafts_created=sum(1 for report in reports if _draft_created_from_report(report)),
        draft_ids=draft_ids,
        images_generated=sum(report.images for report in reports),
        downloads_uploaded=sum(report.downloads for report in reports),
        elapsed_time=resolved_elapsed_time,
        failure_summary=failures,
        reports=reports,
    )


def _build_batch_report_from_returned_reports(
    requested: int,
    reports: tuple[ProductionReport, ...],
    completed: int,
    failed: int,
    draft_ids: tuple[str, ...],
    images_generated: int,
    downloads_uploaded: int,
    elapsed_time: float,
) -> BatchFactoryReport:
    """Build a batch report from counters read directly after execute()."""
    failures = tuple(
        {
            "job_id": report.job_id,
            "product": report.product,
            "failed_stage": report.failed_stage,
            "errors": list(report.errors),
        }
        for report in reports
        if not report.success
    )
    return BatchFactoryReport(
        requested=requested,
        attempted=len(reports),
        completed=completed,
        failed=failed,
        drafts_created=len(draft_ids),
        draft_ids=draft_ids,
        images_generated=images_generated,
        downloads_uploaded=downloads_uploaded,
        elapsed_time=elapsed_time,
        failure_summary=failures,
        reports=reports,
    )


def _report_generated_images_now(report: ProductionReport) -> bool:
    image_generation = report.metadata.get("image_generation")
    if not isinstance(image_generation, dict):
        return False
    if str(image_generation.get("status", "")).upper() != "SUCCESS":
        return False
    warnings = image_generation.get("warnings", ())
    if isinstance(warnings, list | tuple) and any(
        "reused existing" in str(warning).casefold() for warning in warnings
    ):
        return False
    return True


def print_batch_report(report: BatchFactoryReport) -> None:
    """Print the CLI batch summary."""
    print("BATCH FACTORY")
    print("")
    print("Requested")
    print(report.requested)
    print("")
    print("Completed")
    print(report.completed)
    print("")
    print("Failed")
    print(report.failed)
    print("")
    print("Drafts Created")
    print(report.drafts_created)
    print("")
    print("Draft IDs")
    if report.draft_ids:
        for draft_id in report.draft_ids:
            print(draft_id)
    else:
        print("None")
    print("")
    print("Images Generated")
    print(report.images_generated)
    print("")
    print("Downloads Uploaded")
    print(report.downloads_uploaded)
    print("")
    print("Elapsed Time")
    print(f"{_format_elapsed_time(report.elapsed_time)} seconds")
    print("")
    print("Failure Summary")
    if not report.failure_summary:
        print("None")
    else:
        for failure in report.failure_summary:
            print(
                f"{failure['product']} - "
                f"{failure.get('failed_stage') or 'unknown'}"
            )
            for error in failure.get("errors", ()):
                print(f"  {error}")


def print_report_diagnostics(report: ProductionReport) -> None:
    """Print safe per-job report diagnostics without secrets."""
    draft_id = _draft_id_from_report(report)
    print("BATCH JOB REPORT")
    print("Report Type")
    print(type(report).__name__)
    print("Report Draft ID")
    print(draft_id if draft_id else "NONE")
    print("Report Time")
    print(report.time)
    print("Report Success")
    print("true" if report.success else "false")
    print("")


def _format_elapsed_time(value: float) -> str:
    """Format elapsed seconds without hiding short nonzero runs."""
    if value == 0:
        return "0"
    return f"{value:.3f}".rstrip("0").rstrip(".")


def _draft_id_from_report(report: ProductionReport) -> str | None:
    """Return the Etsy draft id represented by one production report."""
    if report.draft_id and report.draft_id.strip():
        return report.draft_id.strip()

    etsy_draft = report.metadata.get("etsy_draft")
    if not isinstance(etsy_draft, dict):
        return None

    listing_id = etsy_draft.get("etsy_listing_id")
    if isinstance(listing_id, str) and listing_id.strip():
        return listing_id.strip()

    status = etsy_draft.get("status")
    if isinstance(status, str) and status.strip().upper() == "DRAFT_CREATED":
        metadata = etsy_draft.get("metadata")
        if isinstance(metadata, dict):
            response = metadata.get("response")
            if isinstance(response, dict):
                response_listing_id = response.get("listing_id")
                if response_listing_id is not None:
                    return str(response_listing_id)
    return None


def _draft_created_from_report(report: ProductionReport) -> bool:
    """Return whether one production report created an Etsy draft."""
    if _draft_id_from_report(report) is not None:
        return True
    etsy_draft = report.metadata.get("etsy_draft")
    if not isinstance(etsy_draft, dict):
        return False
    status = etsy_draft.get("status")
    return isinstance(status, str) and status.strip().upper() == "DRAFT_CREATED"


if __name__ == "__main__":
    main()
