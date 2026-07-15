"""Run Aurora Product Factory over multiple ready jobs sequentially."""

from __future__ import annotations

import argparse
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from time import perf_counter
from typing import Callable

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(SRC_PATH))

from project_aurora.integrations.etsy.etsy_config import EtsyConfig  # noqa: E402
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


@dataclass(frozen=True, slots=True)
class BatchFactoryReport:
    """Summary of one sequential Product Factory batch."""

    requested: int
    attempted: int
    completed: int
    failed: int
    drafts_created: int
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
    ) -> None:
        self._queue_manager = queue_manager
        self._memory = memory
        self._stage_runner_factory = stage_runner_factory
        self._save_report = save_report

    def run(self, count: int) -> BatchFactoryReport:
        """Run up to count ready jobs, continuing after individual failures."""
        if count <= 0:
            raise ValueError("count must be greater than zero.")

        started_at = perf_counter()
        reports: list[ProductionReport] = []
        for _ in range(count):
            job = self._queue_manager.next_ready_job()
            if job is None:
                break
            report = ProductFactory(
                queue_manager=self._queue_manager,
                memory=self._memory,
                stage_runner=self._stage_runner_factory(job),
                dry_run=False,
                save_report=self._save_report,
            ).execute(job)
            reports.append(report)

        batch_report = _build_batch_report(
            requested=count,
            reports=tuple(reports),
            elapsed_time=round(perf_counter() - started_at, 3),
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
    queue_manager = ProductionQueueManager(queue_path=REAL_QUEUE_PATH)
    memory = MemoryManager(
        storage=CSVStorage(base_path=PROJECT_ROOT / "data" / "aurora")
    )
    etsy_config = EtsyConfig.from_environment(PROJECT_ROOT / "config" / "etsy.yaml")
    print_etsy_config_diagnostics(etsy_config)
    return BatchProductionFactory(
        queue_manager=queue_manager,
        memory=memory,
        stage_runner_factory=lambda _job: DefaultProductFactoryStageRunner(
            memory=memory,
            etsy_config=etsy_config,
        ),
        save_report=True,
    ).run(count)


def _build_batch_report(
    requested: int,
    reports: tuple[ProductionReport, ...],
    elapsed_time: float,
) -> BatchFactoryReport:
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
        drafts_created=sum(1 for report in reports if report.draft_id),
        images_generated=sum(report.images for report in reports if report.success),
        downloads_uploaded=sum(report.downloads for report in reports if report.success),
        elapsed_time=elapsed_time,
        failure_summary=failures,
        reports=reports,
    )


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
    print("Images Generated")
    print(report.images_generated)
    print("")
    print("Downloads Uploaded")
    print(report.downloads_uploaded)
    print("")
    print("Elapsed Time")
    print(f"{report.elapsed_time:.2f} seconds")
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


if __name__ == "__main__":
    main()
