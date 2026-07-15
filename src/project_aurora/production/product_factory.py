"""Orchestrate one Aurora production queue job end to end."""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import fields, is_dataclass
from datetime import datetime
import json
from pathlib import Path
import re
from time import perf_counter
from types import SimpleNamespace
from typing import Any, Protocol

from project_aurora.integrations.etsy.etsy_config import EtsyConfig
from project_aurora.integrations.etsy.etsy_token_manager import EtsyTokenManager
from project_aurora.listing.listing_package import (
    READY_FOR_ETSY_DRAFT,
    ListingPackage,
)
from project_aurora.planning.production_queue_manager import (
    ProductionJob,
    ProductionQueueManager,
)
from project_aurora.production.production_report import ProductionReport
from project_aurora.prompt_factory.prompt_composer import PromptComposer
from project_aurora.seo.seo_engine import SEOEngine
from project_aurora.storage.memory_manager import MemoryManager


REPORT_COLLECTION = "production_reports"
PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OPENAI_CONFIG_PATH = PROJECT_ROOT / "config" / "openai.yaml"
DEFAULT_JOBS_DIR = PROJECT_ROOT / "data" / "aurora" / "jobs"
DEFAULT_LOCAL_CREDENTIAL_PATH = PROJECT_ROOT / "config" / "aurora.local.env"
DEFAULT_ETSY_CONFIG_PATH = PROJECT_ROOT / "config" / "etsy.yaml"


class ProductFactoryStageRunner(Protocol):
    """Stage boundary used by ProductFactory orchestration."""

    def compose_prompts(self, job: ProductionJob) -> Any:
        """Compose prompts for one job."""

    def generate_images(self, job: ProductionJob) -> Any:
        """Generate source images."""

    def run_image_qa(self, job: ProductionJob) -> Any:
        """Run image QA."""

    def export_commercial_images(self, job: ProductionJob) -> Any:
        """Export final commercial image files."""

    def generate_seo(self, job: ProductionJob) -> Any:
        """Generate SEO package."""

    def create_etsy_draft(self, job: ProductionJob, seo_package: Any) -> Any:
        """Create Etsy draft."""

    def upload_listing_images(self, job: ProductionJob) -> Any:
        """Upload listing images."""

    def upload_customer_downloads(self, job: ProductionJob, listing_id: str | None) -> Any:
        """Upload customer download files."""


@dataclass(frozen=True, slots=True)
class ProductFactoryPaths:
    """Runtime paths used by the Product Factory default runner."""

    jobs_dir: Path = DEFAULT_JOBS_DIR
    generated_images_dir: Path | None = None
    final_images_dir: Path | None = None
    digital_downloads_dir: Path | None = None

    def for_job(self, job: ProductionJob) -> "ProductFactoryJobPaths":
        """Return isolated working directories for one production job."""
        job_root = self.jobs_dir / _safe_job_folder_name(job)
        return ProductFactoryJobPaths(
            job_root=job_root,
            generated_images_dir=self.generated_images_dir
            or job_root / "generated_images",
            final_images_dir=self.final_images_dir
            or job_root / "final_product_images",
            digital_downloads_dir=self.digital_downloads_dir
            or job_root / "digital_downloads",
        )


@dataclass(frozen=True, slots=True)
class ProductFactoryJobPaths:
    """Concrete isolated filesystem paths for one production job."""

    job_root: Path
    generated_images_dir: Path
    final_images_dir: Path
    digital_downloads_dir: Path

    def to_dict(self) -> dict[str, str]:
        """Return JSON-safe path values for production reports."""
        return {
            "job_root": str(self.job_root),
            "generated_images_dir": str(self.generated_images_dir),
            "final_product_images_dir": str(self.final_images_dir),
            "digital_downloads_dir": str(self.digital_downloads_dir),
        }


