"""Recover compatible watercolor products back to READY status."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_PATH))

from project_aurora.planning.production_queue_manager import (  # noqa: E402
    FAILED,
    READY,
    ProductionQueueManager,
)
from project_aurora.production.watercolor_scope import resolve_watercolor_scope  # noqa: E402


QUEUE_PATH = PROJECT_ROOT / "data" / "aurora" / "production_queue" / "queue.json"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Recover supported watercolor products.")
    parser.add_argument("--dry-run", action="store_true", default=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--all-eligible", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    manager = ProductionQueueManager(queue_path=QUEUE_PATH)
    jobs = manager.list_jobs()
    eligible = []
    for job in jobs:
        if args.limit and len(eligible) >= args.limit:
            break
        if job.status not in {READY, FAILED}:
            continue
        decision = resolve_watercolor_scope(job.product_name, job.category, job.style)
        if not decision.supported:
            continue
        if job.status == READY or args.all_eligible:
            eligible.append((job, decision))
    print("SUPPORTED PRODUCT RECOVERY")
    print("Mode")
    print("APPLY" if args.apply else "DRY_RUN")
    for job, decision in eligible:
        print("")
        print("Product ID")
        print(job.id)
        print("Product Name")
        print(job.product_name)
        print("Current Status")
        print(job.status)
        print("Proposed Status")
        print(READY)
        print("Current Type")
        print(job.category)
        print("Canonical Type")
        print(decision.canonical_product_type)
        print("Reason")
        print(decision.reason)
        if args.apply:
            manager.mark_product_ready(job.product_name)
    print("")
    print("Products Reviewed")
    print(len(jobs))
    print("Products Changed")
    print(len(eligible) if args.apply else 0)


if __name__ == "__main__":
    main()
