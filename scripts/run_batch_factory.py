"""Run Aurora Product Factory over multiple ready jobs sequentially."""

from __future__ import annotations

import argparse
import sys
import tempfile
from dataclasses import dataclass, field, replace
from datetime import datetime
from pathlib import Path
from time import sleep
from typing import Callable

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(SRC_PATH))

from project_aurora.integrations.etsy.etsy_config import EtsyConfig  # noqa: E402
from project_aurora.image_generation.provider_registry import (  # noqa: E402
    ImageProviderConfig,
)
from project_aurora.planning.production_queue_manager import (  # noqa: E402
    COMPLETED,
    FAILED,
    READY,
    ProductionJob,
    ProductionQueueManager,
)
from project_aurora.production.product_capability_resolver import (  # noqa: E402
    ProductCapabilityResolver,
)
from project_aurora.production.product_factory import (  # noqa: E402
    REPORT_COLLECTION,
    DefaultProductFactoryStageRunner,
    DryRunProductFactoryStageRunner,
    ProductFactory,
    ProductFactoryStageRunner,
)
from project_aurora.production.generation_strategy import (  # noqa: E402
    GENERATION_MODE_AUTO,
    GENERATION_MODE_BOTANICAL,
    GENERATION_MODE_CHARACTERS,
    GENERATION_MODE_CLIPART,
    GENERATION_MODE_DIGITAL_PAPER,
    GENERATION_MODE_STORYBOOK,
    GENERATION_MODE_WEDDING,
    GenerationStrategyResolver,
    normalize_generation_mode,
)
from project_aurora.production.production_report import (  # noqa: E402
    ProductionReport,
)
from project_aurora.storage.csv_storage import CSVStorage  # noqa: E402
from project_aurora.storage.memory_manager import MemoryManager  # noqa: E402
from scripts.run_product_factory import (  # noqa: E402
    print_etsy_config_diagnostics,
)
from project_aurora.config.local_env import load_local_env  # noqa: E402
from project_aurora.portfolio.atlas_portfolio_manager import (  # noqa: E402
    AtlasPortfolioManager,
)
from project_aurora.research.athena_market_intelligence import (  # noqa: E402
    AthenaMarketIntelligence,
)
from project_aurora.research.research_config import ResearchPlannerConfig  # noqa: E402
from scripts.run_research_planner import (  # noqa: E402
    build_brand_profile_portfolio_candidates,
    handoff_to_forge,
)


REAL_QUEUE_PATH = (
    PROJECT_ROOT
    / "data"
    / "aurora"
    / "production_queue"
    / "queue.json"
)
DAILY_FACTORY_CONFIG_PATH = PROJECT_ROOT / "config" / "daily_factory.yaml"
LOCAL_ENV_PATH = PROJECT_ROOT / "config" / "aurora.local.env"
RESEARCH_CONFIG_PATH = PROJECT_ROOT / "config" / "research.yaml"
GENERATION_MIX_CONFIG_PATH = PROJECT_ROOT / "config" / "generation_mix.yaml"


@dataclass(frozen=True, slots=True)
class BatchRuntimeConfig:
    """Runtime pacing and retry config for live batch execution."""

    openai_image_delay_seconds: float = 15.0
    openai_rate_limit_max_retries: int = 3
    openai_rate_limit_safety_seconds: float = 3.0
    auto_refill_queue: bool = True


@dataclass(frozen=True, slots=True)
class BatchFactoryReport:
    """Summary of one sequential Product Factory batch."""

    requested: int
    attempted: int
    completed: int
    failed: int
    skipped: int
    drafts_created: int
    draft_ids: tuple[str, ...]
    images_generated: int
    downloads_uploaded: int
    elapsed_time: float
    failure_summary: tuple[dict[str, object], ...] = field(default_factory=tuple)
    reports: tuple[ProductionReport, ...] = field(default_factory=tuple)
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, object]:
        """Return JSON-safe batch report data."""
        return {
            "requested": self.requested,
            "attempted": self.attempted,
            "completed": self.completed,
            "failed": self.failed,
            "skipped": self.skipped,
            "drafts_created": self.drafts_created,
            "draft_ids": list(self.draft_ids),
            "images_generated": self.images_generated,
            "downloads_uploaded": self.downloads_uploaded,
            "elapsed_time": self.elapsed_time,
            "failure_summary": list(self.failure_summary),
            "reports": [report.to_dict() for report in self.reports],
            "created_at": self.created_at.isoformat(),
        }


