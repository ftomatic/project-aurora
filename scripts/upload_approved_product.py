"""Upload one explicitly approved Aurora product."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_PATH))

from project_aurora.planning.production_queue_manager import ProductionQueueManager  # noqa: E402
from project_aurora.storage.csv_storage import CSVStorage  # noqa: E402
from project_aurora.storage.memory_manager import MemoryManager  # noqa: E402


QUEUE_PATH = PROJECT_ROOT / "data" / "aurora" / "production_queue" / "queue.json"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Upload one approved Aurora product.")
    parser.add_argument("--job-id", required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    memory = MemoryManager(storage=CSVStorage(base_path=PROJECT_ROOT / "data" / "aurora"))
    ProductionQueueManager(queue_path=QUEUE_PATH)
    try:
        memory.load_record("human_product_approvals", args.job_id)
    except FileNotFoundError:
        raise SystemExit("Product must be approved before upload.")
    completed = subprocess.run(
        [
            sys.executable,
            str(PROJECT_ROOT / "scripts" / "resume_product_factory_job.py"),
            "--job-id",
            args.job_id,
            "--live",
            "--upload",
        ],
        check=False,
    )
    raise SystemExit(completed.returncode)


if __name__ == "__main__":
    main()
