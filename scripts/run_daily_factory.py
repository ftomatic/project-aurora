"""Run Aurora's daily dynamic market planner and 10-listing factory."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(SRC_PATH))

from project_aurora.config.local_env import load_local_env  # noqa: E402
from project_aurora.config.profile_loader import ProjectProfileLoader  # noqa: E402
from project_aurora.image_generation.image_cost_estimator import (  # noqa: E402
    ImageCostEstimator,
)
from project_aurora.image_generation.provider_registry import (  # noqa: E402
    ImageProviderConfig,
)
from project_aurora.integrations.etsy.etsy_token_manager import (  # noqa: E402
    EtsyTokenManager,
)
from project_aurora.planning.dynamic_product_planner import (  # noqa: E402
    DynamicProductPlanner,
)
from project_aurora.planning.production_queue_manager import (  # noqa: E402
    READY,
    ProductionQueueManager,
)
from project_aurora.portfolio.ai_portfolio_manager import (  # noqa: E402
    AIPortfolioManager,
    ScoredPortfolioCandidate,
)
from project_aurora.portfolio.portfolio_memory import PortfolioMemory  # noqa: E402
from project_aurora.research.dynamic_market_research import (  # noqa: E402
    DynamicMarketResearchEngine,
)
from project_aurora.storage.csv_storage import CSVStorage  # noqa: E402
from project_aurora.storage.memory_manager import MemoryManager  # noqa: E402
from scripts.run_batch_factory import BatchProductionFactory, _run_live_batch  # noqa: E402


QUEUE_PATH = PROJECT_ROOT / "data" / "aurora" / "production_queue" / "queue.json"
DAILY_REPORTS_DIR = PROJECT_ROOT / "data" / "aurora" / "daily_reports"


@dataclass(frozen=True, slots=True)
class DailyFactoryConfig:
    """Daily factory runtime limits."""

    enabled: bool
    daily_product_count: int
    max_daily_products: int
    max_daily_images: int
    max_estimated_daily_cost: float
    continue_after_failure: bool
    require_live_confirmation_for_manual_runs: bool
    schedule_hour: int
    schedule_minute: int
    timezone: str


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse daily factory CLI arguments."""
    parser = argparse.ArgumentParser(description="Run Aurora Daily Factory.")
    parser.add_argument("--count", type=int, default=10)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--scheduled", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    """Run today's dynamic planning and sequential factory."""
    args = parse_args(argv)
    load_local_env(PROJECT_ROOT / "config" / "aurora.local.env")
    config = load_daily_factory_config(PROJECT_ROOT / "config" / "daily_factory.yaml")
    if not config.enabled:
        raise SystemExit("Daily factory is disabled.")
    count = min(args.count, config.max_daily_products)
    image_config = ImageProviderConfig.from_file(PROJECT_ROOT / "config" / "openai.yaml")
    images_planned = count * image_config.number_of_images
    if images_planned > config.max_daily_images:
        raise SystemExit("Daily image limit exceeded.")
    estimate = ImageCostEstimator().estimate(
        provider=image_config.provider,
        quality=image_config.quality,
        number_of_images=images_planned,
    )
    if estimate.total_cost > config.max_estimated_daily_cost:
        raise SystemExit("Estimated daily image cost exceeds configured limit.")
    if args.live and not args.scheduled and config.require_live_confirmation_for_manual_runs:
        print("Products Planned")
        print(count)
        print("")
        print("Images Planned")
        print(images_planned)
        print("")
        print("Estimated Image Cost")
        print(estimate.render())
        print("")
        confirmation = input(f"Type RUN {count} to continue\n")
        if confirmation.strip() != f"RUN {count}":
            raise SystemExit("Daily factory cancelled.")

    if args.scheduled:
        EtsyTokenManager(PROJECT_ROOT / "config" / "aurora.local.env").refresh_if_needed()

    if args.live:
        report = run_daily_factory(
            count=count,
            live=True,
            cost_estimate=estimate.total_cost,
        )
    else:
        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            report = run_daily_factory(
                count=count,
                live=False,
                cost_estimate=estimate.total_cost,
                queue_path=temp_path / "queue.json",
                reports_dir=temp_path / "daily_reports",
                save_daily_report=False,
            )
    print_daily_report(report)