class BatchProductionFactory:
    """Execute multiple ready production jobs one at a time."""

    def __init__(
        self,
        queue_manager: ProductionQueueManager,
        memory: MemoryManager,
        stage_runner_factory: Callable[[ProductionJob], ProductFactoryStageRunner],
        save_report: bool = True,
        image_delay_seconds: float = 0.0,
        sleeper: Callable[[float], None] = sleep,
        auto_refill_queue: bool = True,
        queue_refill: Callable[[ProductionQueueManager, int], int] | None = None,
        generation_mode: str = GENERATION_MODE_AUTO,
    ) -> None:
        self._queue_manager = queue_manager
        self._memory = memory
        self._stage_runner_factory = stage_runner_factory
        self._save_report = save_report
        self._image_delay_seconds = image_delay_seconds
        self._sleeper = sleeper
        self._auto_refill_queue = auto_refill_queue
        self._queue_refill = queue_refill
        self._generation_mode = normalize_generation_mode(generation_mode)

    def run(self, count: int) -> BatchFactoryReport:
        """Run up to count ready jobs, continuing after individual failures."""
        if count <= 0:
            raise ValueError("count must be greater than zero.")

        reports: list[ProductionReport] = []
        completed = 0
        failed = 0
        skipped = 0
        draft_ids: list[str] = []
        images_generated = 0
        downloads_uploaded = 0
        elapsed_time = 0.0
        previous_generated_images = False
        print_queue_selection_diagnostics(self._queue_manager)
        self._refill_queue_when_ready_is_empty(count)
        while completed + failed < count:
            job = self._next_ready_job_for_mode(count)
            if job is None:
                print("")
                print("Queue Selection")
                print("Selected")
                print("None")
                print("Reason")
                print("No READY jobs remain after queue loading and capability skips.")
                break
            print("")
            print("Queue Selection")
            print("Selected")
            print(f"{job.id} - {job.product_name}")
            if previous_generated_images and self._image_delay_seconds > 0:
                self._sleeper(self._image_delay_seconds)
            effective_job = _job_with_generation_strategy(
                job,
                self._generation_mode,
            )
            factory = ProductFactory(
                queue_manager=self._queue_manager,
                memory=self._memory,
                stage_runner=self._stage_runner_factory(effective_job),
                dry_run=False,
                save_report=self._save_report,
            )
            report = factory.execute(effective_job)
            if not isinstance(report, ProductionReport):
                raise RuntimeError(
                    "ProductFactory.execute() did not return a ProductionReport."
                )
            print_report_diagnostics(report)
            if (
                not report.success
                and report.failed_stage == "product_capability"
                and any(
                    "Unsupported recovery product type" in error
                    or "outside the approved watercolor" in error
                    or "Rejected because brand score" in error
                    for error in report.errors
                )
            ):
                skipped += 1
                reports.append(report)
                print("READY Job Skipped")
                print(job.product_name)
                print("Reason")
                print("; ".join(report.errors) if report.errors else "product_capability")
                print("")
                continue
            reports.append(report)
            if report.success:
                completed += 1
            else:
                failed += 1
            draft_id = _draft_id_from_report(report)
            if draft_id:
                draft_ids.append(draft_id)
            images_generated += report.images
            downloads_uploaded += report.downloads
            elapsed_time += report.time
            previous_generated_images = _report_generated_images_now(report)

        batch_report = _build_batch_report_from_returned_reports(
            requested=count,
            reports=tuple(reports),
            completed=completed,
            failed=failed,
            skipped=skipped,
            draft_ids=tuple(draft_ids),
            images_generated=images_generated,
            downloads_uploaded=downloads_uploaded,
            elapsed_time=round(elapsed_time, 3),
        )
        if self._save_report:
            self._save_batch_report(batch_report)
        return batch_report

    def _next_ready_job_for_mode(self, count: int) -> ProductionJob | None:
        """Return a READY job compatible with the requested explicit mode."""
        if self._generation_mode == GENERATION_MODE_AUTO:
            return self._queue_manager.next_ready_job()
        match = _first_ready_job_matching_generation_mode(
            self._queue_manager.list_jobs(),
            self._generation_mode,
        )
        if match is not None:
            return match
        print("")
        print("Explicit Mode Selection")
        print("Requested Mode")
        print(self._generation_mode)
        print("Matching READY Jobs")
        print("0")
        if self._auto_refill_queue and self._queue_refill is not None:
            print("Running research planner for requested mode...")
            created = self._queue_refill(self._queue_manager, count)
            print(f"Generated {created} new mode-specific jobs.")
            return _first_ready_job_matching_generation_mode(
                self._queue_manager.list_jobs(),
                self._generation_mode,
            )
        return None

    def _refill_queue_when_ready_is_empty(self, count: int) -> None:
        """Run planning when no READY work exists."""
        jobs = self._queue_manager.list_jobs()
        if any(job.status == READY for job in jobs):
            return
        print("")
        print("Queue empty.")
        if not self._auto_refill_queue:
            print("Auto refill disabled.")
            return
        print("Running research planner...")
        if self._queue_refill is None:
            print("Generated 0 new jobs.")
            print("Reason")
            print("No queue refill pipeline is configured for this runner.")
            return
        created = self._queue_refill(self._queue_manager, count)
        print(f"Generated {created} new jobs.")
        if created > 0:
            print("Continuing production.")
        else:
            print("Reason")
            print("Planner produced zero new jobs.")

    def _promote_eligible_jobs_when_ready_is_empty(self, count: int) -> None:
        """Legacy retry policy hook; never retries FAILED jobs by default."""
        jobs = self._queue_manager.list_jobs()
        if any(job.status == READY for job in jobs):
            return
        resolver = ProductCapabilityResolver()
        promoted = 0
        print("")
        print("Queue Auto Promotion")
        print("WARNING")
        print("Retry policy is disabled for FAILED jobs.")
        for job in jobs:
            if promoted >= count:
                break
            if job.status == COMPLETED:
                print(f"{job.id} - {job.product_name}")
                print("SKIPPED")
                print("Completed jobs are not retried automatically.")
                continue
            if job.status == FAILED:
                print(f"{job.id} - {job.product_name}")
                print("SKIPPED")
                print("Failed jobs require an explicit retry policy.")
                continue
            capability = resolver.resolve(job.product_name, job.category, job.category)
            if not capability.supported:
                print(f"{job.id} - {job.product_name}")
                print("SKIPPED")
                print(capability.reason)
                continue
            self._queue_manager.mark_ready(job.id)
            promoted += 1
            print(f"{job.id} - {job.product_name}")
            print("PROMOTED_TO_READY")
            if job.status != READY:
                print("WARNING")
                print(f"Recovered queued job from {job.status}.")
        if promoted == 0:
            print("None")

    def _save_batch_report(self, report: BatchFactoryReport) -> None:
        key = f"batch_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self._memory.save_record(REPORT_COLLECTION, "latest_batch", report.to_dict())
        self._memory.save_record(REPORT_COLLECTION, key, report.to_dict())


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse Batch Factory CLI arguments."""
    parser = argparse.ArgumentParser(description="Run Aurora Batch Factory.")
    parser.add_argument(
        "--count",
        type=int,
        default=1,
        help="Maximum number of ready jobs to process.",
    )
    parser.add_argument(
        "--mode",
        default="auto",
        choices=("auto", "storybook", "clipart", "characters", "botanical", "digital-paper", "wedding"),
        help="Generation mode override for this run.",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="Process a temporary queue copy with no live services.",
    )
    mode.add_argument(
        "--live",
        action="store_true",
        help="Consume the real queue and call configured live services.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    """Run a sequential batch of ready Product Factory jobs."""
    args = parse_args(argv)
    dry_run = not args.live
    if dry_run:
        with tempfile.TemporaryDirectory() as temp_dir:
            report = _run_dry_batch(
                count=args.count,
                temp_dir=Path(temp_dir),
                generation_mode=args.mode,
            )
    else:
        report = _run_live_batch(count=args.count, generation_mode=args.mode)
    print_batch_report(report)


def _run_dry_batch(
    count: int,
    temp_dir: Path,
    generation_mode: str = GENERATION_MODE_AUTO,
) -> BatchFactoryReport:
    real_queue = ProductionQueueManager(queue_path=REAL_QUEUE_PATH)
    queue_manager = ProductionQueueManager(queue_path=temp_dir / "queue.json")
    for job in real_queue.list_jobs():
        queue_manager.add_existing_job(job)
    memory = MemoryManager(storage=CSVStorage(base_path=temp_dir / "memory"))
    return BatchProductionFactory(
        queue_manager=queue_manager,
        memory=memory,
        stage_runner_factory=lambda _job: DryRunProductFactoryStageRunner(),
        save_report=False,
        generation_mode=generation_mode,
    ).run(count)


def _run_live_batch(
    count: int,
    generation_mode: str = GENERATION_MODE_AUTO,
) -> BatchFactoryReport:
    loaded_env = load_local_env(LOCAL_ENV_PATH)
    print("OpenAI API Key Loaded")
    print("YES" if "OPENAI_API_KEY" in loaded_env else "NO")
    print("")
    if "OPENAI_API_KEY" not in loaded_env:
        raise RuntimeError("OPENAI_API_KEY is required in config/aurora.local.env.")

    runtime_config = load_batch_runtime_config(DAILY_FACTORY_CONFIG_PATH)
    queue_manager = ProductionQueueManager(queue_path=REAL_QUEUE_PATH)
    memory = MemoryManager(
        storage=CSVStorage(base_path=PROJECT_ROOT / "data" / "aurora")
    )
    etsy_config = EtsyConfig.from_environment(PROJECT_ROOT / "config" / "etsy.yaml")
    image_config = ImageProviderConfig.from_file(PROJECT_ROOT / "config" / "openai.yaml")
    image_config = ImageProviderConfig(
        provider=image_config.provider,
        model=image_config.model,
        size=image_config.size,
        quality=image_config.quality,
        background=image_config.background,
        output_format=image_config.output_format,
        number_of_images=image_config.number_of_images,
        prompt_version=image_config.prompt_version,
        rate_limit_max_retries=runtime_config.openai_rate_limit_max_retries,
        rate_limit_safety_seconds=runtime_config.openai_rate_limit_safety_seconds,
    )
    print_etsy_config_diagnostics(etsy_config)
    return BatchProductionFactory(
        queue_manager=queue_manager,
        memory=memory,
        stage_runner_factory=lambda _job: DefaultProductFactoryStageRunner(
            memory=memory,
            etsy_config=etsy_config,
            image_config=image_config,
        ),
        save_report=True,
        image_delay_seconds=runtime_config.openai_image_delay_seconds,
        auto_refill_queue=runtime_config.auto_refill_queue,
        queue_refill=lambda manager, requested: refill_queue_from_research(
            manager,
            memory,
            requested,
            generation_mode=generation_mode,
        ),
        generation_mode=generation_mode,
    ).run(count)


def refill_queue_from_research(
    queue_manager: ProductionQueueManager,
    memory: MemoryManager,
    requested_count: int,
    generation_mode: str = GENERATION_MODE_AUTO,
) -> int:
    """Run Athena/Atlas and persist new READY jobs for continuous production."""
    config = ResearchPlannerConfig.from_file(RESEARCH_CONFIG_PATH)
    config = replace(config, daily_products=max(1, requested_count))
    research = AthenaMarketIntelligence(candidate_count=config.candidate_count).run()
    if not research.opportunities:
        print("Research candidates")
        print("0")
        print("Reason")
        print("Empty research dataset.")
        return 0
    provider_status = tuple(
        {
            "provider": status.provider,
            "priority": status.priority,
            "status": status.status,
            "detail": status.detail,
            "opportunities": status.opportunities,
        }
        for status in research.provider_statuses
    )
    candidates = build_brand_profile_portfolio_candidates(
        research.opportunities,
        target_count=max(config.daily_products * 4, 50),
        generation_mode=generation_mode,
    )
    if not candidates:
        print("Products selected")
        print("0")
        print("Reason")
        print("No candidates passed brand/product transformation.")
        return 0
    atlas = AtlasPortfolioManager(
        config=config,
        queue_manager=queue_manager,
        memory=memory,
    )
    plan = atlas.build_portfolio(candidates, provider_status=provider_status)
    atlas.save_report(plan)
    if not plan.selected:
        print("Products selected")
        print("0")
        print("Reason")
        for reason in plan.selection_failure_reasons or ("No valid products selected.",):
            print(reason)
        return 0
    return handoff_to_forge(
        plan,
        queue_manager,
        fallback_opportunities=candidates,
        target_new_jobs=config.daily_products,
        generation_mode=generation_mode,
    )


def _job_with_generation_strategy(
    job: ProductionJob,
    generation_mode: str,
) -> ProductionJob:
    """Return a job carrying a runtime generation-mode override."""
    mode = normalize_generation_mode(generation_mode)
    if mode == GENERATION_MODE_AUTO:
        return job
    decision = GenerationStrategyResolver.from_file(GENERATION_MIX_CONFIG_PATH).resolve(
        product_name=job.product_name,
        product_category=job.category,
        keywords=job.keywords,
        requested_mode=mode,
    )
    evidence = tuple(
        item
        for item in job.source_evidence
        if not str(item).strip().casefold().startswith(
            ("generation_mode=", "listing_family=", "generation_strategy_")
        )
    )
    return replace(
        job,
        category=_category_for_generation_mode(job.category, mode),
        source_evidence=evidence + decision.source_evidence(),
    )


def _category_for_generation_mode(current_category: str, generation_mode: str) -> str:
    """Return a compatible effective category for runtime mode overrides."""
    mode = normalize_generation_mode(generation_mode)
    if mode == GENERATION_MODE_DIGITAL_PAPER:
        return "digital print"
    if mode == GENERATION_MODE_WEDDING:
        return "wedding printable"
    if mode in {
        GENERATION_MODE_CHARACTERS,
        GENERATION_MODE_BOTANICAL,
        GENERATION_MODE_CLIPART,
    }:
        return "clipart"
    return current_category


def _first_ready_job_matching_generation_mode(
    jobs: tuple[ProductionJob, ...] | list[ProductionJob],
    generation_mode: str,
) -> ProductionJob | None:
    """Find the first READY job that belongs to an explicit generation mode."""
    mode = normalize_generation_mode(generation_mode)
    for job in jobs:
        if job.status != READY:
            continue
        if _job_matches_generation_mode(job, mode):
            return job
        print("READY Job Skipped For Mode")
        print(f"{job.id} - {job.product_name}")
        print("Requested Mode")
        print(mode)
        print("Reason")
        print("READY job does not match the requested generation mode.")
    return None


def _job_matches_generation_mode(job: ProductionJob, generation_mode: str) -> bool:
    """Return whether a READY job should run under the requested explicit mode."""
    mode = normalize_generation_mode(generation_mode)
    if mode == GENERATION_MODE_AUTO:
        return True
    evidence_mode = _generation_mode_from_source_evidence(job)
    if evidence_mode:
        return evidence_mode == mode
    context = (
        f"{job.product_name} {job.category} {' '.join(job.keywords)}"
        .casefold()
        .replace("_", " ")
        .replace("-", " ")
    )
    if mode == GENERATION_MODE_DIGITAL_PAPER:
        return any(term in context for term in ("digital paper", "paper pack", "scrapbook paper", "digital print"))
    if mode == GENERATION_MODE_WEDDING:
        return any(term in context for term in ("wedding", "bridal", "bride"))
    if mode == GENERATION_MODE_BOTANICAL:
        return any(term in context for term in ("botanical", "floral", "flower", "tree", "blossom"))
    if mode == GENERATION_MODE_CHARACTERS:
        return any(term in context for term in ("character", "characters", "kid", "kids", "children", "people", "fairy", "magical"))
    if mode == GENERATION_MODE_STORYBOOK:
        return any(term in context for term in ("storybook", "woodland", "nursery", "tea party", "picnic", "garden", "bakery", "rabbit", "fox", "mouse", "bear", "hedgehog"))
    if mode == GENERATION_MODE_CLIPART:
        return any(term in context for term in ("clipart", "clip art", "elements", "bundle"))
    return False


def _generation_mode_from_source_evidence(job: ProductionJob) -> str:
    """Read persisted generation_mode source evidence when present."""
    for item in job.source_evidence:
        raw = str(item).strip()
        if not raw.casefold().startswith("generation_mode="):
            continue
        try:
            return normalize_generation_mode(raw.split("=", maxsplit=1)[1])
        except ValueError:
            return ""
    return ""


def load_batch_runtime_config(path: Path) -> BatchRuntimeConfig:
    """Load batch pacing config from daily_factory.yaml."""
    values: dict[str, str] = {}
    if path.exists():
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or ":" not in line:
                continue
            key, value = line.split(":", maxsplit=1)
            values[key.strip()] = value.strip().strip("\"'")
    return BatchRuntimeConfig(
        openai_image_delay_seconds=float(
            values.get("openai_image_delay_seconds", "15")
        ),
        openai_rate_limit_max_retries=int(
            values.get("openai_rate_limit_max_retries", "3")
        ),
        openai_rate_limit_safety_seconds=float(
            values.get("openai_rate_limit_safety_seconds", "3")
        ),
        auto_refill_queue=_config_bool(values.get("auto_refill_queue", "true")),
    )


def _config_bool(value: str) -> bool:
    return value.strip().casefold() in {"1", "true", "yes", "on"}


def _build_batch_report(
    requested: int,
    reports: tuple[ProductionReport, ...],
    elapsed_time: float,
) -> BatchFactoryReport:
    draft_ids = tuple(
        draft_id
        for report in reports
        if (draft_id := _draft_id_from_report(report)) is not None
    )
    report_time_total = round(sum(report.time for report in reports), 3)
    resolved_elapsed_time = report_time_total if report_time_total > 0 else elapsed_time
    failures = tuple(
        {
            "job_id": report.job_id,
            "product": report.product,
            "failed_stage": report.failed_stage,
            "errors": list(report.errors),
        }
        for report in reports
        if not report.success
    )
    return BatchFactoryReport(
        requested=requested,
        attempted=len(reports),
        completed=sum(1 for report in reports if report.success),
        failed=sum(
            1
            for report in reports
            if not report.success and report.failed_stage != "product_capability"
        ),
        skipped=sum(
            1
            for report in reports
            if not report.success and report.failed_stage == "product_capability"
        ),
        drafts_created=sum(1 for report in reports if _draft_created_from_report(report)),
        draft_ids=draft_ids,
        images_generated=sum(report.images for report in reports),
        downloads_uploaded=sum(report.downloads for report in reports),
        elapsed_time=resolved_elapsed_time,
        failure_summary=failures,
        reports=reports,
    )


def _build_batch_report_from_returned_reports(
    requested: int,
    reports: tuple[ProductionReport, ...],
    completed: int,
    failed: int,
    skipped: int,
    draft_ids: tuple[str, ...],
    images_generated: int,
    downloads_uploaded: int,
    elapsed_time: float,
) -> BatchFactoryReport:
    """Build a batch report from counters read directly after execute()."""
    failures = tuple(
        {
            "job_id": report.job_id,
            "product": report.product,
            "failed_stage": report.failed_stage,
            "errors": list(report.errors),
        }
        for report in reports
        if not report.success
    )
    return BatchFactoryReport(
        requested=requested,
        attempted=len(reports),
        completed=completed,
        failed=failed,
        skipped=skipped,
        drafts_created=len(draft_ids),
        draft_ids=draft_ids,
        images_generated=images_generated,
        downloads_uploaded=downloads_uploaded,
        elapsed_time=elapsed_time,
        failure_summary=failures,
        reports=reports,
    )


def _report_generated_images_now(report: ProductionReport) -> bool:
    image_generation = report.metadata.get("image_generation")
    if not isinstance(image_generation, dict):
        return False
    if str(image_generation.get("status", "")).upper() != "SUCCESS":
        return False
    warnings = image_generation.get("warnings", ())
    if isinstance(warnings, list | tuple) and any(
        "reused existing" in str(warning).casefold() for warning in warnings
    ):
        return False
    return True


def print_batch_report(report: BatchFactoryReport) -> None:
    """Print the CLI batch summary."""
    print("BATCH FACTORY")
    print("")
    print("Requested")
    print(report.requested)
    print("")
    print("Completed")
    print(report.completed)
    print("")
    print("Failed")
    print(report.failed)
    print("")
    print("Skipped")
    print(report.skipped)
    print("")
    print("Drafts Created")
    print(report.drafts_created)
    print("")
    print("Draft IDs")
    if report.draft_ids:
        for draft_id in report.draft_ids:
            print(draft_id)
    else:
        print("None")
    print("")
    print("Images Generated")
    print(report.images_generated)
    print("")
    print("Downloads Uploaded")
    print(report.downloads_uploaded)
    print("")
    print("Elapsed Time")
    print(f"{_format_elapsed_time(report.elapsed_time)} seconds")
    print("")
    print("Failure Summary")
    if not report.failure_summary:
        print("None")
    else:
        for failure in report.failure_summary:
            print(
                f"{failure['product']} - "
                f"{failure.get('failed_stage') or 'unknown'}"
            )
            for error in failure.get("errors", ()):
                print(f"  {error}")


def print_queue_selection_diagnostics(queue_manager: ProductionQueueManager) -> None:
    """Print the queue state used by Batch Factory before selecting work."""
    jobs = queue_manager.list_jobs()
    ready_jobs = tuple(job for job in jobs if job.status == "READY")
    print("")
    print("Loaded queue")
    print(queue_manager.queue_path.resolve())
    print("")
    print("Queue file path")
    print(queue_manager.queue_path)
    print("")
    print("Absolute path")
    print(queue_manager.queue_path.resolve())
    print("")
    print("Jobs loaded")
    print(len(jobs))
    print("")
    print("READY jobs")
    print(len(ready_jobs))
    print("")
    print("Candidate IDs")
    if ready_jobs:
        for job in ready_jobs:
            print(f"{job.id} - {job.product_name}")
    else:
        print("None")
    print("")
    print("Non-READY jobs")
    for job in jobs:
        if job.status != "READY":
            print(f"{job.id} - {job.product_name} - {job.status}")


def print_report_diagnostics(report: ProductionReport) -> None:
    """Print safe per-job report diagnostics without secrets."""
    draft_id = _draft_id_from_report(report)
    print("BATCH JOB REPORT")
    print("Report Type")
    print(type(report).__name__)
    print("Report Draft ID")
    print(draft_id if draft_id else "NONE")
    print("Report Time")
    print(report.time)
    print("Report Success")
    print("true" if report.success else "false")
    print("")


def _format_elapsed_time(value: float) -> str:
    """Format elapsed seconds without hiding short nonzero runs."""
    if value == 0:
        return "0"
    return f"{value:.3f}".rstrip("0").rstrip(".")


def _draft_id_from_report(report: ProductionReport) -> str | None:
    """Return the Etsy draft id represented by one production report."""
    if report.draft_id and report.draft_id.strip():
        return report.draft_id.strip()

    etsy_draft = report.metadata.get("etsy_draft")
    if not isinstance(etsy_draft, dict):
        return None

    listing_id = etsy_draft.get("etsy_listing_id")
    if isinstance(listing_id, str) and listing_id.strip():
        return listing_id.strip()

    status = etsy_draft.get("status")
    if isinstance(status, str) and status.strip().upper() == "DRAFT_CREATED":
        metadata = etsy_draft.get("metadata")
        if isinstance(metadata, dict):
            response = metadata.get("response")
            if isinstance(response, dict):
                response_listing_id = response.get("listing_id")
                if response_listing_id is not None:
                    return str(response_listing_id)
    return None


def _draft_created_from_report(report: ProductionReport) -> bool:
    """Return whether one production report created an Etsy draft."""
    if _draft_id_from_report(report) is not None:
        return True
    etsy_draft = report.metadata.get("etsy_draft")
    if not isinstance(etsy_draft, dict):
        return False
    status = etsy_draft.get("status")
    return isinstance(status, str) and status.strip().upper() == "DRAFT_CREATED"


if __name__ == "__main__":
    main()