class DefaultProductFactoryStageRunner:
    """Default stage runner that reuses Aurora's existing services."""

    def __init__(
        self,
        memory: MemoryManager,
        etsy_config: EtsyConfig,
        paths: ProductFactoryPaths | None = None,
        image_config: Any | None = None,
        image_config_path: Path = DEFAULT_OPENAI_CONFIG_PATH,
    ) -> None:
        self._memory = memory
        self._etsy_config = etsy_config
        self._paths = paths or ProductFactoryPaths()
        if image_config is None:
            from project_aurora.image_generation.provider_registry import (
                ImageProviderConfig,
            )

            image_config = ImageProviderConfig.from_file(image_config_path)
        self._image_config = image_config

    def job_paths(self, job: ProductionJob) -> ProductFactoryJobPaths:
        """Return isolated runtime paths for the current production job."""
        return self._paths.for_job(job)

    def compose_prompts(self, job: ProductionJob) -> Any:
        """Compose and save prompt recipe/package-compatible prompt data."""
        recipe = PromptComposer(memory=self._memory).compose(
            subject=job.product_name,
            character=f"{job.product_name} cohesive commercial clipart set",
            style_name=_composer_style(job.style),
            palette_name=_palette_for_job(job),
            composition_name="Centered",
            recipe_id=job.id,
        )
        self._memory.save_prompt_package(
            {
                "product_name": job.product_name,
                "collection": job.product_name,
                "theme": job.seasonal_theme,
                "style": job.style,
                "target_platforms": ["Etsy"],
                "image_prompt": recipe.final_prompt,
                "negative_prompt": recipe.negative_prompt,
                "keywords": job.keywords,
                "notes": "Generated by Product Factory.",
            },
            package_id=job.id,
        )
        return recipe

    def generate_images(self, job: ProductionJob) -> Any:
        """Generate four OpenAI images through the image engine."""
        job_paths = self.job_paths(job)
        reused = self._reuse_completed_generated_images(job, job_paths)
        if reused is not None:
            return reused
        self._prepare_generated_images_dir(job_paths)

        from project_aurora.image_generation.image_generation_engine import (
            ImageGenerationEngine,
        )

        return ImageGenerationEngine(
            memory=self._memory,
            output_dir=job_paths.generated_images_dir,
            provider_config=self._image_config,
        ).run(
            prompt_package_id=job.id,
            provider=self._image_config.provider,
            image_type="product_asset",
            width=1024,
            height=1024,
            dpi=300,
            size=self._image_config.size,
            quality=self._image_config.quality,
            background=self._image_config.background,
            output_format=self._image_config.output_format,
            number_of_images=self._image_config.number_of_images,
        )

    def run_image_qa(self, job: ProductionJob) -> Any:
        """Run deterministic image QA."""
        from project_aurora.image_qa.qa_engine import ImageQAEngine

        return ImageQAEngine(memory=self._memory).run()

    def export_commercial_images(self, job: ProductionJob) -> Any:
        """Export final commercial PNGs."""
        job_paths = self.job_paths(job)
        reused = self._reuse_completed_final_images(job_paths)
        if reused is not None:
            return reused
        from project_aurora.image_generation.commercial_image_exporter import (
            CommercialImageExporter,
        )

        return CommercialImageExporter(
            source_dir=job_paths.generated_images_dir,
            output_dir=job_paths.final_images_dir,
        ).export()

    def generate_seo(self, job: ProductionJob) -> Any:
        """Generate and save SEO package."""
        job_paths = self.job_paths(job)
        seo_dir = job_paths.job_root / "seo"
        seo_path = seo_dir / "seo_package.json"
        if seo_path.exists():
            package = _load_job_seo_package(seo_path)
            _validate_job_seo_package(package, job, previous_tags=_previous_product_tags(self._memory, job.id))
            if not getattr(self._etsy_config, "is_mock_mode", True):
                _print_seo_diagnostics(job, package)
            self._memory.save_seo_package(package, package_id=job.id)
            return package
        package = SEOEngine(memory=self._memory).run(
            {
                "job_id": job.id,
                "product_name": job.product_name,
                "product_type": job.category,
                "target_buyer": "digital printable buyers",
            },
            package_id=job.id,
        )
        _validate_job_seo_package(package, job, previous_tags=_previous_product_tags(self._memory, job.id))
        seo_dir.mkdir(parents=True, exist_ok=True)
        seo_path.write_text(
            json.dumps(_seo_package_to_record(package), indent=2, sort_keys=True),
            encoding="utf-8",
        )
        if not getattr(self._etsy_config, "is_mock_mode", True):
            _print_seo_diagnostics(job, package)
        return package

    def create_etsy_draft(self, job: ProductionJob, seo_package: Any) -> Any:
        """Create an Etsy draft through the existing draft service."""
        from project_aurora.integrations.etsy.etsy_draft_service import (
            EtsyDraftService,
        )

        self._refresh_etsy_config()
        job_paths = self.job_paths(job)
        _validate_job_seo_package(
            seo_package,
            job,
            previous_tags=_previous_product_tags(self._memory, job.id),
        )
        final_files = tuple(
            str(path)
            for path in sorted(
                job_paths.final_images_dir.glob("*.png"),
                key=lambda item: item.name,
            )
        )
        listing_package = ListingPackage(
            product_name=job.product_name,
            collection_name=job.product_name,
            listing_status=READY_FOR_ETSY_DRAFT,
            seo_package_id=job.id,
            prompt_package_id=job.id,
            approved_mockup_files=final_files,
            approved_generated_image_files=final_files,
            is_digital_download=True,
            price=1.99,
        )
        return EtsyDraftService(
            config=self._etsy_config,
            memory=self._memory,
        ).create_draft(
            listing_package=listing_package,
            seo_package=seo_package,
        )

    def upload_listing_images(self, job: ProductionJob) -> Any:
        """Upload final PNGs as Etsy listing images."""
        from project_aurora.integrations.etsy.etsy_image_upload_service import (
            EtsyImageUploadService,
        )

        self._refresh_etsy_config()
        return EtsyImageUploadService(
            config=self._etsy_config,
            memory=self._memory,
            images_dir=self.job_paths(job).final_images_dir,
        ).upload_latest_draft_images()

    def upload_customer_downloads(self, job: ProductionJob, listing_id: str | None) -> Any:
        """Upload final PNGs as Etsy customer downloads."""
        from project_aurora.integrations.etsy.etsy_digital_file_service import (
            EtsyDigitalFileService,
        )

        self._refresh_etsy_config()
        return EtsyDigitalFileService(
            config=self._etsy_config,
            memory=self._memory,
        ).upload_digital_files(
            listing_id=listing_id,
            final_images_dir=self.job_paths(job).final_images_dir,
        )

    def _refresh_etsy_config(self) -> None:
        is_mock_mode = getattr(self._etsy_config, "is_mock_mode", True)
        if is_mock_mode:
            return
        result = EtsyTokenManager(DEFAULT_LOCAL_CREDENTIAL_PATH).refresh_if_needed()
        if result.refreshed:
            self._etsy_config = EtsyConfig.from_environment(DEFAULT_ETSY_CONFIG_PATH)

    def _prepare_generated_images_dir(self, job_paths: ProductFactoryJobPaths) -> None:
        job_paths.generated_images_dir.mkdir(parents=True, exist_ok=True)
        existing_pngs = tuple(job_paths.generated_images_dir.glob("*.png"))
        if existing_pngs:
            raise RuntimeError(
                "Generated images directory must be empty before generation; "
                f"found {len(existing_pngs)} PNG files in "
                f"{job_paths.generated_images_dir}."
            )

    def _reuse_completed_generated_images(
        self,
        job: ProductionJob,
        job_paths: ProductFactoryJobPaths,
    ) -> Any | None:
        from project_aurora.image_generation.image_inspector import inspect_png
        from project_aurora.image_generation.image_result import ImageResult

        if not job_paths.generated_images_dir.exists():
            return None
        pngs = tuple(
            sorted(job_paths.generated_images_dir.glob("*.png"), key=lambda path: path.name)
        )
        if not pngs:
            return None
        valid_pngs = tuple(path for path in pngs if inspect_png(path).is_valid)
        expected = int(self._image_config.number_of_images)
        if len(pngs) == expected and len(valid_pngs) == expected:
            result = ImageResult(
                status="SUCCESS",
                provider="OpenAI GPT Image",
                generated_files=tuple(str(path) for path in valid_pngs),
                generation_time=0.0,
                cost_estimate=0.0,
                warnings=("Reused existing valid job generated images.",),
                metadata={
                    "reused": True,
                    "job_id": job.id,
                    "job_paths": job_paths.to_dict(),
                },
                image_paths=tuple(str(path) for path in valid_pngs),
                prompt_version=self._image_config.prompt_version,
            )
            self._memory.save_image_result(result)
            return result
        raise RuntimeError(
            "Generated images directory contains incomplete or unexpected PNG files; "
            f"expected exactly {expected} valid PNGs, found {len(valid_pngs)} valid "
            f"out of {len(pngs)} total in {job_paths.generated_images_dir}."
        )

    @staticmethod
    def _reuse_completed_final_images(job_paths: ProductFactoryJobPaths) -> Any | None:
        from project_aurora.image_generation.commercial_image_exporter import (
            COMMERCIAL_IMAGE_COUNT,
            CommercialImageExportResult,
            validate_commercial_png,
        )
        from project_aurora.image_generation.image_inspector import inspect_png

        if not job_paths.final_images_dir.exists():
            return None
        pngs = tuple(
            sorted(job_paths.final_images_dir.glob("*.png"), key=lambda path: path.name)
        )
        if not pngs:
            return None
        valid_pngs = tuple(path for path in pngs if not validate_commercial_png(path))
        if len(pngs) == COMMERCIAL_IMAGE_COUNT and len(valid_pngs) == COMMERCIAL_IMAGE_COUNT:
            return CommercialImageExportResult(
                status="SUCCESS",
                exported_files=tuple(str(path) for path in valid_pngs),
                warnings=("Reused existing valid final commercial images.",),
                inspections=tuple(inspect_png(path) for path in valid_pngs),
            )
        raise RuntimeError(
            "Final product images directory contains incomplete or unexpected PNG files; "
            f"expected exactly {COMMERCIAL_IMAGE_COUNT} valid PNGs, found "
            f"{len(valid_pngs)} valid out of {len(pngs)} total in "
            f"{job_paths.final_images_dir}."
        )


