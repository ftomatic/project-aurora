"""Orchestrate one Aurora production queue job end to end."""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import fields, is_dataclass
from dataclasses import replace
from datetime import datetime
import json
from pathlib import Path
import re
from time import perf_counter
from types import SimpleNamespace
from typing import Any, Protocol

from project_aurora.integrations.etsy.etsy_config import EtsyConfig
from project_aurora.integrations.etsy.etsy_token_manager import EtsyTokenManager
from project_aurora.brand_profile import load_brand_profile, score_brand_fit
from project_aurora.listing.listing_package import (
    READY_FOR_ETSY_DRAFT,
    ListingPackage,
)
from project_aurora.planning.production_queue_manager import (
    ProductionJob,
    ProductionQueueManager,
)
from project_aurora.production.watercolor_scope import resolve_watercolor_scope
from project_aurora.production.product_image_family import (
    CLIPART,
    STORYBOOK_SCENE,
    resolve_product_image_family,
)
from project_aurora.production.production_report import ProductionReport
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
    storybook_scenes_dir: Path | None = None
    listing_images_dir: Path | None = None
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
            storybook_scenes_dir=self.storybook_scenes_dir
            or job_root / "storybook_scenes",
            listing_images_dir=self.listing_images_dir
            or job_root / "listing_images",
            digital_downloads_dir=self.digital_downloads_dir
            or job_root / "digital_downloads",
        )


