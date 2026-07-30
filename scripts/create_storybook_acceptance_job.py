"""Create one forced STORYBOOK acceptance job in the Aurora queue."""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_PATH))

from project_aurora.planning.production_queue_manager import (  # noqa: E402
    READY,
    ProductionJob,
    ProductionQueueManager,
)


QUEUE_PATH = PROJECT_ROOT / "data" / "aurora" / "production_queue" / "queue.json"
JOBS_DIR = PROJECT_ROOT / "data" / "aurora" / "jobs"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create the forced STORYBOOK acceptance job.")
    parser.add_argument("--confirm", action="store_true", help="Required to write the queue.")
    return parser.parse_args(argv)


def create_acceptance_job(queue_path: Path = QUEUE_PATH) -> ProductionJob:
    """Add exactly one Rabbit Garden Tea Party STORYBOOK job."""
    manager = ProductionQueueManager(queue_path=queue_path)
    job = manager.add_job(
        priority="High",
        product_name="Rabbit Garden Tea Party Watercolor Clipart",
        category="Digital Clipart",
        style="Whimsical Storybook Watercolor",
        seasonal_theme="Spring",
        keywords=(
            "rabbit",
            "garden tea party",
            "watercolor clipart",
            "storybook",
            "cottagecore",
        ),
        confidence_score=0.99,
        estimated_competition="Low",
        estimated_demand="High",
        estimated_revenue=120.0,
        status=READY,
        target_customer="RainbowMilkStudio buyers looking for whimsical woodland watercolor art",
        source_evidence=(
            "generation_mode=STORYBOOK",
            "acceptance_test=true",
            "brand_profile=RainbowMilkStudio",
        ),
    )
    _remove_job_workspace(job)
    return job


def _remove_job_workspace(job: ProductionJob) -> None:
    slug = "_".join(job.product_name.casefold().replace("-", " ").split())
    for path in JOBS_DIR.glob(f"{job.id.replace('-', '_')[:8]}*"):
        if path.is_dir():
            shutil.rmtree(path)
    for path in JOBS_DIR.glob(f"*{slug}*"):
        if path.is_dir() and job.id.replace("-", "_") in path.name:
            shutil.rmtree(path)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    if not args.confirm:
        raise SystemExit("Refusing to create acceptance job without --confirm.")
    job = create_acceptance_job()
    print("STORYBOOK ACCEPTANCE JOB")
    print("")
    print("Job ID")
    print(job.id)
    print("")
    print("Product")
    print(job.product_name)
    print("")
    print("Status")
    print(job.status)
    print("")
    print("Generation Override")
    print("STORYBOOK")


if __name__ == "__main__":
    main()