class DryRunProductFactoryStageRunner:
    """No-network Product Factory stage runner for verification."""

    def compose_prompts(self, job: ProductionJob) -> Any:
        """Simulate prompt composition."""
        return SimpleNamespace(status="SUCCESS", final_prompt=f"Dry run prompt for {job.product_name}.")

    def generate_images(self, job: ProductionJob) -> Any:
        """Simulate OpenAI image generation without calling OpenAI."""
        return SimpleNamespace(
            status="SUCCESS",
            provider="DRY_RUN",
            generated_files=(
                "dry_run_image_01.png",
                "dry_run_image_02.png",
                "dry_run_image_03.png",
                "dry_run_image_04.png",
            ),
            warnings=(),
            errors=(),
        )

    def run_image_qa(self, job: ProductionJob) -> Any:
        """Simulate QA approval."""
        return tuple(
            SimpleNamespace(status="PASS", asset_name=f"dry_run_image_{index:02d}.png")
            for index in range(1, 5)
        )

    def export_commercial_images(self, job: ProductionJob) -> Any:
        """Simulate commercial export."""
        return SimpleNamespace(
            status="SUCCESS",
            exported_files=(
                "dry_run_final_01.png",
                "dry_run_final_02.png",
                "dry_run_final_03.png",
                "dry_run_final_04.png",
            ),
            warnings=(),
            errors=(),
        )

    def generate_seo(self, job: ProductionJob) -> Any:
        """Simulate SEO generation."""
        return SimpleNamespace(status="SUCCESS", title=f"{job.product_name} SEO", warnings=())

    def create_etsy_draft(self, job: ProductionJob, seo_package: Any) -> Any:
        """Skip Etsy draft creation in dry run."""
        return SimpleNamespace(
            status="READY_FOR_ETSY_DRAFT",
            etsy_listing_id=None,
            warnings=("Dry run: Etsy draft was not created.",),
            errors=(),
        )

    def upload_listing_images(self, job: ProductionJob) -> Any:
        """Skip Etsy listing image upload in dry run."""
        return SimpleNamespace(
            status="SUCCESS",
            images_uploaded=4,
            failed=0,
            warnings=("Dry run: listing images were not uploaded.",),
            errors=(),
        )

    def upload_customer_downloads(self, job: ProductionJob, listing_id: str | None) -> Any:
        """Skip Etsy digital file upload in dry run."""
        return SimpleNamespace(
            status="SUCCESS",
            files_uploaded=4,
            failed=0,
            warnings=("Dry run: customer downloads were not uploaded.",),
            errors=(),
        )