@dataclass(frozen=True, slots=True)
class ProductFactoryJobPaths:
    """Concrete isolated filesystem paths for one production job."""

    job_root: Path
    generated_images_dir: Path
    final_images_dir: Path
    storybook_scenes_dir: Path
    listing_images_dir: Path
    digital_downloads_dir: Path

    def to_dict(self) -> dict[str, str]:
        """Return JSON-safe path values for production reports."""
        return {
            "job_root": str(self.job_root),
            "generated_images_dir": str(self.generated_images_dir),
            "final_product_images_dir": str(self.final_images_dir),
            "storybook_scenes_dir": str(self.storybook_scenes_dir),
            "listing_images_dir": str(self.listing_images_dir),
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
        """Compose and save a simple customer-clipart prompt."""
        from project_aurora.muse.muse_engine import MuseEngine

        scope = resolve_watercolor_scope(job.product_name, job.category, job.style)
        if not scope.supported:
            raise ProductFactoryStageError("product_capability", (scope.reason,))
        brand_score = score_brand_fit(job.product_name, job.category, job.style)
        if not brand_score.accepted:
            raise ProductFactoryStageError("product_capability", (brand_score.reason,))
        art_direction = MuseEngine(memory=self._memory).select_style(
            product=job.product_name,
            audience=job.target_customer,
            season=job.seasonal_theme,
            competition=job.estimated_competition,
            current_portfolio=(),
            historical_products=(),
            product_type=job.category,
        )
        print("STYLE REVIEW")
        print("Selected Style")
        print(art_direction.recommended_style)
        print("Reason")
        print(art_direction.reason)
        print("Trend Score")
        print(art_direction.trend_score)
        print("Portfolio Diversity")
        print(art_direction.portfolio_diversity)
        print("Confidence")
        print(f"{art_direction.confidence}%")
        if art_direction.status == "REJECTED":
            raise RuntimeError("Muse rejected style below confidence threshold.")

        image_family = resolve_product_image_family(
            job.product_name,
            scope.canonical_product_type,
            job.category,
        )
        final_prompt = _product_family_prompt(
            job,
            scope.canonical_product_type,
            image_family.family,
        )
        negative_prompt = _product_family_negative_prompt(image_family.family)
        self._memory.save_prompt_package(
            {
                "product_name": job.product_name,
                "collection": job.product_name,
                "theme": job.seasonal_theme,
                "product_type": scope.canonical_product_type,
                "product_family": image_family.family,
                "transparent_background": image_family.transparent_background,
                "openai_background": image_family.openai_background,
                "product_family_requirements": image_family.prompt_requirements,
                "style": art_direction.recommended_style,
                "palette": art_direction.palette,
                "rendering_family": art_direction.rendering_family,
                "rendering_method": art_direction.rendering_method,
                "composition": art_direction.composition,
                "background_treatment": art_direction.background_treatment,
                "lighting": art_direction.lighting,
                "texture": art_direction.texture,
                "typography_direction": art_direction.typography_direction,
                "mood": art_direction.mood,
                "target_platforms": ["Etsy"],
                "image_prompt": final_prompt,
                "negative_prompt": negative_prompt,
                "keywords": job.keywords,
                "art_direction": {
                    "recommended_style": art_direction.recommended_style,
                    "confidence": art_direction.confidence,
                    "reason": art_direction.reason,
                    "commercial_rationale": art_direction.commercial_rationale,
                    "trend_score": art_direction.trend_score,
                    "portfolio_diversity": art_direction.portfolio_diversity,
                    "rendering_family": art_direction.rendering_family,
                    "background_treatment": art_direction.background_treatment,
                    "negative_style_constraints": list(art_direction.negative_style_constraints),
                    "proven_winner_evidence_used": art_direction.proven_winner_evidence_used,
                    "diversity_penalty_applied": art_direction.diversity_penalty_applied,
                },
                "notes": "Generated by Product Factory.",
                "brand_score": brand_score.score,
                "brand_matched_terms": brand_score.matched_terms,
            },
            package_id=job.id,
        )
        return SimpleNamespace(status="SUCCESS", final_prompt=final_prompt)

    def generate_images(self, job: ProductionJob) -> Any:
        """Generate four OpenAI images through the image engine."""
        capability = _resolve_product_capability(job)
        if not capability.supported:
            raise ProductFactoryStageError("product_capability", (capability.reason,))
        job_paths = self.job_paths(job)
        reused = self._reuse_completed_generated_images(job, job_paths)
        if reused is not None:
            return reused
        self._prepare_generated_images_dir(job_paths)

        from project_aurora.image_generation.image_generation_engine import (
            ImageGenerationEngine,
        )

        try:
            prompt_package = self._memory.load_prompt_package(job.id)
        except FileNotFoundError:
            prompt_package = {}
        _validate_product_type_expectation(job, prompt_package)
        _print_art_direction_diagnostics(prompt_package, job)
        image_family = resolve_product_image_family(
            job.product_name,
            str(prompt_package.get("product_type") or job.category),
            job.category,
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
            transparent_background=image_family.transparent_background,
            background=image_family.openai_background,
            output_format=self._image_config.output_format,
            number_of_images=self._image_config.number_of_images,
        )

    def _generate_storybook_scene(
        self,
        job: ProductionJob,
        prompt_package: dict[str, Any],
        job_paths: ProductFactoryJobPaths,
    ) -> Any:
        from project_aurora.image_generation.image_generation_engine import (
            ImageGenerationEngine,
        )

        existing = tuple(sorted(job_paths.storybook_scenes_dir.glob("*.png")))
        if existing:
            return SimpleNamespace(
                status="SUCCESS",
                generated_files=tuple(str(path) for path in existing),
                warnings=("Reused existing storybook scene.",),
                errors=(),
            )
        scene_package_id = f"{job.id}_storybook_scene"
        scene_package = dict(prompt_package)
        scene_package["image_prompt"] = str(
            prompt_package.get("storybook_scene_prompt")
            or _storybook_scene_prompt(job, job.category)
        )
        scene_package["product_family"] = STORYBOOK_SCENE
        scene_package["transparent_background"] = False
        scene_package["openai_background"] = "opaque"
        self._memory.save_prompt_package(scene_package, package_id=scene_package_id)
        return ImageGenerationEngine(
            memory=self._memory,
            output_dir=job_paths.storybook_scenes_dir,
            provider_config=self._image_config,
        ).run(
            prompt_package_id=scene_package_id,
            provider=self._image_config.provider,
            image_type="storybook_scene",
            width=1024,
            height=1024,
            dpi=300,
            size=self._image_config.size,
            quality=self._image_config.quality,
            transparent_background=False,
            background="opaque",
            output_format=self._image_config.output_format,
            number_of_images=1,
        )

    def run_image_qa(self, job: ProductionJob) -> Any:
        """Keep visual QA optional in the recovery production path."""
        return (
            SimpleNamespace(
                status="WARNING",
                asset_name=job.product_name,
                checks_passed=("visual QA optional",),
                checks_failed=(),
                warnings=("VISUAL_QA_UNAVAILABLE: optional visual inspection unavailable",),
            ),
        )

    def export_commercial_images(self, job: ProductionJob) -> Any:
        """Export final commercial PNGs."""
        job_paths = self.job_paths(job)
        reused = self._reuse_completed_final_images(job, job_paths)
        if reused is not None:
            return reused
        from project_aurora.image_generation.commercial_image_exporter import (
            CommercialImageExporter,
        )
        try:
            prompt_package = self._memory.load_prompt_package(job.id)
        except FileNotFoundError:
            prompt_package = {}
        image_family = resolve_product_image_family(
            job.product_name,
            str(prompt_package.get("product_type") or job.category),
            job.category,
        )

        return CommercialImageExporter(
            source_dir=job_paths.generated_images_dir,
            output_dir=job_paths.final_images_dir,
            output_prefix=_asset_filename_prefix(job),
            product_family=image_family.family,
        ).export()

    def generate_seo(self, job: ProductionJob) -> Any:
        """Generate and save SEO package."""
        job_paths = self.job_paths(job)
        seo_dir = job_paths.job_root / "seo"
        seo_path = seo_dir / "seo_package.json"
        if seo_path.exists():
            package = _load_job_seo_package(seo_path)
            try:
                _validate_job_seo_package(
                    package,
                    job,
                    previous_tags=_previous_product_tags(self._memory, job.id),
                    previous_title=_previous_product_title(self._memory, job.id),
                )
            except RuntimeError as error:
                if "title" not in str(error).casefold():
                    raise
            else:
                if not getattr(self._etsy_config, "is_mock_mode", True):
                    _print_seo_diagnostics(job, package)
                self._memory.save_seo_package(package, package_id=job.id)
                return package
        package = SEOEngine(memory=self._memory).run(
            {
                "job_id": job.id,
                "product_name": job.product_name,
                "product_type": job.category,
                "category": job.category,
                "target_buyer": "digital printable buyers",
                "audience": "digital printable buyers",
                "style": job.style,
            },
            package_id=job.id,
        )
        _validate_job_seo_package(
            package,
            job,
            previous_tags=_previous_product_tags(self._memory, job.id),
            previous_title=_previous_product_title(self._memory, job.id),
        )
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
            previous_title=_previous_product_title(self._memory, job.id),
        )
        final_files = tuple(
            str(path)
            for path in sorted(
                job_paths.final_images_dir.glob("*.png"),
                key=lambda item: item.name,
            )
        )
        merchant_package = _build_and_save_merchant_package(
            job=job,
            seo_package=seo_package,
            memory=self._memory,
            job_paths=job_paths,
            etsy_config=self._etsy_config,
        )
        preflight = _run_merchant_preflight(
            job=job,
            merchant_package=merchant_package,
            seo_package=seo_package,
            memory=self._memory,
            job_paths=job_paths,
        )
        print(preflight.render())
        if preflight.status != "READY_FOR_ETSY_DRAFT":
            raise ProductFactoryStageError("merchant_preflight", tuple(preflight.errors))
        listing_package = ListingPackage(
            product_name=job.product_name,
            collection_name=job.product_name,
            listing_status=READY_FOR_ETSY_DRAFT,
            seo_package_id=job.id,
            prompt_package_id=job.id,
            approved_mockup_files=final_files,
            approved_generated_image_files=final_files,
            is_digital_download=True,
            price=merchant_package.launch_price,
        )
        etsy_config = replace(
            self._etsy_config,
            taxonomy_id=merchant_package.etsy_taxonomy_id,
            default_price=merchant_package.launch_price,
        )
        return EtsyDraftService(
            config=etsy_config,
            memory=self._memory,
        ).create_draft(
            listing_package=listing_package,
            seo_package=seo_package,
        )

    def upload_listing_images(self, job: ProductionJob) -> Any:
        """Upload the final customer PNGs as Etsy listing images."""
        from project_aurora.integrations.etsy.etsy_image_upload_service import (
            EtsyImageUploadService,
        )

        self._refresh_etsy_config()
        job_paths = self.job_paths(job)
        return EtsyImageUploadService(
            config=self._etsy_config,
            memory=self._memory,
            images_dir=job_paths.final_images_dir,
        ).upload_latest_draft_images()

    def upload_customer_downloads(self, job: ProductionJob, listing_id: str | None) -> Any:
        """Upload customer PNG files and the customer ZIP download."""
        from project_aurora.integrations.etsy.etsy_digital_file_service import (
            EtsyDigitalFileService,
        )
        from project_aurora.production.digital_download_builder import (
            DigitalDownloadBuilder,
        )

        self._refresh_etsy_config()
        job_paths = self.job_paths(job)
        try:
            prompt_package = self._memory.load_prompt_package(job.id)
        except FileNotFoundError:
            prompt_package = {}
        image_family = resolve_product_image_family(
            job.product_name,
            str(prompt_package.get("product_type") or job.category),
            job.category,
        )
        service = EtsyDigitalFileService(
            config=self._etsy_config,
            memory=self._memory,
        )
        png_result = service.sync_digital_files(
            listing_id=listing_id,
            final_images_dir=job_paths.final_images_dir,
        )
        if getattr(png_result, "status", "").upper() != "SUCCESS":
            return png_result
        package = DigitalDownloadBuilder(
            final_images_dir=job_paths.final_images_dir,
            output_dir=job_paths.digital_downloads_dir,
            zip_filename=f"{_asset_filename_prefix(job)}.zip",
            product_family=image_family.family,
        ).build()
        if package.status != "SUCCESS" or not package.zip_path:
            raise ProductFactoryStageError(
                "customer_download_upload",
                package.errors or ("Digital download ZIP could not be created.",),
            )
        zip_result = service.upload_digital_file(
            listing_id=listing_id,
            file_path=Path(package.zip_path),
        )
        png_uploaded = int(getattr(png_result, "files_uploaded", 0))
        zip_uploaded = int(getattr(zip_result, "files_uploaded", 0))
        failed = int(getattr(png_result, "failed", 0)) + int(
            getattr(zip_result, "failed", 0)
        )
        errors = tuple(getattr(png_result, "errors", ()) or ()) + tuple(
            getattr(zip_result, "errors", ()) or ()
        )
        warnings = tuple(getattr(png_result, "warnings", ()) or ()) + tuple(
            getattr(zip_result, "warnings", ()) or ()
        )
        return SimpleNamespace(
            status=(
                "SUCCESS"
                if getattr(zip_result, "status", "").upper() == "SUCCESS"
                else "PARTIAL_FAILURE"
            ),
            files_uploaded=png_uploaded + zip_uploaded,
            failed=failed,
            errors=errors,
            warnings=warnings,
            metadata={
                "png_upload": _summarize_result(png_result),
                "zip_upload": _summarize_result(zip_result),
                "zip_path": package.zip_path,
            },
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

    def _reuse_completed_final_images(
        self,
        job: ProductionJob,
        job_paths: ProductFactoryJobPaths,
    ) -> Any | None:
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
        try:
            prompt_package = self._memory.load_prompt_package(job.id)
        except FileNotFoundError:
            prompt_package = {}
        image_family = resolve_product_image_family(
            job.product_name,
            str(prompt_package.get("product_type") or job.category),
            job.category,
        )
        valid_pngs = tuple(
            path
            for path in pngs
            if not validate_commercial_png(
                path,
                product_family=image_family.family,
            )
        )
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
        scope = resolve_watercolor_scope(job.product_name, job.category, job.style)
        if not scope.supported:
            if not self._dry_run and hasattr(self._queue_manager, "mark_unsupported_product_type"):
                self._queue_manager.mark_unsupported_product_type(job.id, scope.reason)
            report = ProductionReport(
                job_id=job.id,
                product=job.product_name,
                style=job.style,
                draft_id=None,
                images=0,
                downloads=0,
                time=round(perf_counter() - started_at, 3),
                success=False,
                failed_stage="product_capability",
                errors=(scope.reason,),
                job_paths=job_paths,
                metadata={"scope": {"canonical_product_type": scope.canonical_product_type}},
            )
            if self._save_report_enabled:
                self._save_report(report)
            return report
        brand_score = score_brand_fit(job.product_name, job.category, job.style)
        if not brand_score.accepted:
            if not self._dry_run and hasattr(self._queue_manager, "mark_unsupported_product_type"):
                self._queue_manager.mark_unsupported_product_type(job.id, brand_score.reason)
            report = ProductionReport(
                job_id=job.id,
                product=job.product_name,
                style=job.style,
                draft_id=None,
                images=0,
                downloads=0,
                time=round(perf_counter() - started_at, 3),
                success=False,
                failed_stage="product_capability",
                errors=(brand_score.reason,),
                job_paths=job_paths,
                metadata={
                    "brand_score": {
                        "score": brand_score.score,
                        "matched_terms": list(brand_score.matched_terms),
                        "blocked_terms": list(brand_score.blocked_terms),
                    }
                },
            )
            if self._save_report_enabled:
                self._save_report(report)
            return report

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
                except ProductFactoryStageError:
                    raise
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
                if (
                    isinstance(error, ProductFactoryStageError)
                    and error.stage == "product_capability"
                    and hasattr(self._queue_manager, "mark_unsupported_product_type")
                ):
                    self._queue_manager.mark_unsupported_product_type(job.id, str(error))
                else:
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
                    f"{getattr(item, 'asset_name', 'asset')} failed QA: "
                    f"{', '.join(getattr(item, 'checks_failed', ()) or ('unknown rule',))}"
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
        "images_already_present",
        "images_present_after",
        "expected_images",
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


def _asset_filename_prefix(job: ProductionJob) -> str:
    job_short = _slug_part(job.id)[:8] or "job"
    product = _slug_part(job.product_name) or "product"
    return f"{job_short}_{product}"


def _simple_clipart_prompt(job: ProductionJob, canonical_product_type: str) -> str:
    subjects = _prompt_subjects(job)
    palette = _prompt_palette(job)
    profile = load_brand_profile()
    return (
        "Create actual customer clipart illustrations only. "
        f"Product: {job.product_name}. "
        f"Product type: {canonical_product_type}. "
        f"Show: {subjects}. "
        f"Brand direction: {profile.get('primary_brand', 'storybook watercolor woodland illustrations')}. "
        "Whimsical vintage watercolor storybook illustrations with warm watercolor, "
        "rich storybook scenes, cottagecore details, woodland atmosphere, cozy interiors "
        "when appropriate, soft natural lighting, beautiful composition, expressive "
        "woodland or farm animals, classic country clothing where relevant, gentle "
        "human-like activities, delicate botanicals, hand-painted watercolor texture, "
        "warm nostalgic charm. "
        f"Palette: {palette}. "
        "Each subject must be isolated, fully visible, centered, separate, and clean edged "
        "on a true transparent background as an RGBA PNG with alpha channel. "
        "No paper. No watercolor-paper texture. No grid. No checkerboard pattern. "
        "No beige canvas. No white canvas. No frame. No border. No drop shadow. "
        "No background decoration. Entire body visible. Head visible. Ears visible. "
        "Feet visible. Tail visible when the animal has a tail. Accessories visible. "
        "Leave at least 10 percent transparent padding around every subject. "
        "Do not crop, clip, cut off, zoom in too close, or let any character touch the edge. "
        "No Etsy cover, no collection overview, no detail preview, no use case mockup, "
        "no poster layout, no packaging, no title card, no product label, no typography. "
        "No text, no words, no letters, no numbers, no logo, no watermark, no border."
    )


def _product_family_prompt(
    job: ProductionJob,
    canonical_product_type: str,
    product_family: str,
) -> str:
    if product_family == STORYBOOK_SCENE:
        return _storybook_scene_prompt(job, canonical_product_type)
    return _simple_clipart_prompt(job, canonical_product_type)


def _storybook_scene_prompt(job: ProductionJob, canonical_product_type: str) -> str:
    subjects = _prompt_subjects(job)
    palette = _prompt_palette(job)
    profile = load_brand_profile()
    return (
        "Create one complete customer-ready watercolor storybook scene. "
        f"Product: {job.product_name}. "
        f"Product type: {canonical_product_type}. "
        f"Scene subject: {subjects}. "
        f"Brand direction: {profile.get('primary_brand', 'storybook watercolor woodland illustrations')}. "
        "Use a rich cozy woodland environment, cottagecore details, warm natural lighting, "
        "soft watercolor rendering, and a full beautiful composition. "
        f"Palette: {palette}. "
        "The background must remain part of the artwork. No transparency. "
        "Fill the canvas with a complete illustration while keeping every character fully visible. "
        "Entire body visible. Head visible. Ears visible. Feet visible. Tail visible when present. "
        "Accessories visible. Leave at least 10 percent padding around important subjects. "
        "Do not crop, clip, cut off, zoom in too close, or let any character touch the edge. "
        "No isolated clipart, no transparent background, no cutout elements, no grid, no border, "
        "no product cover, no mockup, no product label, no typography. "
        "No text, no words, no letters, no numbers, no logo, no watermark."
    )


def _product_family_negative_prompt(product_family: str) -> str:
    common = "no text, no letters, no numbers, no logo, no watermark"
    if product_family == STORYBOOK_SCENE:
        return (
            f"{common}, no transparent background, no isolated cutout, no clipart grid, "
            "no border, no frame, no product title, no typography, no cropped characters"
        )
    return (
        f"{common}, no background, no paper texture, no watercolor paper, "
        "no beige background, no grid, no border, no frame, no shadow, "
        "no poster layout, no mockup, no product title, no typography, "
        "no promotional cover, no black background"
    )


def _prompt_subjects(job: ProductionJob) -> str:
    text = f"{job.product_name} {' '.join(job.keywords)}".casefold()
    if "bakery" in text:
        return "rabbit baking bread, fox reading a recipe book, mouse painting at a tiny easel, bear holding a pie"
    if "mushroom" in text:
        return "autumn mushrooms, woodland leaves, acorns, berries, and fern accents"
    if "botanical" in text or "floral" in text:
        return "watercolor botanical sprigs, flowers, leaves, berries, and garden accents"
    if "baby" in text or "nursery" in text:
        return "baby woodland animals, gentle farm animals, soft botanical accents, nursery-friendly characters"
    if "woodland" in text or "animal" in text:
        return "rabbit baking bread, fox reading a book, hedgehog gardening, mouse painting at a tiny easel"
    return "coordinated watercolor clipart elements matching the product theme"


def _prompt_palette(job: ProductionJob) -> str:
    text = f"{job.product_name} {job.seasonal_theme}".casefold()
    if "autumn" in text or "mushroom" in text:
        return "warm cream, muted rust, sage green, soft brown, dusty berry"
    if "spring" in text:
        return "warm cream, fresh sage, blush pink, butter yellow, soft blue"
    if "christmas" in text or "winter" in text:
        return "warm cream, evergreen, cranberry, soft brown, muted gold"
    return "warm cream, sage green, soft brown, muted red, pale blue"


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
        etsy_listing_id=str(data.get("etsy_listing_id", "")),
        category=str(data.get("category", data.get("product_type", ""))),
        audience=str(data.get("audience", data.get("target_buyer", ""))),
        style=str(data.get("style", "")),
        source=str(data.get("source", "")),
        warnings=tuple(str(item) for item in data.get("warnings", ())),
        created_at=datetime.fromisoformat(str(data["created_at"])),
        generated_at=datetime.fromisoformat(str(data.get("generated_at") or data["created_at"])),
    )


