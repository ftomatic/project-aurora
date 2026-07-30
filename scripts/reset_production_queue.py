"""Safely archive and reset Aurora's active production queue."""

from __future__ import annotations

import argparse
import shutil
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_PATH))

from project_aurora.planning.production_queue_manager import ProductionQueueManager  # noqa: E402


DATA_ROOT = PROJECT_ROOT / "data" / "aurora"
QUEUE_PATH = DATA_ROOT / "production_queue" / "queue.json"
ARCHIVE_ROOT = DATA_ROOT / "archive"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Archive and reset Aurora production queue.")
    parser.add_argument("--archive", action="store_true", help="Archive current queue state before reset.")
    parser.add_argument("--confirm", action="store_true", help="Required confirmation for reset.")
    return parser.parse_args(argv)


def archive_current_state(timestamp: str | None = None) -> Path:
    """Copy recoverable production state into a timestamped archive directory."""
    stamp = timestamp or datetime.now().strftime("%Y%m%d_%H%M%S")
    archive_dir = ARCHIVE_ROOT / f"reset_{stamp}"
    archive_dir.mkdir(parents=True, exist_ok=False)
    copied: list[str] = []
    _copy_file_if_exists(QUEUE_PATH, archive_dir / "production_queue" / "queue.json", copied)
    for folder_name in (
        "production_reports",
        "jobs",
        "etsy_complete_drafts",
        "etsy_drafts",
        "etsy_image_uploads",
        "etsy_digital_file_uploads",
        "etsy_upload_checkpoints",
    ):
        source = DATA_ROOT / folder_name
        if source.exists():
            shutil.copytree(source, archive_dir / folder_name)
            copied.append(folder_name)
    (archive_dir / "archive_manifest.txt").write_text(
        "\n".join(copied) + "\n",
        encoding="utf-8",
    )
    return archive_dir


def reset_queue() -> Path:
    """Write a valid empty queue and verify it can be loaded."""
    QUEUE_PATH.parent.mkdir(parents=True, exist_ok=True)
    QUEUE_PATH.write_text(
        '{\n  "job_count": 0,\n  "jobs": [],\n  "saved_at": "reset"\n}\n',
        encoding="utf-8",
    )
    manager = ProductionQueueManager(queue_path=QUEUE_PATH)
    if manager.list_jobs():
        raise RuntimeError("Queue reset verification failed; jobs are still loaded.")
    return QUEUE_PATH


def _copy_file_if_exists(source: Path, target: Path, copied: list[str]) -> None:
    if not source.exists():
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    copied.append(str(source.relative_to(DATA_ROOT)))


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    if not args.confirm:
        raise SystemExit("Refusing to reset queue without --confirm.")
    if not args.archive:
        raise SystemExit("Refusing to reset queue without --archive.")
    archive_dir = archive_current_state()
    queue_path = reset_queue()
    ready_count = sum(1 for job in ProductionQueueManager(queue_path=queue_path).list_jobs() if job.status == "READY")
    print("AURORA PRODUCTION RESET")
    print("")
    print("Archive Path")
    print(archive_dir)
    print("")
    print("Queue Reset")
    print(queue_path)
    print("")
    print("READY Count")
    print(ready_count)
    print("")
    print("Remote Etsy Drafts")
    print("Not touched")


if __name__ == "__main__":
    main()
