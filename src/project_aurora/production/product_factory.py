"""Orchestrate one Aurora production queue job end to end."""

from __future__ import annotations

from dataclasses import dataclass, field
from dataclasses import fields, is_dataclass
from dataclasses import replace
from datetime import datetime
import json
from pathlib import Path
import re
import shutil
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
    NEEDS_ASSETS,
    ProductionJob,
    ProductionQueueManager,
)
from project_aurora.production.asset_manifest import (
    manifest_path_for,
    product_slug,
    validate_asset_ownership,
    write_asset_manifest,
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
MAX_OPENAI_IMAGES_PER_REQUEST = 5


@dataclass(frozen=True, slots=True)
class ImageGenerationBatchResult:
    """Aggregated result for category jobs split across provider requests."""

    status: str
    generated_files: tuple[str, ...] = field(default_factory=tuple)
    image_paths: tuple[str, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)
    errors: tuple[str, ...] = field(default_factory=tuple)
    metadata: dict[str, Any] = field(default_factory=dict)


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

    def run_commercial_image_qa(self, job: ProductionJob) -> Any:
        """Run commercial image-set QA before Etsy draft creation."""

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
            "asset_manifest": str(manifest_path_for(self.job_root)),
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
        from project_aurora.muse.muse_engine import MuseEngine
        from project_aurora.creative.product_creative_director import (
            ProductionCreativeDirector,
        )
        from project_aurora.image_generation.image_prompt_builder import (
            StructuredImagePromptBuilder,
        )
        from project_aurora.research.seasonal_intelligence import SeasonalIntelligence

        seasonal_review = SeasonalIntelligence().evaluate(
            product_name=job.product_name,
            season=job.seasonal_theme,
            product_type=job.category,
        )
        _print_seasonal_review(seasonal_review)
        if seasonal_review.production_decision in {"HOLD", "REJECT_OUT_OF_SEASON"}:
            raise ProductFactoryStageError("seasonal_review", (seasonal_review.reason,))
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

        creative_brief = ProductionCreativeDirector().create_brief(job, art_direction)
        image_prompts = StructuredImagePromptBuilder().build_prompts(
            creative_brief,
            seasonal_review,
        )
        _print_creative_brief(creative_brief)
        _print_image_blueprints(creative_brief)
        _print_prompt_diagnostics(image_prompts, seasonal_review)

        recipe = PromptComposer(memory=self._memory).compose_art_directed(
            product=job.product_name,
            style=art_direction.recommended_style,
            palette=art_direction.palette,
            rendering_method=art_direction.rendering_method,
            composition=art_direction.composition,
            mood=art_direction.mood,
            background_treatment=art_direction.background_treatment,
            lighting=art_direction.lighting,
            texture=art_direction.texture,
            typography_direction=art_direction.typography_direction,
            negative_style_constraints=art_direction.negative_style_constraints,
            category=job.category,
            recipe_id=job.id,
        )
        self._memory.save_prompt_package(
            {
                "product_name": job.product_name,
                "collection": job.product_name,
                "theme": job.seasonal_theme,
                "product_type": job.category,
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
                "image_prompt": _combined_generation_prompt(image_prompts),
                "negative_prompt": ", ".join(creative_brief.negative_prompt),
                "image_prompts": [prompt.to_dict() for prompt in image_prompts],
                "creative_brief": creative_brief.to_dict(),
                "seasonal_review": seasonal_review.to_dict(),
                "consistency_key": creative_brief.consistency_key,
                "text_policy": creative_brief.text_policy,
                "expected_image_count": _resolve_generation_image_count(
                    job,
                    configured_count=self._image_config.number_of_images,
                ),
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
            },
            package_id=job.id,
        )
        return recipe

    def generate_images(self, job: ProductionJob) -> Any:
        """Generate four OpenAI images through the image engine."""
        job_paths = self.job_paths(job)
        _ensure_required_layout_template(job, job_paths)
        capability = _resolve_product_capability(job, assets_dir=job_paths.final_images_dir)
        if not capability.supported:
            raise ProductFactoryStageError("product_capability", (capability.reason,))
        number_of_images = _resolve_generation_image_count(
            job,
            configured_count=self._image_config.number_of_images,
        )
        reused = self._reuse_completed_generated_images(
            job,
            job_paths,
            expected_count=number_of_images,
        )
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
        engine = ImageGenerationEngine(
            memory=self._memory,
            output_dir=job_paths.generated_images_dir,
            provider_config=self._image_config,
        )
        result = _run_image_generation_chunks(
            engine=engine,
            prompt_package_id=job.id,
            provider=self._image_config.provider,
            size=self._image_config.size,
            quality=self._image_config.quality,
            background=self._image_config.background,
            output_format=self._image_config.output_format,
            number_of_images=number_of_images,
        )
        normalized = _normalize_asset_result_files(
            job=job,
            job_paths=job_paths,
            result=result,
            file_attribute="generated_files",
            source_stage="image_generation",
        )
        if _result_files_exist(normalized, "generated_files"):
            self._memory.save_image_result(normalized, result_id=job.id)
            self._memory.save_image_result(normalized)
        return normalized

    def run_image_qa(self, job: ProductionJob) -> Any:
        """Run deterministic image QA."""
        from project_aurora.image_qa.qa_engine import ImageQAEngine

        results = ImageQAEngine(memory=self._memory).run(image_result_id=job.id)
        try:
            findings = self._memory.load_record("image_qa_findings", job.id).get("findings", ())
        except FileNotFoundError:
            findings = ()
        _print_qa_findings(findings)
        return results

    def export_commercial_images(self, job: ProductionJob) -> Any:
        """Export final commercial PNGs."""
        job_paths = self.job_paths(job)
        expected_count = _resolve_generation_image_count(
            job,
            configured_count=self._image_config.number_of_images,
        )
        export_category = _resolve_export_category(job)
        reused = self._reuse_completed_final_images(job, job_paths, expected_count)
        if reused is not None:
            return reused
        _archive_existing_final_assets(job_paths)
        from project_aurora.image_generation.commercial_image_exporter import (
            CommercialImageExporter,
        )

        result = CommercialImageExporter(
            source_dir=job_paths.generated_images_dir,
            output_dir=job_paths.final_images_dir,
            required_count=expected_count,
            category=export_category,
        ).export()
        if getattr(result, "status", "").upper() != "SUCCESS":
            return result
        result = _normalize_asset_result_files(
            job=job,
            job_paths=job_paths,
            result=result,
            file_attribute="exported_files",
            source_stage="commercial_export",
        )
        package_result = _build_required_product_package(job, job_paths.final_images_dir)
        if package_result is not None and package_result.status != "SUCCESS":
            from project_aurora.image_generation.commercial_image_exporter import (
                CommercialImageExportResult,
            )

            return CommercialImageExportResult(
                status="FAILED",
                exported_files=tuple(getattr(result, "exported_files", ())),
                errors=tuple(package_result.errors),
            )
        return result

    def run_commercial_image_qa(self, job: ProductionJob) -> Any:
        """Run commercial image QA on final assets before Etsy draft creation."""
        from project_aurora.quality.commercial_image_qa import CommercialImageQA

        job_paths = self.job_paths(job)
        _sanitize_final_asset_names(job, job_paths)
        final_files = _final_asset_files(job, job_paths.final_images_dir)
        try:
            prompt_package = self._memory.load_prompt_package(job.id)
        except FileNotFoundError:
            prompt_package = {}
        seasonal_review = (
            prompt_package.get("seasonal_review")
            if isinstance(prompt_package.get("seasonal_review"), dict)
            else None
        )
        ownership = validate_asset_ownership(
            manifest_path=manifest_path_for(job_paths.job_root),
            job_id=job.id,
            product_name=job.product_name,
            workspace=job_paths.job_root,
            files=final_files,
            source_stage="commercial_export",
        )
        _print_asset_ownership_diagnostics(ownership.diagnostics)
        result = CommercialImageQA().evaluate(
            job=job,
            final_files=final_files,
            prompt_package=prompt_package,
            seasonal_review=seasonal_review,
            asset_manifest_path=manifest_path_for(job_paths.job_root),
            workspace=job_paths.job_root,
        )
        self._memory.save_record("commercial_image_qa", job.id, result.to_dict())
        self._memory.save_record("commercial_image_qa", "latest", result.to_dict())
        print(result.render())
        return result

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
                if not getattr(self._etsy_config, "is_mock_mode", True):
                    print("SEO PACKAGE REGENERATION")
                    print("")
                    print("Product")
                    print(job.product_name)
                    print("")
                    print("Reason")
                    print(str(error))
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
        final_files = tuple(str(path) for path in _final_asset_files(job, job_paths.final_images_dir))
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
        """Upload final PNGs as Etsy listing images."""
        from project_aurora.integrations.etsy.etsy_image_upload_service import (
            EtsyImageUploadService,
        )

        self._refresh_etsy_config()
        return EtsyImageUploadService(
            config=self._etsy_config,
            memory=self._memory,
            images_dir=self.job_paths(job).final_images_dir,
            max_images=min(
                10,
                _resolve_generation_image_count(
                    job,
                    configured_count=self._image_config.number_of_images,
                ),
            ),
            required_image_count=_resolve_generation_image_count(
                job,
                configured_count=self._image_config.number_of_images,
            ),
            job_id=job.id,
            product_name=job.product_name,
            asset_manifest_path=manifest_path_for(self.job_paths(job).job_root),
        ).upload_latest_draft_images()

    def upload_customer_downloads(self, job: ProductionJob, listing_id: str | None) -> Any:
        """Upload final PNGs as Etsy customer downloads."""
        from project_aurora.integrations.etsy.etsy_digital_file_service import (
            EtsyDigitalFileService,
        )

        self._refresh_etsy_config()
        package_file = _required_zip_package_file(job, self.job_paths(job).final_images_dir)
        if package_file is not None:
            return EtsyDigitalFileService(
                config=self._etsy_config,
                memory=self._memory,
                required_count=1,
            ).sync_digital_package(
                listing_id=listing_id,
                package_path=package_file,
            )
        return EtsyDigitalFileService(
            config=self._etsy_config,
            memory=self._memory,
            required_count=_resolve_generation_image_count(
                job,
                configured_count=self._image_config.number_of_images,
            ),
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
            self._etsy_config = EtsyConfig.from_environment(
                DEFAULT_ETSY_CONFIG_PATH,
                DEFAULT_LOCAL_CREDENTIAL_PATH,
            )

    def _prepare_generated_images_dir(self, job_paths: ProductFactoryJobPaths) -> None:
        job_paths.generated_images_dir.mkdir(parents=True, exist_ok=True)
        existing_pngs = tuple(job_paths.generated_images_dir.glob("*.png"))
        if existing_pngs:
            rejected_dir = (
                job_paths.job_root
                / "rejected"
                / f"generated_images_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            )
            rejected_dir.mkdir(parents=True, exist_ok=True)
            for png_path in existing_pngs:
                shutil.move(str(png_path), str(rejected_dir / png_path.name))

    def _reuse_completed_generated_images(
        self,
        job: ProductionJob,
        job_paths: ProductFactoryJobPaths,
        expected_count: int,
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
        if len(pngs) == expected_count and len(valid_pngs) == expected_count:
            ownership = validate_asset_ownership(
                manifest_path=manifest_path_for(job_paths.job_root),
                job_id=job.id,
                product_name=job.product_name,
                workspace=job_paths.job_root,
                files=valid_pngs,
                source_stage="image_generation",
            )
            _print_asset_ownership_diagnostics(ownership.diagnostics)
            if not ownership.passed:
                return None
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
            self._memory.save_image_result(result, result_id=job.id)
            return result
        if len(pngs) != expected_count:
            return None
        raise RuntimeError(
            "Generated images directory contains incomplete or unexpected PNG files; "
            f"expected exactly {expected_count} valid PNGs, found {len(valid_pngs)} valid "
            f"out of {len(pngs)} total in {job_paths.generated_images_dir}."
        )

    @staticmethod
    def _reuse_completed_final_images(
        job: ProductionJob,
        job_paths: ProductFactoryJobPaths,
        expected_count: int,
    ) -> Any | None:
        from project_aurora.image_generation.commercial_image_exporter import (
            DIGITAL_PAPER_IMAGE_SIZE,
            DIGITAL_PAPER_MIN_SHARPNESS,
            PARTY_PRINTABLE_IMAGE_SIZE,
            WALL_ART_MIN_SHARPNESS,
            WALL_ART_RATIOS,
            CommercialImageExportResult,
            validate_commercial_jpg,
            validate_commercial_png,
        )
        from project_aurora.image_generation.image_inspector import inspect_png
        from project_aurora.production.merchant_specification import (
            MerchantSpecificationLibrary,
        )

        if not job_paths.final_images_dir.exists():
            return None
        try:
            spec = MerchantSpecificationLibrary().resolve(job.category, job.product_name)
        except RuntimeError:
            spec = None
        if spec is not None:
            suffixes = {f".{fmt.casefold()}" for fmt in spec.file_formats}
            files = tuple(
                path
                for path in sorted(job_paths.final_images_dir.glob("*"), key=lambda item: item.name)
                if path.is_file()
                and path.suffix.casefold() in suffixes
                and "preview" not in path.stem.casefold()
            )
            if not files:
                return None
            if len(files) != expected_count:
                return None
            errors: list[str] = []
            if spec.category == "Printable Wall Art":
                expected_sizes = dict(WALL_ART_RATIOS)
                for path in files:
                    label = _ratio_label_from_final_file(path)
                    expected_size = expected_sizes.get(label)
                    if expected_size is None:
                        errors.append(f"{path.name}: Missing required wall art ratio label.")
                    else:
                        errors.extend(
                            f"{path.name}: {error}"
                            for error in validate_commercial_jpg(
                                path,
                                expected_size,
                                minimum_sharpness=WALL_ART_MIN_SHARPNESS,
                            )
                        )
            elif spec.category == "Digital Paper":
                for path in files:
                    errors.extend(
                        f"{path.name}: {error}"
                        for error in validate_commercial_jpg(
                            path,
                            DIGITAL_PAPER_IMAGE_SIZE,
                            minimum_sharpness=DIGITAL_PAPER_MIN_SHARPNESS,
                        )
                    )
            elif spec.category == "Party Printables":
                for path in files:
                    errors.extend(
                        f"{path.name}: {error}"
                        for error in validate_commercial_jpg(path, PARTY_PRINTABLE_IMAGE_SIZE)
                    )
            else:
                for path in files:
                    if path.suffix.casefold() == ".png":
                        errors.extend(
                            f"{path.name}: {error}" for error in validate_commercial_png(path)
                        )
            if errors:
                return None
            ownership = validate_asset_ownership(
                manifest_path=manifest_path_for(job_paths.job_root),
                job_id=job.id,
                product_name=job.product_name,
                workspace=job_paths.job_root,
                files=files,
                source_stage="commercial_export",
            )
            _print_asset_ownership_diagnostics(ownership.diagnostics)
            if not ownership.passed:
                return None
            return CommercialImageExportResult(
                status="SUCCESS",
                exported_files=tuple(str(path) for path in files),
                warnings=("Reused existing valid category-specific final commercial images.",),
                inspections=tuple(
                    inspect_png(path) for path in files if path.suffix.casefold() == ".png"
                ),
            )
        pngs = tuple(sorted(job_paths.final_images_dir.glob("*.png"), key=lambda path: path.name))
        if not pngs:
            return None
        valid_pngs = tuple(path for path in pngs if not validate_commercial_png(path))
        if len(pngs) == expected_count and len(valid_pngs) == expected_count:
            ownership = validate_asset_ownership(
                manifest_path=manifest_path_for(job_paths.job_root),
                job_id=job.id,
                product_name=job.product_name,
                workspace=job_paths.job_root,
                files=valid_pngs,
                source_stage="commercial_export",
            )
            _print_asset_ownership_diagnostics(ownership.diagnostics)
            if not ownership.passed:
                return None
            return CommercialImageExportResult(
                status="SUCCESS",
                exported_files=tuple(str(path) for path in valid_pngs),
                warnings=("Reused existing valid final commercial images.",),
                inspections=tuple(inspect_png(path) for path in valid_pngs),
            )
        return None


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

    def run_commercial_image_qa(self, job: ProductionJob) -> Any:
        """Simulate commercial image QA."""
        return SimpleNamespace(
            status="PASS",
            overall_score=100,
            blocking_issues=(),
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
            (
                "commercial_image_qa",
                lambda: _run_commercial_image_qa_stage(self._stage_runner, job),
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
            failed_stage = _failed_stage_from(error)
            if not self._dry_run:
                if (
                    isinstance(error, ProductFactoryStageError)
                    and error.stage == "product_capability"
                ):
                    self._queue_manager.mark_needs_assets(job.id, str(error))
                else:
                    self._queue_manager.mark_failed(job.id)
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


def _run_commercial_image_qa_stage(
    stage_runner: ProductFactoryStageRunner,
    job: ProductionJob,
) -> Any:
    runner = getattr(stage_runner, "run_commercial_image_qa", None)
    if runner is None:
        return SimpleNamespace(
            status="PASS",
            overall_score=100,
            warnings=("Commercial Image QA skipped by legacy test stage runner.",),
            errors=(),
        )
    return runner(job)


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


def _print_seasonal_review(review: Any) -> None:
    print("SEASONAL REVIEW")
    print("Product")
    print(review.product_name)
    print("Current Date")
    print(review.current_date.isoformat())
    print("Seasonal Score")
    print(review.seasonal_score)
    print("Lead Time")
    print(review.lead_time_score)
    print("Decision")
    print(review.production_decision)
    print("Reason")
    print(review.reason)


def _print_creative_brief(brief: Any) -> None:
    print("CREATIVE BRIEF")
    print("Target Customer")
    print(brief.target_customer)
    print("Commercial Use")
    print(brief.commercial_use_case)
    print("Theme")
    print(brief.theme)
    print("Required Objects")
    print(", ".join(brief.required_objects))
    print("Forbidden Objects")
    print(", ".join(brief.forbidden_objects))
    print("Palette")
    print(", ".join(brief.palette))
    print("Text Policy")
    print(brief.text_policy)
    print("Confidence")
    print(f"{brief.confidence}%")


def _print_image_blueprints(brief: Any) -> None:
    print("IMAGE BLUEPRINT")
    for blueprint in brief.image_blueprint:
        print(f"Image {blueprint.image_number} Role")
        print(blueprint.role)


def _print_prompt_diagnostics(prompts: tuple[Any, ...], seasonal_review: Any) -> None:
    for prompt in prompts:
        print("PROMPT DIAGNOSTIC")
        print("Image Number")
        print(prompt.image_number)
        print("Blueprint Role")
        print(prompt.blueprint_role)
        print("Required Objects")
        print(", ".join(prompt.required_objects))
        print("Forbidden Objects")
        print(", ".join(prompt.forbidden_objects))
        print("Text Policy")
        print(prompt.text_policy)
        print("Seasonal Decision")
        print(seasonal_review.production_decision)
        print("Final Negative Prompt")
        print(prompt.negative_prompt)
        print("Consistency Key")
        print(prompt.consistency_key)


def _combined_generation_prompt(prompts: tuple[Any, ...]) -> str:
    """Return one provider prompt containing all image roles and shared identity."""
    return "\n\n".join(
        f"IMAGE {prompt.image_number} ROLE: {prompt.blueprint_role}\n{prompt.prompt}"
        for prompt in prompts
    )


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
    "alphabet poster",
    "alphabet posters",
    "bridal shower printable",
    "wall art",
    "invitation",
    "party printable",
    "sticker sheet",
    "sticker sheets",
    "clipart",
    "digital illustration",
    "digital illustration collection",
    "illustration collection",
    "digital paper",
    "digital journal",
    "journal kit",
    "junk journal",
    "planner sticker",
    "planner stickers",
    "teacher printable",
    "teacher printables",
    "teacher wall art",
    "wedding planner",
}


def _normalize_product_type_expectation(value: str) -> str:
    normalized = re.sub(r"[-_]+", " ", value.casefold())
    normalized = re.sub(r"[^a-z0-9\s]+", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def _tokens_match_product_type(expected: str, actual: str) -> bool:
    if expected == actual:
        return True
    if actual in {f"{expected}s", f"{expected}es"}:
        return True
    if expected.endswith("y") and actual == f"{expected[:-1]}ies":
        return True
    if expected.endswith("s") and expected[:-1] == actual:
        return True
    return False


def _product_type_expectation_matches(expected: str, normalized_product_type: str) -> bool:
    normalized_expected = _normalize_product_type_expectation(expected)
    if normalized_expected in normalized_product_type:
        return True

    expected_tokens = normalized_expected.split()
    actual_tokens = normalized_product_type.split()
    token_count = len(expected_tokens)
    if not expected_tokens or len(actual_tokens) < token_count:
        return False

    for index in range(0, len(actual_tokens) - token_count + 1):
        window = actual_tokens[index : index + token_count]
        if all(
            _tokens_match_product_type(expected_token, actual_token)
            for expected_token, actual_token in zip(expected_tokens, window)
        ):
            return True
    return False


def _validate_product_type_expectation(
    job: ProductionJob,
    prompt_package: dict[str, Any],
) -> None:
    product_type = str(prompt_package.get("product_type") or "").strip()
    normalized = _normalize_product_type_expectation(product_type)
    if not normalized:
        raise RuntimeError("Missing product-type expectation before image generation.")
    if not any(
        _product_type_expectation_matches(expected, normalized)
        for expected in SUPPORTED_PRODUCT_TYPE_EXPECTATIONS
    ):
        raise RuntimeError(
            "Unsupported product-type expectation before image generation: "
            f"{product_type}."
        )
    if _product_type_expectation_matches("digital paper", normalized):
        _validate_digital_paper_prompt_package(prompt_package)


def _validate_digital_paper_prompt_package(prompt_package: dict[str, Any]) -> None:
    """Prevent paid digital-paper generation from using preview/mockup prompts."""
    prompt_text = " ".join(
        str(prompt_package.get(key) or "")
        for key in (
            "image_prompt",
            "final_prompt",
            "prompt",
            "commercial_requirements",
            "composition",
            "negative_prompt",
        )
    ).casefold()
    required_positive_concepts = (
        ("seamless",),
        ("tileable", "repeating"),
        ("single", "one pattern", "one customer-ready", "one continuous"),
        ("full-bleed", "fills the entire square canvas", "entire square canvas"),
    )
    required_negative_concepts = (
        ("no text",),
        ("no labels", "no label"),
        ("no mockup",),
        ("no collage",),
        ("no layered paper", "no layered paper sheets"),
        ("no multiple patterns", "one pattern per image"),
    )
    missing_positive = tuple(
        "/".join(options)
        for options in required_positive_concepts
        if not any(option in prompt_text for option in options)
    )
    missing_negative = tuple(
        "/".join(options)
        for options in required_negative_concepts
        if not any(option in prompt_text for option in options)
    )
    if missing_positive or missing_negative:
        pieces: list[str] = []
        if missing_positive:
            pieces.append(f"missing production concepts: {', '.join(missing_positive)}")
        if missing_negative:
            pieces.append(f"missing negative constraints: {', '.join(missing_negative)}")
        raise RuntimeError(
            "Digital Paper prompt is not customer-deliverable safe before image generation: "
            + "; ".join(pieces)
            + "."
        )


def _resolve_product_capability(
    job: ProductionJob,
    assets_dir: Path | None = None,
) -> Any:
    from project_aurora.production.product_capability_resolver import (
        ProductCapabilityResolver,
    )

    return ProductCapabilityResolver().resolve(
        product_name=job.product_name,
        product_type=job.category,
        category=job.category,
        assets_dir=assets_dir,
    )


def _ensure_required_layout_template(
    job: ProductionJob,
    job_paths: ProductFactoryJobPaths,
) -> None:
    """Create deterministic local templates required before paid image generation."""
    lowered = f"{job.product_name} {job.category}".casefold()
    if "sticker" not in lowered:
        return
    from project_aurora.production.layout_template_engine import LayoutTemplateEngine
    from project_aurora.production.merchant_specification import (
        MerchantSpecificationLibrary,
    )

    try:
        spec = MerchantSpecificationLibrary().resolve(job.category, job.product_name)
        item_count = int(spec.bundle_size)
    except RuntimeError:
        item_count = 8
    result = LayoutTemplateEngine().create_for_product(
        product_name=job.product_name,
        category=job.category,
        output_dir=job_paths.final_images_dir,
        item_count=item_count,
    )
    if result.status != "SUCCESS":
        raise ProductFactoryStageError(
            "product_capability",
            ("Sticker sheet layout/template could not be created.",),
        )


def _resolve_generation_image_count(
    job: ProductionJob,
    configured_count: int,
) -> int:
    """Return category-specific generation count required by merchant specs."""
    try:
        from project_aurora.production.merchant_specification import (
            MerchantSpecificationLibrary,
        )

        spec = MerchantSpecificationLibrary().resolve(job.category, job.product_name)
    except RuntimeError:
        return configured_count
    return max(configured_count, int(spec.bundle_size))


def _run_image_generation_chunks(
    *,
    engine: Any,
    prompt_package_id: str,
    provider: str,
    size: str,
    quality: str,
    background: str,
    output_format: str,
    number_of_images: int,
) -> Any:
    """Run provider image generation in chunks under provider request limits."""
    if number_of_images <= MAX_OPENAI_IMAGES_PER_REQUEST:
        return engine.run(
            prompt_package_id=prompt_package_id,
            provider=provider,
            image_type="product_asset",
            width=1024,
            height=1024,
            dpi=300,
            size=size,
            quality=quality,
            background=background,
            output_format=output_format,
            number_of_images=number_of_images,
        )
    remaining = number_of_images
    generated_files: list[str] = []
    warnings: list[str] = []
    errors: list[str] = []
    chunks: list[int] = []
    while remaining > 0:
        chunk_size = min(MAX_OPENAI_IMAGES_PER_REQUEST, remaining)
        chunks.append(chunk_size)
        result = engine.run(
            prompt_package_id=prompt_package_id,
            provider=provider,
            image_type="product_asset",
            width=1024,
            height=1024,
            dpi=300,
            size=size,
            quality=quality,
            background=background,
            output_format=output_format,
            number_of_images=chunk_size,
        )
        generated_files.extend(str(path) for path in getattr(result, "generated_files", ()))
        warnings.extend(str(item) for item in getattr(result, "warnings", ()))
        errors.extend(str(item) for item in getattr(result, "errors", ()))
        if str(getattr(result, "status", "")).upper() != "SUCCESS":
            errors.append(f"Image generation chunk of {chunk_size} failed.")
            break
        remaining -= chunk_size
    status = "SUCCESS" if not errors and len(generated_files) >= number_of_images else "FAILED"
    if status != "SUCCESS" and not errors:
        errors.append(
            f"Expected {number_of_images} generated files, found {len(generated_files)}."
        )
    return ImageGenerationBatchResult(
        status=status,
        generated_files=tuple(generated_files),
        image_paths=tuple(generated_files),
        warnings=tuple(warnings),
        errors=tuple(errors),
        metadata={"chunks": chunks, "requested_images": number_of_images},
    )


def _normalize_asset_result_files(
    *,
    job: ProductionJob,
    job_paths: ProductFactoryJobPaths,
    result: Any,
    file_attribute: str,
    source_stage: str,
) -> Any:
    """Namespace files for one job and write ownership records."""
    file_values = tuple(str(path) for path in getattr(result, file_attribute, ()) or ())
    files = tuple(Path(value) for value in file_values)
    if not files:
        return result
    if not all(file_path.exists() for file_path in files):
        return result
    normalized_files = _namespace_asset_files(
        job=job,
        files=files,
        source_stage=source_stage,
    )
    write_asset_manifest(
        manifest_path=manifest_path_for(job_paths.job_root),
        job_id=job.id,
        product_name=job.product_name,
        files=normalized_files,
        source_stage=source_stage,
    )
    updates = {file_attribute: tuple(str(path) for path in normalized_files)}
    if hasattr(result, "image_paths"):
        updates["image_paths"] = tuple(str(path) for path in normalized_files)
    if hasattr(result, "metadata"):
        updates["metadata"] = {
            **dict(getattr(result, "metadata", {}) or {}),
            "job_id": job.id,
            "product_slug": product_slug(job.product_name),
            "source_stage": source_stage,
            "asset_manifest": str(manifest_path_for(job_paths.job_root)),
        }
    try:
        return replace(result, **updates)
    except TypeError:
        values = dict(getattr(result, "__dict__", {}))
        values.update(updates)
        return SimpleNamespace(**values)


def _result_files_exist(result: Any, file_attribute: str) -> bool:
    """Return whether a result points to real files on disk."""
    file_values = tuple(str(path) for path in getattr(result, file_attribute, ()) or ())
    return bool(file_values) and all(Path(value).exists() for value in file_values)


def _namespace_asset_files(
    *,
    job: ProductionJob,
    files: tuple[Path, ...],
    source_stage: str,
) -> tuple[Path, ...]:
    """Rename current job assets with a job/product prefix."""
    prefix = f"{_slug_part(job.id)[:12]}_{product_slug(job.product_name)}"
    normalized: list[Path] = []
    for index, file_path in enumerate(files, start=1):
        clean_stem = _asset_stem_for_namespace(
            file_path=file_path,
            index=index,
            source_stage=source_stage,
        )
        if (
            file_path.name.casefold().startswith(prefix.casefold())
            and not _contains_legacy_product_stem(file_path)
        ):
            normalized.append(file_path)
            continue
        target = file_path.with_name(f"{prefix}_{clean_stem}{file_path.suffix.casefold()}")
        counter = 2
        while target.exists() and target != file_path:
            target = file_path.with_name(
                f"{prefix}_{clean_stem}_{counter}{file_path.suffix.casefold()}"
            )
            counter += 1
        if target != file_path:
            file_path.rename(target)
        normalized.append(target)
    return tuple(normalized)


def _asset_stem_for_namespace(
    *,
    file_path: Path,
    index: int,
    source_stage: str,
) -> str:
    """Return a clean current-job filename stem without legacy product text."""
    if source_stage == "image_generation":
        return f"{index:02d}"
    if source_stage == "commercial_export" and file_path.suffix.casefold() == ".png":
        return f"{index:02d}"
    return file_path.stem


def _contains_legacy_product_stem(path: Path) -> bool:
    """Return whether a filename still carries a known previous product stem."""
    name = path.name.casefold()
    return "strawberry_birthday_party_printable" in name


def _sanitize_final_asset_names(job: ProductionJob, job_paths: ProductFactoryJobPaths) -> None:
    """Rename current-job final assets that still contain legacy product stems."""
    files = _final_asset_files(job, job_paths.final_images_dir)
    if not files or not any(_contains_legacy_product_stem(path) for path in files):
        return
    normalized = _namespace_asset_files(
        job=job,
        files=files,
        source_stage="commercial_export",
    )
    write_asset_manifest(
        manifest_path=manifest_path_for(job_paths.job_root),
        job_id=job.id,
        product_name=job.product_name,
        files=normalized,
        source_stage="commercial_export",
    )


def _archive_existing_final_assets(job_paths: ProductFactoryJobPaths) -> None:
    """Move stale final assets aside before a fresh export."""
    if not job_paths.final_images_dir.exists():
        return
    candidates = tuple(
        path
        for path in sorted(job_paths.final_images_dir.glob("*"), key=lambda item: item.name)
        if path.is_file() and path.suffix.casefold() in {".png", ".jpg", ".jpeg", ".zip"}
    )
    if not candidates:
        return
    rejected_dir = (
        job_paths.job_root
        / "rejected"
        / f"final_product_images_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    )
    rejected_dir.mkdir(parents=True, exist_ok=True)
    for path in candidates:
        shutil.move(str(path), str(rejected_dir / path.name))


def _print_asset_ownership_diagnostics(
    diagnostics: tuple[Any, ...],
) -> None:
    """Print safe manifest diagnostics for asset ownership checks."""
    if not diagnostics:
        return
    print("ASSET OWNERSHIP")
    for item in diagnostics:
        print("Active Job ID")
        print(getattr(item, "active_job_id", ""))
        print("Active Product Slug")
        print(getattr(item, "active_product_slug", ""))
        print("Workspace")
        print(getattr(item, "workspace", ""))
        print("Asset Owner Job ID")
        print(getattr(item, "asset_owner_job_id", ""))
        print("Asset Owner Product Slug")
        print(getattr(item, "asset_owner_product_slug", ""))
        print("Filename")
        print(getattr(item, "filename", ""))
        print("Validation Result")
        print(getattr(item, "validation_result", ""))


def _resolve_export_category(job: ProductionJob) -> str:
    """Return the merchant category that controls final asset export."""
    try:
        from project_aurora.production.merchant_specification import (
            MerchantSpecificationLibrary,
        )

        return MerchantSpecificationLibrary().resolve(job.category, job.product_name).category
    except RuntimeError:
        return job.category


def _final_asset_files(job: ProductionJob, final_images_dir: Path) -> tuple[Path, ...]:
    """Return category-specific final deliverable files in deterministic order."""
    try:
        from project_aurora.production.merchant_specification import (
            MerchantSpecificationLibrary,
        )

        spec = MerchantSpecificationLibrary().resolve(job.category, job.product_name)
        suffixes = {f".{fmt.casefold()}" for fmt in spec.file_formats}
    except RuntimeError:
        suffixes = {".png"}
    return tuple(
        path
        for path in sorted(final_images_dir.glob("*"), key=lambda item: item.name)
        if path.is_file()
        and path.suffix.casefold() in suffixes
        and "preview" not in path.stem.casefold()
    )


def _ratio_label_from_final_file(path: Path) -> str:
    """Return wall-art ratio label encoded in a final filename."""
    stem = path.stem.casefold().replace("_", "x").replace("-", "x")
    for label in ("2x3", "3x4", "4x5", "11x14", "iso"):
        if label in stem:
            return label
    return ""


def _build_required_product_package(job: ProductionJob, final_images_dir: Path) -> Any | None:
    """Build a ZIP package when the merchant spec requires one."""
    try:
        from project_aurora.production.merchant_specification import (
            MerchantSpecificationLibrary,
        )
        from project_aurora.production.product_packager import ProductPackager

        spec = MerchantSpecificationLibrary().resolve(job.category, job.product_name)
    except RuntimeError:
        return None
    if spec.packaging != "ZIP":
        return None
    return ProductPackager().package(
        product_name=job.product_name,
        category=job.category,
        product_dir=final_images_dir,
    )


def _required_zip_package_file(job: ProductionJob, final_images_dir: Path) -> Path | None:
    """Return the required ZIP package file for ZIP-packaged products."""
    try:
        from project_aurora.production.merchant_specification import (
            MerchantSpecificationLibrary,
        )

        spec = MerchantSpecificationLibrary().resolve(job.category, job.product_name)
    except RuntimeError:
        return None
    if spec.packaging != "ZIP":
        return None
    packages = tuple(sorted(final_images_dir.glob("*.zip"), key=lambda item: item.name))
    if not packages:
        raise ProductFactoryStageError(
            "customer_download_upload",
            (f"{spec.category} requires a ZIP package before Etsy upload.",),
        )
    return packages[0]


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

    capability = _resolve_product_capability(job, assets_dir=job_paths.final_images_dir)
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
    if (
        ("dark" in product_lower or "moody" in product_lower or "academia" in product_lower)
        and "classroom" not in product_lower
        and ("teacher printable" in lowered or "bright classroom" in lowered or "kids room decor" in lowered)
    ):
        return False
    strawberry_terms = ("strawberry", "berry")
    party_terms = ("cupcake", "favor tag")
    if "strawberry" not in product_lower and any(term in lowered for term in strawberry_terms):
        return False
    if "party" not in product_lower and "birthday" not in product_lower and any(term in lowered for term in party_terms):
        return False
    return True