def _validate_job_seo_package(
    package: Any,
    job: ProductionJob,
    previous_tags: tuple[str, ...] = (),
    previous_title: str = "",
) -> None:
    job_id = getattr(package, "job_id", "")
    product_name = getattr(package, "product_name", "")
    tags = tuple(str(tag).strip() for tag in getattr(package, "tags", ()))
    title = str(getattr(package, "title", "")).strip()
    description = str(getattr(package, "description", "")).strip()
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
    if not title:
        raise RuntimeError("SEO package title is empty.")
    if len(title) > 140:
        raise RuntimeError("SEO package title exceeds Etsy title length.")
    if not _title_is_relevant_to_job(title, job):
        report = _title_relevance_report(title, job)
        _print_title_relevance_report(report)
        raise RuntimeError(
            "SEO package title is not relevant to the current product. "
            f"Generated title: {report['generated_title']}. "
            f"Required product concepts: {', '.join(report['required_product_concepts'])}. "
            f"Missing concepts: {', '.join(report['missing_concepts']) or 'none'}. "
            "Unrelated concepts detected: "
            f"{', '.join(report['unrelated_concepts_detected']) or 'none'}. "
            f"Relevance score: {report['relevance_score']}."
        )
    if previous_title and title.casefold() == previous_title.casefold():
        raise RuntimeError("SEO package title is identical to the immediately previous product.")
    if not _description_is_relevant_to_job(description, job):
        raise RuntimeError("SEO package description is not relevant to the current product.")
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