class ProductFactory:
    """Execute exactly one production job from the planning queue."""

    def __init__(
        self,
        queue_manager: ProductionQueueManager,
        memory: MemoryManager,
        stage_runner: ProductFactoryStageRunner,
        dry_run: bool = False,
        save_report: bool | None = None,
    ) -> None:
        self._queue_manager = queue_manager
        self._memory = memory
        self._stage_runner = stage_runner
        self._dry_run = dry_run
        self._save_report_enabled = (not dry_run) if save_report is None else save_report

    def execute(self, job: ProductionJob) -> ProductionReport:
        """Execute one ready production job and return a saved report."""
        started_at = perf_counter()
        draft_id: str | None = None
        images = 0
        downloads = 0
        warnings: list[str] = []
        metadata: dict[str, Any] = {}
        job_paths = _job_paths_from_runner(self._stage_runner, job)

        if not self._dry_run:
            self._queue_manager.mark_in_progress(job.id)
        stages = (
            ("prompt_composition", lambda: self._stage_runner.compose_prompts(job)),
            ("image_generation", lambda: self._stage_runner.generate_images(job)),
            ("image_qa", lambda: self._stage_runner.run_image_qa(job)),
            (
                "commercial_export",
                lambda: self._stage_runner.export_commercial_images(job),
            ),
            ("seo_generation", lambda: self._stage_runner.generate_seo(job)),
            (
                "etsy_draft",
                lambda: self._stage_runner.create_etsy_draft(
                    job,
                    metadata["seo_package"],
                ),
            ),
            ("listing_image_upload", lambda: self._stage_runner.upload_listing_images(job)),
            (
                "customer_download_upload",
                lambda: self._stage_runner.upload_customer_downloads(job, draft_id),
            ),
        )

        try:
            for stage_name, stage in stages:
                try:
                    result = stage()
                except Exception as error:
                    raise ProductFactoryStageError(
                        stage_name,
                        (str(error),),
                    ) from error
                metadata[stage_name] = _summarize_result(result)
                warnings.extend(_warnings_from(result))
                if stage_name == "seo_generation":
                    metadata["seo_package"] = result
                elif stage_name == "etsy_draft":
                    draft_id = _draft_id_from(result)
                elif stage_name == "commercial_export":
                    images = len(getattr(result, "exported_files", ()))
                elif stage_name == "listing_image_upload":
                    images = max(images, int(getattr(result, "images_uploaded", 0)))
                elif stage_name == "customer_download_upload":
                    downloads = int(getattr(result, "files_uploaded", 0))
                _raise_if_failed(stage_name, result)

            if not self._dry_run:
                self._queue_manager.mark_completed(job.id)
            report = ProductionReport(
                job_id=job.id,
                product=job.product_name,
                style=job.style,
                draft_id=draft_id,
                images=images,
                downloads=downloads,
                time=round(perf_counter() - started_at, 3),
                success=True,
                warnings=tuple(warnings),
                job_paths=job_paths,
                metadata=_report_metadata(metadata),
            )
        except Exception as error:
            if not self._dry_run:
                self._queue_manager.mark_failed(job.id)
            failed_stage = _failed_stage_from(error)
            draft_id = draft_id or _draft_id_from_metadata(metadata)
            report = ProductionReport(
                job_id=job.id,
                product=job.product_name,
                style=job.style,
                draft_id=draft_id,
                images=images,
                downloads=downloads,
                time=round(perf_counter() - started_at, 3),
                success=False,
                failed_stage=failed_stage,
                warnings=tuple(warnings),
                errors=(str(error),),
                job_paths=job_paths,
                metadata=_report_metadata(metadata),
            )

        if self._save_report_enabled:
            self._save_report(report)
        return report

    def _save_report(self, report: ProductionReport) -> None:
        self._memory.save_record(
            REPORT_COLLECTION,
            "latest",
            report.to_dict(),
        )
        self._memory.save_record(
            REPORT_COLLECTION,
            report.job_id,
            report.to_dict(),
        )


