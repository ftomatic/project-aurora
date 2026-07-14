"""Run Aurora Product Factory for one ready production job."""

from __future__ import annotations

import sys
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
    ProductFactory,
)
from project_aurora.storage.csv_storage import CSVStorage  # noqa: E402
from project_aurora.storage.memory_manager import MemoryManager  # noqa: E402


def main() -> None:
    """Execute exactly one ready production queue job."""
    queue_manager = ProductionQueueManager(
        queue_path=(
            PROJECT_ROOT
            / "data"
            / "aurora"
            / "production_queue"
            / "queue.json"
        )
    )
    job = queue_manager.next_ready_job()
    if job is None:
        print("PRODUCT FACTORY")
        print("")
        print("Status")
        print("NO_READY_JOB")
        return

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
    ).execute(job)

    print("PRODUCT FACTORY")
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
    print(report.queue_status)
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