def _previous_product_title(memory: MemoryManager, current_job_id: str) -> str:
    try:
        latest = memory.load_record(REPORT_COLLECTION, "latest")
    except FileNotFoundError:
        return ""
    if latest.get("job_id") == current_job_id:
        return ""
    metadata = latest.get("metadata")
    if not isinstance(metadata, dict):
        return ""
    seo = metadata.get("seo_generation")
    if isinstance(seo, dict) and isinstance(seo.get("title"), str):
        return seo["title"]
    return ""


def _print_seo_diagnostics(job: ProductionJob, package: Any) -> None:
    report = _title_relevance_report(str(getattr(package, "title", "")), job)
    print("SEO JOB")
    print(job.product_name)
    print("")
    print("SEO TITLE")
    print(getattr(package, "title", ""))
    print("")
    print("REQUIRED PRODUCT CONCEPTS")
    for concept in report["required_product_concepts"]:
        print(concept)
    print("")
    print("MISSING CONCEPTS")
    for concept in report["missing_concepts"]:
        print(concept)
    print("")
    print("UNRELATED CONCEPTS DETECTED")
    for concept in report["unrelated_concepts_detected"]:
        print(concept)
    print("")
    print("RELEVANCE SCORE")
    print(report["relevance_score"])
    print("")
    print("SEO TAGS")
    for tag in getattr(package, "tags", ()):
        print(tag)