def run_daily_factory(
    count: int,
    live: bool,
    cost_estimate: float,
    queue_path: Path | None = None,
    reports_dir: Path | None = None,
    save_daily_report: bool = True,
) -> dict[str, Any]:
    """Run research, planning, sequential production, and report saving."""
    started_at = datetime.now()
    resolved_queue_path = queue_path or QUEUE_PATH
    resolved_reports_dir = reports_dir or DAILY_REPORTS_DIR
    queue_manager = ProductionQueueManager(queue_path=resolved_queue_path)
    memory = MemoryManager(storage=CSVStorage(base_path=PROJECT_ROOT / "data" / "aurora"))
    profile = ProjectProfileLoader().load(
        PROJECT_ROOT / "config" / "projects" / "rainbow_milk_studio.yaml"
    )
    research = DynamicMarketResearchEngine().run()
    planner = DynamicProductPlanner(
        queue_manager=queue_manager,
        project_profile=profile,
    )
    candidates = planner.generate_candidates(research)
    portfolio_plan = AIPortfolioManager().plan(
        candidates=candidates,
        research=research,
        memory=PortfolioMemory.from_queue(queue_manager),
        count=count,
    )
    _add_portfolio_jobs(queue_manager, portfolio_plan.selected)
    if live:
        batch = _run_live_batch(count=count)
    else:
        from scripts.run_batch_factory import _run_dry_batch

        with TemporaryDirectory() as temp_dir:
            temp_dir_path = Path(temp_dir)
            from scripts import run_batch_factory

            original_real_queue = run_batch_factory.REAL_QUEUE_PATH
            run_batch_factory.REAL_QUEUE_PATH = resolved_queue_path
            try:
                batch = _run_dry_batch(count=count, temp_dir=temp_dir_path)
            finally:
                run_batch_factory.REAL_QUEUE_PATH = original_real_queue

    status = "SUCCESS"
    if batch.failed:
        status = "PARTIAL_FAILURE" if batch.completed else "FAILED"
    report = {
        "date": date.today().isoformat(),
        "research_providers_used": list(research.providers_used),
        "research_providers_unavailable": [
            {"provider": item.provider, "reason": item.reason}
            for item in research.providers_unavailable
        ],
        "candidates_evaluated": len(portfolio_plan.candidates),
        "duplicates_rejected": [
            item.product_name for item in portfolio_plan.rejected_duplicates
        ],
        "products_selected": [item.product_name for item in portfolio_plan.selected],
        "portfolio": portfolio_plan.to_report(),
        "products_completed": batch.completed,
        "products_failed": batch.failed,
        "etsy_draft_ids": list(batch.draft_ids),
        "images_generated": batch.images_generated,
        "downloads_uploaded": batch.downloads_uploaded,
        "estimated_image_cost": cost_estimate,
        "actual_configured_image_cost": cost_estimate,
        "elapsed_time": batch.elapsed_time,
        "failed_stages": [
            failure.get("failed_stage") for failure in batch.failure_summary
        ],
        "ai_disclosure": "MANUAL_REQUIRED",
        "next_scheduled_run": "08:00 America/New_York",
        "status": status,
        "created_at": started_at.isoformat(),
    }
    if save_daily_report:
        resolved_reports_dir.mkdir(parents=True, exist_ok=True)
        path = resolved_reports_dir / f"{date.today().isoformat()}.json"
        path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
        memory.save_record("daily_reports", "latest", report)
    return report


def _add_portfolio_jobs(
    queue_manager: ProductionQueueManager,
    selected: tuple[ScoredPortfolioCandidate, ...],
) -> None:
    """Persist selected portfolio candidates as READY queue jobs."""
    for item in selected:
        candidate = item.candidate
        try:
            queue_manager.add_job(
                priority="High" if candidate.confidence_score >= 0.86 else "Medium",
                product_name=candidate.product_name,
                category=candidate.product_type,
                style=item.art_style,
                seasonal_theme=candidate.season,
                keywords=candidate.keywords,
                confidence_score=round(candidate.confidence_score, 2),
                estimated_competition=_competition_label(candidate.competition_score),
                estimated_demand=_demand_label(candidate.demand_score),
                estimated_revenue=round(80 + candidate.confidence_score * 90, 2),
                status=READY,
                target_customer=candidate.target_customer,
                demand_score=candidate.demand_score,
                competition_score=candidate.competition_score,
                source_evidence=candidate.source_evidence,
            )
        except ValueError:
            continue


def _competition_label(score: float) -> str:
    if score < 0.4:
        return "Low"
    if score < 0.7:
        return "Medium"
    return "High"


def _demand_label(score: float) -> str:
    if score >= 0.75:
        return "High"
    if score >= 0.5:
        return "Medium"
    return "Low"


def print_daily_report(report: dict[str, Any]) -> None:
    """Print daily factory summary."""
    print("AURORA DAILY FACTORY")
    print("")
    print("Date")
    print(report["date"])
    print("")
    print("Products Planned")
    print(len(report["products_selected"]))
    print("")
    if report.get("portfolio"):
        portfolio = report["portfolio"]
        print("Today's Portfolio")
        print("\n".join(portfolio["today_portfolio"]))
        print("")
        print("Wildcard Selection")
        print(portfolio["wildcard_selection"] or "None")
        print("")
    print("Products Completed")
    print(report["products_completed"])
    print("")
    print("Products Failed")
    print(report["products_failed"])
    print("")
    print("Drafts Created")
    print(len(report["etsy_draft_ids"]))
    print("")
    print("Images Generated")
    print(report["images_generated"])
    print("")
    print("Downloads Uploaded")
    print(report["downloads_uploaded"])
    print("")
    print("Draft IDs")
    print("\n".join(report["etsy_draft_ids"]) if report["etsy_draft_ids"] else "None")
    print("")
    print("AI Disclosure")
    print("MANUAL_REQUIRED")
    print("")
    print("Status")
    print(report["status"])


def load_daily_factory_config(path: Path) -> DailyFactoryConfig:
    """Load simple daily factory YAML config."""
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, value = line.split(":", maxsplit=1)
        values[key.strip()] = value.strip().strip("\"'")
    return DailyFactoryConfig(
        enabled=_bool(values.get("enabled", "true")),
        daily_product_count=int(values.get("daily_product_count", "10")),
        max_daily_products=int(values.get("max_daily_products", "10")),
        max_daily_images=int(values.get("max_daily_images", "40")),
        max_estimated_daily_cost=float(values.get("max_estimated_daily_cost", "5.0")),
        continue_after_failure=_bool(values.get("continue_after_failure", "true")),
        require_live_confirmation_for_manual_runs=_bool(
            values.get("require_live_confirmation_for_manual_runs", "true")
        ),
        schedule_hour=int(values.get("schedule_hour", "8")),
        schedule_minute=int(values.get("schedule_minute", "0")),
        timezone=values.get("timezone", "America/New_York"),
    )


def _bool(value: str) -> bool:
    return value.casefold() in {"1", "true", "yes", "on"}


if __name__ == "__main__":
    main()
