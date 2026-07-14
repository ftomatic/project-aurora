"""Run Aurora Product Factory for one ready production job."""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_PATH))

from project_aurora.integrations.etsy.etsy_config import EtsyConfig  # noqa: E402
from project_aurora.planning.production_queue_manager import (  # noqa: E402
    ProductionQueueManager,
)
from project_aurora.production.product_factory import (  # noqa: E402
    DefaultProductFactoryStageRunner,
    DryRunProductFactoryStageRunner,
    ProductFactory,
)
from project_aurora.storage.csv_storage import CSVStorage  # noqa: E402
from project_aurora.storage.memory_manager import MemoryManager  # noqa: E402


REAL_QUEUE_PATH = (
    PROJECT_ROOT
    / "data"
    / "aurora"
    / "production_queue"
    / "queue.json"
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse Product Factory mode flags."""
    parser = argparse.ArgumentParser(description="Run one Aurora Product Factory job.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="Verify one ready job without consuming the real queue.",
    )
    mode.add_argument(
        "--live",
        action="store_true",
        help="Consume one real queue job and call configured live services.",
    )
    parser.add_argument(
        "--save-report",
        action="store_true",
        help="Save a production report during dry run verification.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    """Execute exactly one ready production queue job."""
    args = parse_args(argv)
    dry_run = not args.live
    real_queue = ProductionQueueManager(queue_path=REAL_QUEUE_PATH)
    job = real_queue.next_ready_job()
    if job is None:
        print("PRODUCT FACTORY")
        print("")
        print("Mode")
        print("DRY RUN" if dry_run else "LIVE")
        print("")
        print("Status")
        print("NO_READY_JOB")
        return

    if dry_run:
        with tempfile.TemporaryDirectory() as temp_dir:
            queue_manager = ProductionQueueManager(
                queue_path=Path(temp_dir) / "queue.json"
            )
            job = queue_manager.add_existing_job(job)
            memory = MemoryManager(storage=CSVStorage(base_path=Path(temp_dir) / "memory"))
            report = ProductFactory(
                queue_manager=queue_manager,
                memory=memory,
                stage_runner=DryRunProductFactoryStageRunner(),
                dry_run=True,
                save_report=args.save_report,
            ).execute(job)
    else:
        queue_manager = real_queue
        memory = MemoryManager(
            storage=CSVStorage(base_path=PROJECT_ROOT / "data" / "aurora")
        )
        etsy_config = EtsyConfig.from_file(PROJECT_ROOT / "config" / "etsy.yaml")
        report = ProductFactory(
            queue_manager=queue_manager,
            memory=memory,
            stage_runner=DefaultProductFactoryStageRunner(
                memory=memory,
                etsy_config=etsy_config,
            ),
            dry_run=False,
        ).execute(job)

    print("PRODUCT FACTORY")
    print("")
    print("Mode")
    print("DRY RUN" if dry_run else "LIVE")
    print("")
    print("Job")
    print(report.product)
    print("")
    print("Completed")
    print("YES" if report.success else "NO")
    print("")
    print("Draft Created")
    print("YES" if report.draft_id else "NO")
    print("")
    print("Images")
    print(report.images)
    print("")
    print("Downloads")
    print(report.downloads)
    print("")
    print("Queue Status")
    print("UNCHANGED" if dry_run else report.queue_status)
    if dry_run:
        print("")
        print("Real Queue")
        print("NOT MODIFIED")
    if not report.success:
        print("")
        print("Failed Stage")
        print(report.failed_stage)
        print("")
        print("Errors")
        for error in report.errors:
            print(error)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