def _print_title_relevance_report(report: dict[str, Any]) -> None:
    print("SEO RELEVANCE DIAGNOSTICS")
    print("")
    print("Generated Title")
    print(report["generated_title"])
    print("")
    print("Required Product Concepts")
    for concept in report["required_product_concepts"]:
        print(concept)
    print("")
    print("Missing Concepts")
    for concept in report["missing_concepts"]:
        print(concept)
    print("")
    print("Unrelated Concepts Detected")
    for concept in report["unrelated_concepts_detected"]:
        print(concept)
    print("")
    print("Exact Relevance Score")
    print(report["relevance_score"])


def _print_art_direction_diagnostics(prompt_package: dict[str, Any], job: ProductionJob) -> None:
    art_direction = prompt_package.get("art_direction")
    if not isinstance(art_direction, dict):
        art_direction = {}
    print("ART DIRECTION")
    print("")
    print("Product")
    print(job.product_name)
    print("")
    print("Category")
    print(job.category)
    print("")
    print("Selected Style")
    print(prompt_package.get("style", ""))
    print("")
    print("Rendering Family")
    print(prompt_package.get("rendering_family", ""))
    print("")
    print("Palette")
    print(prompt_package.get("palette", ""))
    print("")
    print("Composition")
    print(prompt_package.get("composition", ""))
    print("")
    print("Background")
    print(prompt_package.get("background_treatment", ""))
    print("")
    print("Reason")
    print(art_direction.get("commercial_rationale") or art_direction.get("reason", ""))
    print("")
    print("Proven Winner Evidence")
    print(art_direction.get("proven_winner_evidence_used", "none"))