class ProductFactoryStageError(RuntimeError):
    """Raised when a product factory stage fails."""

    def __init__(self, stage: str, errors: tuple[str, ...]) -> None:
        self.stage = stage
        message = "; ".join(errors) if errors else f"{stage} failed."
        super().__init__(message)


def _raise_if_failed(stage_name: str, result: Any) -> None:
    status = getattr(result, "status", None)
    if isinstance(status, str) and status.strip().upper() not in {
        "SUCCESS",
        "PASS",
        "WARNING",
        "DRAFT_CREATED",
        "READY_FOR_ETSY_DRAFT",
    }:
        errors = tuple(str(error) for error in getattr(result, "errors", ()) or ())
        raise ProductFactoryStageError(stage_name, errors)
    if isinstance(result, tuple) and result:
        bad = [
            item
            for item in result
            if str(getattr(item, "status", "")).upper() not in {"PASS", "WARNING"}
        ]
        if bad:
            raise ProductFactoryStageError(
                stage_name,
                tuple(
                    f"{getattr(item, 'asset_name', 'asset')} failed QA"
                    for item in bad
                ),
            )


def _warnings_from(result: Any) -> tuple[str, ...]:
    warnings = getattr(result, "warnings", ())
    return tuple(str(warning) for warning in warnings or ())


