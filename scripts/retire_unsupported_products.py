"""Safely retire unsupported products from active Aurora production."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_PATH))

from project_aurora.planning.production_queue_manager import (  # noqa: E402
    FAILED,
    NEEDS_ASSETS,
    READY,
    UNSUPPORTED_PRODUCT_TYPE,
    ProductionQueueManager,
)
from project_aurora.production.watercolor_scope import resolve_watercolor_scope  # noqa: E402


QUEUE_PATH = PROJECT_ROOT / "data" / "aurora" / "production_queue" / "queue.json"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Retire unsupported pending Aurora products.")
    parser.add_argument("--dry-run", action="store_true", default=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    manager = ProductionQueueManager(queue_path=QUEUE_PATH)
    jobs = manager.list_jobs()
    changed = []
    for job in jobs:
        if args.limit and len(changed) >= args.limit:
            break
        if job.status not in {READY, FAILED, NEEDS_ASSETS}:
            continue
        decision = resolve_watercolor_scope(job.product_name, job.category, job.style)
        if decision.supported:
            continue
        changed.append((job, decision))
    print("UNSUPPORTED PRODUCT RETIREMENT")
    print("Mode")
    print("APPLY" if args.apply else "DRY_RUN")
    for job, decision in changed:
        print("")
        print("Product ID")
        print(job.id)
        print("Product Name")
        print(job.product_name)
        print("Current Status")
        print(job.status)
        print("Proposed Status")
        print(UNSUPPORTED_PRODUCT_TYPE)
        print("Current Type")
        print(job.category)
        print("Canonical Type")
        print("UNSUPPORTED")
        print("Reason")
        print(decision.reason)
        if args.apply:
            manager.mark_unsupported_product_type(job.id, decision.reason)
    print("")
    print("Products Reviewed")
    print(len(jobs))
    print("Products Changed")
    print(len(changed) if args.apply else 0)


if __name__ == "__main__":
    main()