def _print_qa_findings(findings: Any) -> None:
    if not isinstance(findings, (list, tuple)):
        return
    failed = [
        finding
        for finding in findings
        if isinstance(finding, dict) and finding.get("failed_rules")
    ]
    if not failed:
        return
    print("IMAGE QA FINDINGS")
    for finding in failed:
        print("")
        print("File")
        print(finding.get("file", ""))
        print("Selected Style")
        print(finding.get("selected_style", ""))
        for label, key in (
            ("Rendering Family", "rendering_family_result"),
            ("Palette", "palette_result"),
            ("Composition", "composition_result"),
            ("Background", "background_result"),
            ("Product Type Suitability", "product_type_suitability"),
        ):
            value = finding.get(key)
            if not isinstance(value, dict):
                continue
            print(label)
            print(
                f"{value.get('status', '')} "
                f"({value.get('confidence', 0)}%) - {value.get('message', '')}"
            )
        print("Exact Failed Rules")
        for rule in finding.get("failed_rules", ()):
            print(rule)


SUPPORTED_PRODUCT_TYPE_EXPECTATIONS = {
    "clipart",
    "watercolor_clipart_bundle",
    "watercolor_animal_collection",
    "watercolor_botanical_collection",
    "watercolor_woodland_collection",
    "watercolor_seasonal_collection",
    "signature_storybook_animal_collection",
    "watercolor_sticker_illustration_set",
    "digital illustration collection",
    "illustration collection",
    "sticker illustration set",
}


def _validate_product_type_expectation(
    job: ProductionJob,
    prompt_package: dict[str, Any],
) -> None:
    product_type = str(prompt_package.get("product_type") or job.category or "").strip()
    normalized = product_type.casefold()
    if not normalized:
        raise RuntimeError("Missing product-type expectation before image generation.")
    scope = resolve_watercolor_scope(job.product_name, product_type, job.style)
    if not scope.supported and not any(expected in normalized for expected in SUPPORTED_PRODUCT_TYPE_EXPECTATIONS):
        raise RuntimeError(
            "Unsupported product-type expectation before image generation: "
            f"{product_type}."
        )


def _resolve_product_capability(job: ProductionJob) -> Any:
    from project_aurora.production.product_capability_resolver import (
        ProductCapabilityResolver,
    )

    return ProductCapabilityResolver().resolve(
        product_name=job.product_name,
        product_type=job.category,
        category=job.category,
    )


