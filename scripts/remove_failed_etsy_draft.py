"""Identify a failed Aurora Etsy draft without deleting it by default."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_PATH))

from project_aurora.storage.csv_storage import CSVStorage  # noqa: E402
from project_aurora.storage.memory_manager import MemoryManager  # noqa: E402


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Identify a failed Etsy draft mapped to a job.")
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--confirm", action="store_true", help="Reserved for future deletion support.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    memory = MemoryManager(storage=CSVStorage(base_path=PROJECT_ROOT / "data" / "aurora"))
    try:
        report = memory.load_record("production_reports", args.job_id)
    except FileNotFoundError:
        raise SystemExit(f"No production report found for job {args.job_id}")
    print("FAILED ETSY DRAFT INSPECTION")
    print("Job ID")
    print(args.job_id)
    print("Product")
    print(report.get("product", ""))
    print("Etsy Draft ID")
    print(report.get("draft_id") or "NONE")
    print("Failed Stage")
    print(report.get("failed_stage") or "")
    print("Safe To Delete")
    print("YES" if report.get("draft_id") and not report.get("success") else "NO")
    print("Action")
    print("No deletion performed. This command is inspection-only in the hotfix.")


if __name__ == "__main__":
    main()
