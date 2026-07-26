"""Persist human approval for generated Aurora product assets."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_PATH))

from project_aurora.planning.production_queue_manager import ProductionQueueManager  # noqa: E402
from project_aurora.storage.csv_storage import CSVStorage  # noqa: E402
from project_aurora.storage.memory_manager import MemoryManager  # noqa: E402


QUEUE_PATH = PROJECT_ROOT / "data" / "aurora" / "production_queue" / "queue.json"
JOBS_DIR = PROJECT_ROOT / "data" / "aurora" / "jobs"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Approve generated Aurora product assets.")
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--notes", default="")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    queue = ProductionQueueManager(queue_path=QUEUE_PATH)
    job = next((item for item in queue.list_jobs() if item.id == args.job_id), None)
    if job is None:
        raise SystemExit(f"Job not found: {args.job_id}")
    job_root = _job_root(args.job_id)
    review_dir = job_root / "review"
    review_dir.mkdir(parents=True, exist_ok=True)
    approved_at = datetime.now().isoformat()
    marker = review_dir / "APPROVED"
    marker.write_text(f"APPROVED\n{approved_at}\n{args.notes}\n", encoding="utf-8")
    memory = MemoryManager(storage=CSVStorage(base_path=PROJECT_ROOT / "data" / "aurora"))
    memory.save_record(
        "human_product_approvals",
        args.job_id,
        {
            "job_id": args.job_id,
            "product_name": job.product_name,
            "approval_status": "APPROVED",
            "approved_at": approved_at,
            "approval_marker": str(marker),
            "notes": args.notes,
        },
    )
    print("PRODUCT APPROVAL")
    print("")
    print("Job ID")
    print(args.job_id)
    print("")
    print("Product")
    print(job.product_name)
    print("")
    print("Approval")
    print("APPROVED")
    print("")
    print("Marker")
    print(marker)


def _job_root(job_id: str) -> Path:
    prefix = job_id.replace("-", "_")[:12]
    found = next(JOBS_DIR.glob(f"{prefix}*"), None)
    if found is None:
        raise SystemExit(f"Job workspace not found for {job_id}")
    return found


if __name__ == "__main__":
    main()