def _draft_id_from(result: Any) -> str | None:
    listing_id = getattr(result, "etsy_listing_id", None)
    if isinstance(listing_id, str) and listing_id.strip():
        return listing_id.strip()
    return None


def _draft_id_from_metadata(metadata: dict[str, Any]) -> str | None:
    draft = metadata.get("etsy_draft")
    if isinstance(draft, dict):
        value = draft.get("etsy_listing_id")
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _failed_stage_from(error: Exception) -> str:
    if isinstance(error, ProductFactoryStageError):
        return error.stage
    return "unexpected_error"


def _summarize_result(result: Any) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for name in (
        "status",
        "provider",
        "etsy_listing_id",
        "job_id",
        "product_name",
        "title",
        "tags",
        "images_uploaded",
        "files_uploaded",
        "failed",
        "errors",
        "warnings",
    ):
        if hasattr(result, name):
            value = getattr(result, name)
            summary[name] = list(value) if isinstance(value, tuple) else value
    if isinstance(result, tuple):
        summary["count"] = len(result)
        summary["statuses"] = [getattr(item, "status", None) for item in result]
    return summary


def _report_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in metadata.items()
        if key != "seo_package"
    }


def _job_paths_from_runner(
    runner: ProductFactoryStageRunner,
    job: ProductionJob,
) -> dict[str, str]:
    job_paths_method = getattr(runner, "job_paths", None)
    if not callable(job_paths_method):
        return {}
    job_paths = job_paths_method(job)
    to_dict = getattr(job_paths, "to_dict", None)
    if callable(to_dict):
        return dict(to_dict())
    return {}


def _safe_job_folder_name(job: ProductionJob) -> str:
    job_id = _slug_part(job.id) or "job"
    product = _slug_part(job.product_name) or "product"
    return f"{job_id}_{product}"