def _build_and_save_merchant_package(
    *,
    job: ProductionJob,
    seo_package: Any,
    memory: MemoryManager,
    job_paths: ProductFactoryJobPaths,
    etsy_config: Any,
) -> Any:
    from project_aurora.integrations.etsy.etsy_client import EtsyClient
    from project_aurora.integrations.etsy.etsy_taxonomy_resolver import (
        EtsyTaxonomyResolver,
    )
    from project_aurora.merchandising.market_pricing import (
        EtsyMarketPricingProvider,
    )
    from project_aurora.merchandising.pricing_engine import PricingEngine
    from project_aurora.production.merchant_package import MerchantPackage

    capability = _resolve_product_capability(job)
    if not capability.supported:
        raise ProductFactoryStageError("product_capability", (capability.reason,))
    taxonomy = EtsyTaxonomyResolver().resolve(
        product_name=job.product_name,
        product_type=job.category,
        category=job.category,
        audience=job.target_customer,
        holiday=job.seasonal_theme,
    )
    _print_taxonomy_diagnostics(job, taxonomy)
    if not taxonomy.resolved:
        raise ProductFactoryStageError(
            "taxonomy_resolution",
            (taxonomy.resolution_reason,),
        )
    market_provider = None
    if not getattr(etsy_config, "is_mock_mode", True):
        market_provider = EtsyMarketPricingProvider(
            client=EtsyClient(etsy_config),
            memory=memory,
        )
    pricing = PricingEngine(market_provider=market_provider).resolve_price(
        product_name=job.product_name,
        product_type=job.category,
        category=job.category,
        bundle_size=max(4, len(job.keywords)),
        image_count=4,
        commercial_license=True,
        competition_level=job.estimated_competition,
        demand_score=job.demand_score or job.confidence_score,
        confidence_score=job.confidence_score,
        target_buyer=job.target_customer,
        artistic_category=job.style,
        keywords=job.keywords,
    )
    _print_pricing_diagnostics(job, pricing)
    prompt = _load_optional_prompt(memory, job.id)
    merchant = MerchantPackage(
        job_id=job.id,
        product_name=job.product_name,
        product_type=job.category,
        capability_mode=capability.mode,
        etsy_taxonomy_id=int(taxonomy.taxonomy_id or 0),
        etsy_taxonomy_path=taxonomy.full_taxonomy_path,
        taxonomy_confidence=taxonomy.confidence,
        price_range=(pricing.market_low, pricing.market_median, pricing.market_high),
        recommended_price=pricing.recommended_price,
        launch_price=pricing.launch_price,
        pricing_reason=pricing.reason,
        pricing_source=pricing.source,
        selected_style=str(prompt.get("style") or job.style),
        style_confidence=int(prompt.get("art_direction", {}).get("confidence", 90))
        if isinstance(prompt.get("art_direction"), dict)
        else 90,
        composition=str(prompt.get("composition", "")),
        background=str(prompt.get("background_treatment", "")),
        product_capability_result=capability.to_dict(),
    )
    merchant_dir = job_paths.job_root / "merchant"
    merchant_dir.mkdir(parents=True, exist_ok=True)
    (merchant_dir / "merchant_package.json").write_text(
        json.dumps(merchant.to_dict(), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    memory.save_record("merchant_packages", job.id, merchant.to_dict())
    return merchant


def _run_merchant_preflight(
    *,
    job: ProductionJob,
    merchant_package: Any,
    seo_package: Any,
    memory: MemoryManager,
    job_paths: ProductFactoryJobPaths,
) -> Any:
    from project_aurora.production.merchant_preflight import MerchantPreflight

    result = MerchantPreflight().run(
        job=job,
        merchant_package=merchant_package,
        seo_package=seo_package,
        final_images_dir=job_paths.final_images_dir,
        image_qa_approved=_image_qa_ready(memory),
    )
    memory.save_record("merchant_preflight", job.id, result.to_dict())
    return result


def _image_qa_ready(memory: MemoryManager) -> bool:
    try:
        record = memory.load_image_qa_results()
    except FileNotFoundError:
        return True
    results = record.get("results", ())
    if not isinstance(results, list):
        return False
    return all(str(result.get("status", "")).upper() in {"PASS", "WARNING"} for result in results if isinstance(result, dict))


def _load_optional_prompt(memory: MemoryManager, job_id: str) -> dict[str, Any]:
    try:
        return memory.load_prompt_package(job_id)
    except FileNotFoundError:
        return {}


def _print_taxonomy_diagnostics(job: ProductionJob, taxonomy: Any) -> None:
    print("ETSY TAXONOMY")
    print("")
    print("Product")
    print(job.product_name)
    print("")
    print("Product Type")
    print(job.category)
    print("")
    print("Taxonomy")
    print(taxonomy.full_taxonomy_path)
    print("")
    print("Taxonomy ID")
    print(taxonomy.taxonomy_id or "")
    print("")
    print("Confidence")
    print(taxonomy.confidence)
    print("")
    print("Reason")
    print(taxonomy.resolution_reason)


def _print_pricing_diagnostics(job: ProductionJob, pricing: Any) -> None:
    print("PRICING")
    print("")
    print("Product")
    print(job.product_name)
    print("")
    print("Product Type")
    print(job.category)
    print("")
    print("Market Range")
    print(f"{pricing.market_low:.2f} - {pricing.market_high:.2f}")
    print("")
    print("Listings Compared")
    print(getattr(pricing, "listings_compared", 0))
    print("")
    print("Median")
    print(f"{pricing.market_median:.2f}")
    print("")
    print("Top Seller Median")
    print(f"{getattr(pricing, 'top_seller_median', 0.0):.2f}")
    print("")
    print("Competition")
    print(getattr(pricing, "competition_level", ""))
    print("")
    print("Recommended Price")
    print(f"{pricing.recommended_price:.2f}")
    print("")
    print("Launch Price")
    print(f"{pricing.launch_price:.2f}")
    print("")
    print("Reason")
    print(pricing.reason)
    print("")
    print("Source")
    print(pricing.source)


def _title_is_relevant_to_job(title: str, job: ProductionJob) -> bool:
    report = _title_relevance_report(title, job)
    return (
        report["relevance_score"] >= 70
        and not report["missing_concepts"]
        and not report["unrelated_concepts_detected"]
    )


def _title_relevance_report(title: str, job: ProductionJob) -> dict[str, Any]:
    lowered = title.casefold()
    product_lower = job.product_name.casefold()
    title_tokens = {
        token
        for token in re.split(r"[^a-z0-9]+", lowered)
        if len(token) > 2
    }
    unrelated = (
        "summer berry",
        "cupcake toppers",
        "favor tags",
        "girls party decor",
        "birthday invitation",
    )
    unrelated_detected = tuple(term for term in unrelated if term in lowered)
    required = _required_title_concepts(job)
    missing: list[str] = []
    for concept in required:
        options = tuple(option.strip() for option in concept.split("|"))
        if not any(option.casefold() in title_tokens or option.casefold() in lowered for option in options):
            missing.append(concept)
    product_tokens = {
        token
        for token in re.split(r"[^a-z0-9]+", job.product_name.casefold())
        if len(token) > 2
    }
    overlap_score = 20 if product_tokens & title_tokens else 0
    concept_score = int(80 * ((len(required) - len(missing)) / max(1, len(required))))
    penalty = 25 * len(unrelated_detected)
    score = max(0, min(100, overlap_score + concept_score - penalty))
    if "wildflower wedding invitation" in product_lower:
        if not {"wildflower", "wedding", "invitation"} <= title_tokens:
            score = 0
        if not ({"floral"} & title_tokens):
            score = 0
        if not ({"printable", "digital"} & title_tokens):
            score = 0
    if "clipart" in product_lower and not ({"clipart", "graphics"} & title_tokens):
        score = 0
    if "sticker" in product_lower and "sticker" not in title_tokens and "stickers" not in title_tokens:
        score = 0
    if "paper" in product_lower and "paper" not in title_tokens:
        score = 0
    if "birthday" in product_lower and ({"wall", "art"} <= title_tokens):
        score = 0
    if "clipart" in product_lower and ({"wall", "art"} <= title_tokens):
        score = 0
    return {
        "generated_title": title,
        "required_product_concepts": tuple(required),
        "missing_concepts": tuple(missing),
        "unrelated_concepts_detected": unrelated_detected,
        "relevance_score": score,
    }


def _required_title_concepts(job: ProductionJob) -> tuple[str, ...]:
    lowered = f"{job.product_name} {job.category}".casefold()
    concepts: list[str] = []
    for token in re.split(r"[^a-z0-9]+", job.product_name.casefold()):
        if len(token) > 2 and token not in {"and", "the", "for", "with"}:
            concepts.append(token)
    if "strawberry" in lowered:
        concepts.append("berry|summer")
    if "printable" in lowered or "party" in lowered:
        concepts.append("printable")
    if "birthday" in lowered:
        concepts.append("birthday")
    return tuple(dict.fromkeys(concepts))


def _description_is_relevant_to_job(description: str, job: ProductionJob) -> bool:
    from project_aurora.seo.description_builder import (
        DOWNLOAD_DISCLAIMER_SECTION,
        PURCHASE_SECTION,
        RAINBOW_MILK_STUDIO_DESCRIPTION,
    )

    if not description or len(description) > 13000:
        return False
    if description == RAINBOW_MILK_STUDIO_DESCRIPTION:
        return False
    if PURCHASE_SECTION not in description:
        return False
    if DOWNLOAD_DISCLAIMER_SECTION not in description:
        return False
    lowered = description.casefold()
    product_lower = job.product_name.casefold()
    product_tokens = {
        token
        for token in re.split(r"[^a-z0-9]+", product_lower)
        if len(token) > 2
    }
    if not (product_tokens & set(re.split(r"[^a-z0-9]+", lowered))):
        return False
    if "girls party decor" in lowered:
        return False
    if "summer berry" in lowered and "strawberry" not in product_lower:
        return False
    if "this seo-ready printable download works beautifully" in lowered:
        return False
    if "classroom, alphabet, wall" in lowered and "classroom" not in product_lower:
        return False
    strawberry_terms = ("strawberry", "berry")
    party_terms = ("cupcake", "favor tag")
    if "strawberry" not in product_lower and any(term in lowered for term in strawberry_terms):
        return False
    if "party" not in product_lower and "birthday" not in product_lower and any(term in lowered for term in party_terms):
        return False
    return True