def _slug_part(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", value.casefold()).strip("_")
    return slug[:80]


def _composer_style(style: str) -> str:
    supported = {
        "storybook watercolor": "Storybook Watercolor",
        "vintage botanical": "Vintage Botanical",
        "soft cottagecore": "Soft Cottagecore",
        "cottagecore watercolor": "Soft Cottagecore",
        "soft nursery": "Pastel Nursery",
        "vintage christmas": "Vintage Christmas",
        "fairy garden": "Storybook Watercolor",
        "woodland friends": "Storybook Watercolor",
        "strawberry summer": "Storybook Watercolor",
    }
    return supported.get(style.casefold(), "Storybook Watercolor")


def _palette_for_job(job: ProductionJob) -> str:
    if "strawberry" in job.product_name.casefold():
        return "Strawberry Summer"
    return "Strawberry Summer"


def _seo_package_to_record(package: Any) -> dict[str, Any]:
    if is_dataclass(package) and not isinstance(package, type):
        record: dict[str, Any] = {}
        for field in fields(package):
            value = getattr(package, field.name)
            if isinstance(value, datetime):
                record[field.name] = value.isoformat()
            elif isinstance(value, tuple):
                record[field.name] = list(value)
            else:
                record[field.name] = value
        return record
    raise TypeError("Expected dataclass SEO package.")


def _load_job_seo_package(path: Path) -> Any:
    from project_aurora.seo.seo_package import SEOPackage

    data = json.loads(path.read_text(encoding="utf-8"))
    return SEOPackage(
        job_id=str(data.get("job_id", "")),
        product_name=str(data["product_name"]),
        product_type=str(data["product_type"]),
        target_buyer=str(data["target_buyer"]),
        title=str(data["title"]),
        tags=tuple(str(item) for item in data["tags"]),
        description=str(data["description"]),
        keywords=tuple(str(item) for item in data["keywords"]),
        buyer_use_case=str(data["buyer_use_case"]),
        product_positioning=str(data["product_positioning"]),
        seo_score=int(data["seo_score"]),
        warnings=tuple(str(item) for item in data.get("warnings", ())),
        created_at=datetime.fromisoformat(str(data["created_at"])),
        generated_at=datetime.fromisoformat(str(data.get("generated_at") or data["created_at"])),
    )


def _validate_job_seo_package(
    package: Any,
    job: ProductionJob,
    previous_tags: tuple[str, ...] = (),
) -> None:
    job_id = getattr(package, "job_id", "")
    product_name = getattr(package, "product_name", "")
    tags = tuple(str(tag).strip() for tag in getattr(package, "tags", ()))
    if job_id != job.id:
        raise RuntimeError("SEO package job_id does not match ProductionJob id.")
    if product_name != job.product_name:
        raise RuntimeError("SEO package product_name does not match ProductionJob.")
    if len(tags) != 13:
        raise RuntimeError("SEO package must include exactly 13 tags.")
    if any(not tag for tag in tags):
        raise RuntimeError("SEO package contains empty tags.")
    if len(set(tag.casefold() for tag in tags)) != len(tags):
        raise RuntimeError("SEO package contains duplicate tags.")
    if previous_tags and tuple(tag.casefold() for tag in tags) == tuple(
        tag.casefold() for tag in previous_tags
    ):
        raise RuntimeError("SEO tags are identical to the immediately previous product.")
    relevant_tokens = {
        token
        for token in re.split(r"[^a-z0-9]+", f"{job.product_name} {job.category}".casefold())
        if len(token) > 2
    }
    irrelevant = [
        tag
        for tag in tags
        if not (set(tag.casefold().split()) & relevant_tokens)
        and tag.casefold() not in _GENERIC_RELEVANT_TAGS
    ]
    if len(irrelevant) > 5:
        raise RuntimeError(
            "SEO package tags are not relevant to the current product: "
            + ", ".join(irrelevant)
        )


_GENERIC_RELEVANT_TAGS = {
    "etsy download",
    "instant download",
    "digital download",
    "commercial use",
    "craft supply",
    "craft download",
    "png clipart",
    "digital clipart",
    "clipart bundle",
    "printable graphics",
    "wall art",
    "printable art",
    "digital print",
    "home decor",
    "party printable",
    "printable bundle",
    "party decor",
    "party download",
    "digital paper",
    "scrapbook paper",
    "sticker sheet",
    "planner stickers",
}


def _previous_product_tags(memory: MemoryManager, current_job_id: str) -> tuple[str, ...]:
    try:
        latest = memory.load_record(REPORT_COLLECTION, "latest")
    except FileNotFoundError:
        return ()
    if latest.get("job_id") == current_job_id:
        return ()
    metadata = latest.get("metadata")
    if not isinstance(metadata, dict):
        return ()
    seo = metadata.get("seo_generation")
    if isinstance(seo, dict):
        tags = seo.get("tags")
        if isinstance(tags, list):
            return tuple(str(tag) for tag in tags)
    return ()


def _print_seo_diagnostics(job: ProductionJob, package: Any) -> None:
    print("SEO JOB")
    print(job.product_name)
    print("")
    print("SEO TAGS")
    for tag in getattr(package, "tags", ()):
        print(tag)
