"""Resume a Product Factory job after Etsy listing-image upload failure."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from time import sleep
from types import SimpleNamespace
from typing import Any, Callable

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(SRC_PATH))

from project_aurora.image_generation.commercial_image_exporter import (  # noqa: E402
    COMMERCIAL_IMAGE_COUNT,
    validate_commercial_png,
)
from project_aurora.integrations.etsy.etsy_client import EtsyClient  # noqa: E402
from project_aurora.integrations.etsy.etsy_config import EtsyConfig  # noqa: E402
from project_aurora.integrations.etsy.etsy_digital_file_service import (  # noqa: E402
    EtsyDigitalFileService,
)
from project_aurora.integrations.etsy.etsy_listing_image_policy import (  # noqa: E402
    MAX_LISTING_IMAGES,
    MIN_LISTING_IMAGES,
    MIN_STORYBOOK_LISTING_IMAGES,
)
from project_aurora.integrations.etsy.etsy_result import (  # noqa: E402
    EtsyImageUploadAttempt,
)
from project_aurora.image_generation.provider_registry import ImageProviderConfig  # noqa: E402
from project_aurora.image_generation.image_inspector import inspect_png  # noqa: E402
from project_aurora.config.local_env import load_local_env  # noqa: E402
from project_aurora.planning.production_queue_manager import (  # noqa: E402
    ProductionJob,
    ProductionQueueManager,
)
from project_aurora.production.product_factory import (  # noqa: E402
    REPORT_COLLECTION,
    DefaultProductFactoryStageRunner,
    ProductFactory,
    ProductFactoryJobPaths,
    _generation_plan_from_prompt,
    _ensure_listing_previews,
)
from project_aurora.production.product_image_family import (  # noqa: E402
    resolve_product_image_family,
)
from project_aurora.production.digital_download_builder import (  # noqa: E402
    DigitalDownloadBuilder,
)
from project_aurora.production.production_report import ProductionReport  # noqa: E402
from project_aurora.storage.csv_storage import CSVStorage  # noqa: E402
from project_aurora.storage.memory_manager import MemoryManager  # noqa: E402


QUEUE_PATH = PROJECT_ROOT / "data" / "aurora" / "production_queue" / "queue.json"
OPENAI_CONFIG_PATH = PROJECT_ROOT / "config" / "openai.yaml"


@dataclass(frozen=True, slots=True)
class ResumeResult:
    """Result of resuming one Product Factory job."""

    job_id: str
    etsy_listing_id: str
    resumed_from_stage: str
    images_already_present: int
    images_present_after: int
    digital_files_present_after: int
    images_uploaded_now: int
    downloads_uploaded: int
    final_status: str
    verification: str
    image_attempts: tuple[EtsyImageUploadAttempt, ...] = field(default_factory=tuple)
    errors: tuple[str, ...] = field(default_factory=tuple)


class ProductFactoryResumeService:
    """Resume an existing draft without recreating prior production stages."""

    def __init__(
        self,
        memory: MemoryManager,
        queue_manager: ProductionQueueManager,
        config: EtsyConfig,
        client: EtsyClient | None = None,
        sleeper: Callable[[float], None] = sleep,
        verification_timeout_seconds: float = 30.0,
        verification_poll_seconds: float = 2.0,
    ) -> None:
        self._memory = memory
        self._queue_manager = queue_manager
        self._config = config
        self._client = client or EtsyClient(config)
        self._sleeper = sleeper
        self._verification_timeout_seconds = verification_timeout_seconds
        self._verification_poll_seconds = verification_poll_seconds

    def resume(self, job_id: str) -> ResumeResult:
        """Resume a failed Product Factory job from its failed stage."""
        report_data = self._memory.load_record(REPORT_COLLECTION, job_id)
        listing_id = _existing_draft_id(report_data)
        failed_stage = str(report_data.get("failed_stage") or "")
        supported = {
            "image_generation",
            "image_qa",
            "commercial_export",
            "seo_generation",
            "taxonomy_resolution",
            "etsy_draft",
            "listing_image_upload",
            "customer_download_upload",
        }
        if failed_stage not in supported:
            raise RuntimeError(f"Unsupported failed stage for resume: {failed_stage}.")
        if failed_stage in {"listing_image_upload", "customer_download_upload"} and not listing_id:
            raise RuntimeError("Existing Etsy draft ID is required for resume.")
        if failed_stage == "customer_download_upload":
            return self._resume_customer_downloads(job_id, report_data, str(listing_id))
        if failed_stage != "listing_image_upload":
            return self._resume_with_product_factory(job_id, report_data, failed_stage, listing_id)
        return self._resume_listing_images(job_id, report_data, str(listing_id), failed_stage)

    def _resume_listing_images(
        self,
        job_id: str,
        report_data: dict[str, Any],
        listing_id: str,
        failed_stage: str,
    ) -> ResumeResult:
        final_images_dir = _final_images_dir_from_report(report_data)
        job = _job_by_id(self._queue_manager, job_id)
        try:
            prompt_package = self._memory.load_prompt_package(job_id)
        except FileNotFoundError:
            prompt_package = {}
        product_family = resolve_product_image_family(
            job.product_name,
            str(prompt_package.get("product_type") or job.category),
            job.category,
        ).family
        _valid_final_image_files(final_images_dir, product_family=product_family)
        listing_images_dir = _listing_images_dir_from_report(report_data)
        generation_plan = _generation_plan_from_prompt(job, prompt_package)
        if generation_plan.scene_required:
            StageAwareResumeRunner(
                memory=self._memory,
                etsy_config=self._config,
                image_config=ImageProviderConfig.from_file(OPENAI_CONFIG_PATH),
                existing_draft_id=listing_id,
                client=self._client,
            )._generate_validated_storybook_scene(
                job,
                prompt_package,
                _job_paths_from_report(report_data),
            )
        preview_count_before = len(tuple(listing_images_dir.glob("*.png")))
        _ensure_listing_previews(
            job,
            _job_paths_from_report(report_data),
            generation_mode=generation_plan.resolved_mode,
            art_direction_fingerprint=str(prompt_package.get("art_direction_fingerprint") or ""),
        )
        preview_count_after = len(tuple(listing_images_dir.glob("*.png")))
        if preview_count_before != preview_count_after:
            print("Listing previews regenerated during resume")
            print(preview_count_after)
        listing_files = _valid_listing_image_files(listing_images_dir)
        expected_listing_images = len(listing_files)
        existing_images = self._poll_listing_images(
            listing_id=listing_id,
            expected_count=0,
            endpoint_label="Pre-repair listing image lookup",
            timeout_seconds=0,
        )
        existing_by_rank = _existing_listing_images_by_rank(existing_images)
        attempts: list[EtsyImageUploadAttempt] = []

        for rank, image_path in enumerate(listing_files, start=1):
            if _image_already_present(existing_by_rank.get(rank), image_path, rank):
                continue
            attempts.append(self._upload_one(listing_id, image_path, rank))

        uploaded_now = sum(1 for attempt in attempts if attempt.status == "SUCCESS")
        failed_attempts = tuple(
            attempt for attempt in attempts if attempt.status != "SUCCESS"
        )
        verified_images = self._poll_listing_images(
            listing_id=listing_id,
            expected_count=expected_listing_images,
            endpoint_label="Post-upload listing image verification",
        )
        images_after = len(verified_images)
        if failed_attempts or images_after < expected_listing_images:
            reason = (
                f"expected {expected_listing_images} Etsy images, found "
                f"{images_after} after recovery"
            )
            updated = _updated_report(
                report_data=report_data,
                success=False,
                failed_stage="listing_image_upload",
                images=min(images_after, expected_listing_images),
                downloads=int(report_data.get("downloads") or 0),
                metadata_update={
                    "listing_image_upload": {
                        "status": "PARTIAL_FAILURE",
                        "etsy_listing_id": listing_id,
                        "images_already_present": len(existing_by_rank),
                        "images_uploaded_now": uploaded_now,
                        "images_present_after": images_after,
                        "expected_images": expected_listing_images,
                        "verification": "FAIL",
                        "failed": len(failed_attempts),
                        "attempts": [_attempt_to_dict(attempt) for attempt in attempts],
                    }
                },
                errors=tuple(
                    error
                    for attempt in failed_attempts
                    for error in attempt.errors
                )
                or (reason,),
            )
            self._save_report(updated)
            self._queue_manager.mark_failed(job_id)
            return ResumeResult(
                job_id=job_id,
                etsy_listing_id=listing_id,
                resumed_from_stage=failed_stage,
                images_already_present=len(existing_by_rank),
                images_present_after=images_after,
                digital_files_present_after=int(report_data.get("downloads") or 0),
                images_uploaded_now=uploaded_now,
                downloads_uploaded=0,
                final_status="NEEDS_REPAIR",
                verification="FAIL",
                image_attempts=tuple(attempts),
                errors=updated.errors,
            )

        digital_result = self._sync_customer_downloads(listing_id, final_images_dir)
        digital_total = len(
            self._poll_digital_files(
                listing_id=listing_id,
                expected_count=5,
                endpoint_label="Post-upload digital file verification",
            )
        )
        success = digital_result.status == "SUCCESS" and digital_total == 5
        final_status = "COMPLETED" if success else "NEEDS_REPAIR"
        verification = "PASS" if success else "FAIL"
        updated_report = _updated_report(
            report_data=report_data,
            success=success,
            failed_stage=None if success else "customer_download_upload",
            images=COMMERCIAL_IMAGE_COUNT,
            downloads=digital_total,
            metadata_update={
                "listing_image_upload": {
                    "status": "SUCCESS",
                        "etsy_listing_id": listing_id,
                        "images_already_present": len(existing_by_rank),
                        "images_uploaded_now": uploaded_now,
                        "images_present_after": images_after,
                        "expected_images": expected_listing_images,
                        "verification": "PASS",
                        "total_present": images_after,
                        "attempts": [_attempt_to_dict(attempt) for attempt in attempts],
                    },
                "customer_download_upload": digital_result,
            },
            errors=tuple(digital_result.errors) if not success else (),
        )
        self._save_report(updated_report)
        if success:
            self._queue_manager.mark_completed(job_id)
        else:
            self._queue_manager.mark_failed(job_id)

        return ResumeResult(
            job_id=job_id,
            etsy_listing_id=listing_id,
            resumed_from_stage=failed_stage,
            images_already_present=len(existing_by_rank),
            images_present_after=images_after,
            digital_files_present_after=digital_total,
            images_uploaded_now=uploaded_now,
            downloads_uploaded=int(digital_result.files_uploaded),
            final_status=final_status,
            verification=verification,
            image_attempts=tuple(attempts),
            errors=updated_report.errors,
        )

    def _resume_customer_downloads(
        self,
        job_id: str,
        report_data: dict[str, Any],
        listing_id: str,
    ) -> ResumeResult:
        final_images_dir = _final_images_dir_from_report(report_data)
        product_family = self._product_family(job_id)
        _valid_final_image_files(final_images_dir, product_family=product_family)
        digital_result = self._sync_customer_downloads(
            listing_id,
            final_images_dir,
            product_family=product_family,
        )
        digital_total = len(
            self._poll_digital_files(
                listing_id=listing_id,
                expected_count=5,
                endpoint_label="Post-upload digital file verification",
            )
        )
        success = digital_result.status == "SUCCESS" and digital_total == 5
        updated_report = _updated_report(
            report_data=report_data,
            success=success,
            failed_stage=None if success else "customer_download_upload",
            images=int(report_data.get("images") or COMMERCIAL_IMAGE_COUNT),
            downloads=digital_total,
            metadata_update={"customer_download_upload": digital_result},
            errors=tuple(digital_result.errors) if not success else (),
        )
        self._save_report(updated_report)
        if success:
            self._queue_manager.mark_completed(job_id)
        else:
            self._queue_manager.mark_failed(job_id)
        return ResumeResult(
            job_id=job_id,
            etsy_listing_id=listing_id,
            resumed_from_stage="customer_download_upload",
            images_already_present=int(report_data.get("images") or 0),
            images_present_after=int(report_data.get("images") or 0),
            digital_files_present_after=digital_total,
            images_uploaded_now=0,
            downloads_uploaded=int(digital_result.files_uploaded),
            final_status="COMPLETED" if success else "NEEDS_REPAIR",
            verification="PASS" if success else "FAIL",
            errors=updated_report.errors,
        )

    def _product_family(self, job_id: str) -> str:
        job = _job_by_id(self._queue_manager, job_id)
        try:
            prompt_package = self._memory.load_prompt_package(job_id)
        except FileNotFoundError:
            prompt_package = {}
        return resolve_product_image_family(
            job.product_name,
            str(prompt_package.get("product_type") or job.category),
            job.category,
        ).family

    def _sync_customer_downloads(
        self,
        listing_id: str,
        final_images_dir: Path,
        product_family: str = "",
    ) -> Any:
        digital_service = EtsyDigitalFileService(
            config=self._config,
            memory=self._memory,
            client=self._client,
        )
        png_result = digital_service.sync_digital_files(
            listing_id=listing_id,
            final_images_dir=final_images_dir,
            product_family=product_family,
        )
        _print_etsy_trace(
            heading="ETSY UPLOAD TRACE",
            listing_id=listing_id,
            endpoint=f"/shops/{self._config.shop_id}/listings/{listing_id}/files",
            response=_record_value(png_result),
            extra={
                "upload_endpoint": "uploadListingFile",
                "file_group": "customer PNG files",
            },
        )
        if png_result.status != "SUCCESS":
            return png_result

        zip_result = self._sync_customer_zip(
            listing_id=listing_id,
            final_images_dir=final_images_dir,
            digital_service=digital_service,
            product_family=product_family,
        )
        _print_etsy_trace(
            heading="ETSY UPLOAD TRACE",
            listing_id=listing_id,
            endpoint=f"/shops/{self._config.shop_id}/listings/{listing_id}/files",
            response=_record_value(zip_result),
            extra={
                "upload_endpoint": "uploadListingFile",
                "file_group": "customer ZIP file",
            },
        )
        files_uploaded = int(png_result.files_uploaded) + int(zip_result.files_uploaded)
        errors = tuple(png_result.errors) + tuple(zip_result.errors)
        status = "SUCCESS" if png_result.status == "SUCCESS" and zip_result.status == "SUCCESS" else "PARTIAL_FAILURE"
        return SimpleNamespace(
            status=status,
            files_uploaded=files_uploaded,
            errors=errors,
            to_dict=lambda: {
                "status": status,
                "png_sync": _record_value(png_result),
                "zip_sync": _record_value(zip_result),
                "files_uploaded": files_uploaded,
                "errors": list(errors),
            },
        )

    def _sync_customer_zip(
        self,
        *,
        listing_id: str,
        final_images_dir: Path,
        digital_service: EtsyDigitalFileService,
        product_family: str = "",
    ) -> Any:
        existing = self._poll_digital_files(
            listing_id=listing_id,
            expected_count=0,
            endpoint_label="Pre-repair digital file lookup",
            timeout_seconds=0,
        )
        zip_path = _ensure_customer_zip(
            final_images_dir,
            product_family=product_family,
        )
        if any(_digital_record_filename(record) == zip_path.name for record in existing):
            return SimpleNamespace(status="SUCCESS", files_uploaded=0, errors=())
        if len(existing) >= 5:
            return SimpleNamespace(
                status="PARTIAL_FAILURE",
                files_uploaded=0,
                errors=("Etsy already has 5 digital files; ZIP cannot be uploaded without exceeding the limit.",),
            )
        return digital_service.upload_digital_file(listing_id=listing_id, file_path=zip_path)

    def _resume_with_product_factory(
        self,
        job_id: str,
        report_data: dict[str, Any],
        failed_stage: str,
        listing_id: str | None,
    ) -> ResumeResult:
        job = _job_by_id(self._queue_manager, job_id)
        runner = StageAwareResumeRunner(
            memory=self._memory,
            etsy_config=self._config,
            client=self._client,
            existing_draft_id=listing_id,
            image_config=ImageProviderConfig.from_file(OPENAI_CONFIG_PATH),
            failed_stage=failed_stage,
        )
        report = ProductFactory(
            queue_manager=self._queue_manager,
            memory=self._memory,
            stage_runner=runner,
            dry_run=False,
            save_report=True,
        ).execute(job)
        return ResumeResult(
            job_id=job_id,
            etsy_listing_id=report.draft_id or listing_id or "",
            resumed_from_stage=failed_stage,
            images_already_present=4 if _image_reused(report) else 0,
            images_present_after=report.images,
            digital_files_present_after=report.downloads,
            images_uploaded_now=_images_uploaded_now(report),
            downloads_uploaded=report.downloads,
            final_status="COMPLETED" if report.success else "FAILED",
            verification="PASS" if report.success else "FAIL",
            errors=report.errors,
        )

    def _upload_one(
        self,
        listing_id: str,
        image_path: Path,
        rank: int,
    ) -> EtsyImageUploadAttempt:
        try:
            response = self._client.upload_listing_image(
                listing_id=listing_id,
                image_path=image_path,
                rank=rank,
            )
        except RuntimeError as error:
            return EtsyImageUploadAttempt(
                image_path=str(image_path),
                rank=rank,
                status="FAILED",
                errors=(str(error),),
            )
        _print_etsy_trace(
            heading="ETSY UPLOAD TRACE",
            listing_id=listing_id,
            endpoint=(
                f"/shops/{self._config.shop_id}/listings/{listing_id}/images"
            ),
            response=response,
            extra={
                "upload_endpoint": "uploadListingImage",
                "filename": image_path.name,
                "rank": rank,
            },
        )
        image_id = response.get("listing_image_id") or response.get("image_id")
        return EtsyImageUploadAttempt(
            image_path=str(image_path),
            rank=rank,
            status="SUCCESS",
            etsy_image_id=str(image_id) if image_id is not None else None,
            metadata={"response": response},
        )

    def _save_report(self, report: ProductionReport) -> None:
        self._memory.save_record(REPORT_COLLECTION, "latest", report.to_dict())
        self._memory.save_record(REPORT_COLLECTION, report.job_id, report.to_dict())

    def _verified_listing_images(self, listing_id: str) -> dict[int, dict[str, Any]]:
        return _existing_listing_images_by_rank(
            self._poll_listing_images(
                listing_id=listing_id,
                expected_count=0,
                endpoint_label="Listing image verification",
                timeout_seconds=0,
            )
        )

    def _verified_digital_file_count(self, listing_id: str) -> int:
        return len(
            self._poll_digital_files(
                listing_id=listing_id,
                expected_count=0,
                endpoint_label="Digital file verification",
                timeout_seconds=0,
            )
        )

    def _poll_listing_images(
        self,
        *,
        listing_id: str,
        expected_count: int,
        endpoint_label: str,
        timeout_seconds: float | None = None,
    ) -> tuple[dict[str, Any], ...]:
        endpoint = f"/listings/{listing_id}/images"
        return self._poll_etsy_results(
            listing_id=listing_id,
            endpoint=endpoint,
            endpoint_label=endpoint_label,
            expected_count=expected_count,
            count_label="Number of listing images returned",
            timeout_seconds=timeout_seconds,
        )

    def _poll_digital_files(
        self,
        *,
        listing_id: str,
        expected_count: int,
        endpoint_label: str,
        timeout_seconds: float | None = None,
    ) -> tuple[dict[str, Any], ...]:
        if not self._config.shop_id:
            raise RuntimeError("ETSY_SHOP_ID is required.")
        endpoint = f"/shops/{self._config.shop_id}/listings/{listing_id}/files"
        return self._poll_etsy_results(
            listing_id=listing_id,
            endpoint=endpoint,
            endpoint_label=endpoint_label,
            expected_count=expected_count,
            count_label="Number of digital files returned",
            timeout_seconds=timeout_seconds,
        )

    def _poll_etsy_results(
        self,
        *,
        listing_id: str,
        endpoint: str,
        endpoint_label: str,
        expected_count: int,
        count_label: str,
        timeout_seconds: float | None,
    ) -> tuple[dict[str, Any], ...]:
        timeout = self._verification_timeout_seconds if timeout_seconds is None else timeout_seconds
        deadline = datetime.now().timestamp() + timeout
        last_results: tuple[dict[str, Any], ...] = ()
        while True:
            raw = self._get_verification_json(endpoint)
            results = _results_from_raw(raw)
            last_results = results
            _print_etsy_trace(
                heading="ETSY VERIFICATION TRACE",
                listing_id=listing_id,
                endpoint=endpoint,
                response=raw,
                extra={
                    "verification_endpoint": endpoint_label,
                    count_label: len(results),
                    "expected_count": expected_count,
                },
            )
            if expected_count <= 0 or len(results) >= expected_count:
                return results
            if datetime.now().timestamp() >= deadline:
                print("ETSY VERIFICATION TIMEOUT")
                print("")
                print("Listing ID")
                print(listing_id)
                print("")
                print("Verification endpoint")
                print(endpoint)
                print("")
                print("Raw JSON")
                print(json.dumps(raw, indent=2, sort_keys=True))
                return last_results
            self._sleeper(self._verification_poll_seconds)

    def _get_verification_json(self, endpoint: str) -> dict[str, Any]:
        get_json = getattr(self._client, "get_json", None)
        if callable(get_json):
            return get_json(endpoint)
        if endpoint.endswith("/images"):
            return {"results": list(self._client.list_listing_images(endpoint.split("/")[-2]))}
        return {"results": list(self._client.list_listing_digital_files(endpoint.split("/")[-2]))}


class StageAwareResumeRunner(DefaultProductFactoryStageRunner):
    """Factory runner that preserves existing Etsy drafts and idempotent uploads."""

    def __init__(
        self,
        memory: MemoryManager,
        etsy_config: EtsyConfig,
        client: EtsyClient,
        existing_draft_id: str | None,
        image_config: ImageProviderConfig,
        failed_stage: str = "",
    ) -> None:
        super().__init__(
            memory=memory,
            etsy_config=etsy_config,
            image_config=image_config,
        )
        self._resume_client = client
        self._existing_draft_id = existing_draft_id
        self._failed_stage = failed_stage

    def compose_prompts(self, job: ProductionJob) -> Any:
        if self._failed_stage == "taxonomy_resolution":
            try:
                prompt_package = self._memory.load_prompt_package(job.id)
            except FileNotFoundError:
                prompt_package = {}
            if prompt_package:
                return SimpleNamespace(
                    status="SUCCESS",
                    final_prompt=str(prompt_package.get("image_prompt") or ""),
                    warnings=("Reused persisted prompt package during taxonomy recovery.",),
                    errors=(),
                )
        result = super().compose_prompts(job)
        if self._failed_stage == "image_qa":
            try:
                prompt_package = self._memory.load_prompt_package(job.id)
            except FileNotFoundError:
                prompt_package = {}
            print("PROMPT CORRECTION")
            print("")
            print("Product")
            print(job.product_name)
            print("")
            print("Corrected Category")
            print(job.category)
            print("")
            print("Corrected Style")
            print(prompt_package.get("style", ""))
            print("")
            print("Corrected Composition")
            print(prompt_package.get("composition", ""))
            print("")
            print("Negative Constraints")
            for constraint in prompt_package.get("negative_prompt", "").split(","):
                cleaned = constraint.strip()
                if cleaned:
                    print(cleaned)
        return result

    def generate_images(self, job: ProductionJob) -> Any:
        if self._failed_stage == "image_qa":
            _archive_rejected_generated_images(self.job_paths(job).generated_images_dir)
        return super().generate_images(job)

    def create_etsy_draft(self, job: ProductionJob, seo_package: Any) -> Any:
        if self._existing_draft_id:
            return type(
                "DraftReuse",
                (),
                {
                    "status": "DRAFT_CREATED",
                    "etsy_listing_id": self._existing_draft_id,
                    "warnings": ("Reused existing Etsy draft during resume.",),
                    "errors": (),
                },
            )()
        return super().create_etsy_draft(job, seo_package)

    def upload_listing_images(self, job: ProductionJob) -> Any:
        listing_id = self._existing_draft_id or _latest_draft_id(self._memory)
        if not listing_id:
            raise RuntimeError("Existing Etsy draft ID is required for image sync.")
        try:
            prompt_package = self._memory.load_prompt_package(job.id)
        except FileNotFoundError:
            prompt_package = {}
        product_family = resolve_product_image_family(
            job.product_name,
            str(prompt_package.get("product_type") or job.category),
            job.category,
        ).family
        _valid_final_image_files(
            self.job_paths(job).final_images_dir,
            product_family=product_family,
        )
        generation_plan = _generation_plan_from_prompt(job, prompt_package)
        if generation_plan.scene_required:
            self._generate_validated_storybook_scene(job, prompt_package, self.job_paths(job))
        _ensure_listing_previews(
            job,
            self.job_paths(job),
            generation_mode=generation_plan.resolved_mode,
            art_direction_fingerprint=str(prompt_package.get("art_direction_fingerprint") or ""),
        )
        listing_files = _valid_listing_image_files(self.job_paths(job).listing_images_dir)
        expected_listing_images = len(listing_files)
        existing = self._resume_client.list_listing_images(listing_id)
        existing_by_rank = _existing_listing_images_by_rank(existing)
        attempts: list[EtsyImageUploadAttempt] = []
        for rank, image_path in enumerate(listing_files, start=1):
            if _image_already_present(existing_by_rank.get(rank), image_path, rank):
                continue
            response = self._resume_client.upload_listing_image(listing_id, image_path, rank)
            image_id = response.get("listing_image_id") or response.get("image_id")
            attempts.append(
                EtsyImageUploadAttempt(
                    image_path=str(image_path),
                    rank=rank,
                    status="SUCCESS",
                    etsy_image_id=str(image_id) if image_id is not None else None,
                    metadata={"response": response},
                )
            )
        verified = _existing_listing_images_by_rank(self._resume_client.list_listing_images(listing_id))
        images_after = len(verified)
        errors = ()
        status = "SUCCESS"
        failed = 0
        if images_after < expected_listing_images:
            status = "PARTIAL_FAILURE"
            failed = 1
            errors = (
                f"expected {expected_listing_images} Etsy images, found "
                f"{images_after} after recovery",
            )
        return SimpleNamespace(
            status=status,
            etsy_listing_id=listing_id,
            images_uploaded=len(attempts),
            images_already_present=len(existing_by_rank),
            images_present_after=images_after,
            expected_images=expected_listing_images,
            failed=failed,
            warnings=(),
            errors=errors,
        )

    def upload_customer_downloads(self, job: ProductionJob, listing_id: str | None) -> Any:
        resolved_listing_id = listing_id or self._existing_draft_id or _latest_draft_id(self._memory)
        try:
            prompt_package = self._memory.load_prompt_package(job.id)
        except FileNotFoundError:
            prompt_package = {}
        product_family = resolve_product_image_family(
            job.product_name,
            str(prompt_package.get("product_type") or job.category),
            job.category,
        ).family
        return EtsyDigitalFileService(
            config=self._etsy_config,
            memory=self._memory,
            client=self._resume_client,
        ).sync_digital_files(
            listing_id=resolved_listing_id,
            final_images_dir=self.job_paths(job).final_images_dir,
            product_family=product_family,
        )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse resume CLI arguments."""
    parser = argparse.ArgumentParser(description="Resume one Product Factory job.")
    parser.add_argument("--job-id", required=True, help="Production queue job id.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    """Resume a failed Product Factory job safely."""
    args = parse_args(argv)
    load_local_env(PROJECT_ROOT / "config" / "aurora.local.env")
    memory = MemoryManager(storage=CSVStorage(base_path=PROJECT_ROOT / "data" / "aurora"))
    queue_manager = ProductionQueueManager(queue_path=QUEUE_PATH)
    config = EtsyConfig.from_environment(PROJECT_ROOT / "config" / "etsy.yaml")
    try:
        result = ProductFactoryResumeService(
            memory=memory,
            queue_manager=queue_manager,
            config=config,
        ).resume(args.job_id)
    except RuntimeError as error:
        print_resume_error(args.job_id, error)
        raise SystemExit(1) from error
    print_resume_result(result)
    if result.final_status != "COMPLETED":
        raise SystemExit(1)


def print_resume_result(result: ResumeResult) -> None:
    """Print the resume result."""
    print("PRODUCT FACTORY RESUME")
    print("")
    print("Existing Draft ID")
    print(result.etsy_listing_id)
    print("")
    print("Resuming From Stage")
    print(result.resumed_from_stage)
    print("")
    print("Images Already Present")
    print(result.images_already_present)
    print("")
    print("Images Present After")
    print(result.images_present_after)
    print("")
    print("Images Uploaded Now")
    print(result.images_uploaded_now)
    print("")
    print("Downloads Uploaded")
    print(result.downloads_uploaded)
    print("")
    print("Digital Files Present After")
    print(result.digital_files_present_after)
    print("")
    print("Verification")
    print(result.verification)
    print("")
    print("Final Status")
    print(result.final_status)
    if result.errors:
        print("")
        print("Errors")
        for error in result.errors:
            print(error)


def print_resume_error(job_id: str, error: RuntimeError) -> None:
    """Print a concise recovery summary for resume failures."""
    print("PRODUCT FACTORY RESUME")
    print("")
    print("Job ID")
    print(job_id)
    print("")
    print("Final Status")
    print("FAILED")
    print("")
    print("Recovery Summary")
    print(str(error))


def _existing_draft_id(report_data: dict[str, Any]) -> str | None:
    draft_id = report_data.get("draft_id")
    if isinstance(draft_id, str) and draft_id.strip():
        return draft_id.strip()
    etsy_draft = report_data.get("metadata", {}).get("etsy_draft")
    if isinstance(etsy_draft, dict):
        listing_id = etsy_draft.get("etsy_listing_id")
        if isinstance(listing_id, str) and listing_id.strip():
            return listing_id.strip()
    return None


def _final_images_dir_from_report(report_data: dict[str, Any]) -> Path:
    job_paths = report_data.get("job_paths")
    if not isinstance(job_paths, dict):
        raise RuntimeError("ProductionReport does not include job_paths.")
    value = job_paths.get("final_product_images_dir")
    if not isinstance(value, str) or not value.strip():
        raise RuntimeError("ProductionReport does not include final images path.")
    return Path(value)


def _listing_images_dir_from_report(report_data: dict[str, Any]) -> Path:
    job_paths = report_data.get("job_paths")
    if not isinstance(job_paths, dict):
        raise RuntimeError("ProductionReport does not include job_paths.")
    value = job_paths.get("listing_images_dir")
    if isinstance(value, str) and value.strip():
        return Path(value)
    final_images_dir = _final_images_dir_from_report(report_data)
    return final_images_dir.parent / "listing_images"


def _job_paths_from_report(report_data: dict[str, Any]) -> ProductFactoryJobPaths:
    job_paths = report_data.get("job_paths")
    if not isinstance(job_paths, dict):
        raise RuntimeError("ProductionReport does not include job_paths.")
    final_images_dir = _final_images_dir_from_report(report_data)
    listing_images_dir = _listing_images_dir_from_report(report_data)
    job_root_value = job_paths.get("job_root")
    job_root = Path(str(job_root_value)) if job_root_value else final_images_dir.parent
    generated_value = job_paths.get("generated_images_dir")
    storybook_value = job_paths.get("storybook_scenes_dir")
    downloads_value = job_paths.get("digital_downloads_dir")
    return ProductFactoryJobPaths(
        job_root=job_root,
        generated_images_dir=(
            Path(str(generated_value)) if generated_value else job_root / "generated_images"
        ),
        final_images_dir=final_images_dir,
        storybook_scenes_dir=(
            Path(str(storybook_value)) if storybook_value else job_root / "storybook_scenes"
        ),
        listing_images_dir=listing_images_dir,
        digital_downloads_dir=(
            Path(str(downloads_value)) if downloads_value else job_root / "digital_downloads"
        ),
    )


def _valid_final_image_files(
    final_images_dir: Path,
    product_family: str = "",
) -> tuple[Path, ...]:
    if final_images_dir.name != "final_product_images":
        raise RuntimeError("Resume must use job final_product_images directory.")
    files = tuple(sorted(final_images_dir.glob("*.png"), key=lambda path: path.name))
    if len(files) != COMMERCIAL_IMAGE_COUNT:
        raise RuntimeError(
            f"Expected exactly {COMMERCIAL_IMAGE_COUNT} final PNG files, "
            f"found {len(files)}."
        )
    errors = tuple(
        f"{path.name}: {error}"
        for path in files
        for error in validate_commercial_png(path, product_family=product_family)
    )
    if errors:
        raise RuntimeError("Invalid final image files: " + "; ".join(errors))
    return files


def _valid_listing_image_files(listing_images_dir: Path) -> tuple[Path, ...]:
    if listing_images_dir.name != "listing_images":
        raise RuntimeError("Resume must use job listing_images directory.")
    files = tuple(sorted(listing_images_dir.glob("*.png"), key=lambda path: path.name))
    minimum = (
        MIN_STORYBOOK_LISTING_IMAGES
        if _listing_manifest_family(listing_images_dir) == "STORYBOOK"
        else MIN_LISTING_IMAGES
    )
    if not minimum <= len(files) <= MAX_LISTING_IMAGES:
        raise RuntimeError(
            f"Expected between {minimum} and {MAX_LISTING_IMAGES} "
            f"listing PNG files, found {len(files)}."
        )
    errors = tuple(
        f"{path.name}: invalid listing preview ({inspect_png(path).classification})"
        for path in files
        if not inspect_png(path).is_valid
    )
    if errors:
        raise RuntimeError("Invalid listing image files: " + "; ".join(errors))
    return files


def _listing_manifest_family(listing_images_dir: Path) -> str:
    manifest_path = listing_images_dir / "preview_manifest.json"
    if not manifest_path.exists():
        return ""
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return ""
    if not isinstance(manifest, dict):
        return ""
    return str(manifest.get("listing_family") or "").strip().upper()


def _ensure_customer_zip(
    final_images_dir: Path,
    product_family: str = "",
) -> Path:
    digital_downloads_dir = final_images_dir.parent / "digital_downloads"
    safe_name = _safe_customer_zip_name(final_images_dir.parent.name)
    existing_zips = tuple(sorted(digital_downloads_dir.glob("*.zip"), key=lambda path: path.name))
    for zip_path in existing_zips:
        if zip_path.name == safe_name:
            return zip_path
    for zip_path in existing_zips:
        if 3 <= len(zip_path.name) <= 70 and all(
            char.isalnum() or char in {"-", "_", "."} for char in zip_path.name
        ):
            return zip_path
    result = DigitalDownloadBuilder(
        final_images_dir=final_images_dir,
        output_dir=digital_downloads_dir,
        zip_filename=safe_name,
        product_family=product_family,
    ).build()
    if result.status != "SUCCESS" or not result.zip_path:
        raise RuntimeError(
            "Digital download ZIP could not be built: "
            + "; ".join(result.errors or ("unknown error",))
        )
    return Path(result.zip_path)


def _safe_customer_zip_name(job_folder_name: str) -> str:
    parts = job_folder_name.split("_")
    slug = "_".join(parts[5:]) if len(parts) > 5 else job_folder_name
    cleaned = "".join(
        char if char.isalnum() or char in {"-", "_"} else "_"
        for char in slug.strip("_").casefold()
    ).strip("_")
    if not cleaned:
        cleaned = "aurora_customer_files"
    max_stem_length = 66
    return f"{cleaned[:max_stem_length].strip('_')}.zip"


def _digital_record_filename(record: dict[str, object]) -> str:
    value = (
        record.get("filename")
        or record.get("file_name")
        or record.get("name")
        or record.get("display_name")
    )
    return Path(str(value)).name if value else ""


def _archive_rejected_generated_images(generated_images_dir: Path) -> None:
    """Move image-QA rejected source PNGs out of the active generation folder."""
    if not generated_images_dir.exists():
        return
    pngs = tuple(sorted(generated_images_dir.glob("*.png"), key=lambda path: path.name))
    if not pngs:
        return
    rejected_root = generated_images_dir / "rejected"
    rejected_root.mkdir(parents=True, exist_ok=True)
    attempt_index = 1
    while (rejected_root / f"attempt_{attempt_index}").exists():
        attempt_index += 1
    if attempt_index > 2:
        raise RuntimeError("Maximum image QA regeneration attempts reached for this job.")
    attempt_dir = rejected_root / f"attempt_{attempt_index}"
    attempt_dir.mkdir(parents=True, exist_ok=False)
    for path in pngs:
        shutil.move(str(path), str(attempt_dir / path.name))


def _existing_listing_images_by_rank(
    records: tuple[dict[str, Any], ...],
) -> dict[int, dict[str, Any]]:
    by_rank: dict[int, dict[str, Any]] = {}
    for record in records:
        rank = _rank_from_record(record)
        if rank is not None:
            by_rank[rank] = record
    return by_rank


def _image_already_present(
    record: dict[str, Any] | None,
    image_path: Path,
    rank: int,
) -> bool:
    if record is None:
        return False
    filename = _filename_from_record(record)
    if filename is None:
        return _rank_from_record(record) == rank
    return filename == image_path.name


def _rank_from_record(record: dict[str, Any]) -> int | None:
    for key in ("rank", "image_rank", "listing_image_rank"):
        value = record.get(key)
        if value is not None:
            try:
                return int(value)
            except (TypeError, ValueError):
                return None
    return None


def _filename_from_record(record: dict[str, Any]) -> str | None:
    for key in ("filename", "file_name", "name"):
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            return Path(value).name
    return None


def _digital_total_present(result: Any) -> int:
    total = result.metadata.get("total_present")
    if isinstance(total, int):
        return total
    already_present = result.metadata.get("already_present")
    if isinstance(already_present, list):
        return len(already_present) + int(result.files_uploaded)
    return int(result.files_uploaded)


def _updated_report(
    report_data: dict[str, Any],
    success: bool,
    failed_stage: str | None,
    images: int,
    downloads: int,
    metadata_update: dict[str, Any],
    errors: tuple[str, ...],
) -> ProductionReport:
    metadata = dict(report_data.get("metadata") or {})
    metadata.update(
        {
            key: _record_value(value)
            for key, value in metadata_update.items()
        }
    )
    return ProductionReport(
        job_id=str(report_data["job_id"]),
        product=str(report_data["product"]),
        style=str(report_data["style"]),
        draft_id=_existing_draft_id(report_data),
        images=images,
        downloads=downloads,
        time=float(report_data.get("time") or 0),
        success=success,
        failed_stage=failed_stage,
        warnings=tuple(str(item) for item in report_data.get("warnings", ())),
        errors=errors,
        job_paths=dict(report_data.get("job_paths") or {}),
        metadata=metadata,
        created_at=datetime.now(),
    )


def _record_value(value: Any) -> Any:
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        return to_dict()
    if hasattr(value, "__dataclass_fields__"):
        return {
            key: _record_value(getattr(value, key))
            for key in value.__dataclass_fields__
        }
    if isinstance(value, tuple):
        return [_record_value(item) for item in value]
    if isinstance(value, list):
        return [_record_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _record_value(item) for key, item in value.items()}
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "__dict__"):
        return {
            key: _record_value(item)
            for key, item in vars(value).items()
            if not callable(item)
        }
    return value


def _attempt_to_dict(attempt: EtsyImageUploadAttempt) -> dict[str, Any]:
    return {
        "image_path": attempt.image_path,
        "rank": attempt.rank,
        "status": attempt.status,
        "etsy_image_id": attempt.etsy_image_id,
        "errors": list(attempt.errors),
        "warnings": list(attempt.warnings),
        "metadata": attempt.metadata,
    }


def _results_from_raw(raw: dict[str, Any]) -> tuple[dict[str, Any], ...]:
    results = raw.get("results", ())
    if isinstance(results, list):
        return tuple(item for item in results if isinstance(item, dict))
    if isinstance(results, tuple):
        return tuple(item for item in results if isinstance(item, dict))
    return ()


def _print_etsy_trace(
    *,
    heading: str,
    listing_id: str,
    endpoint: str,
    response: Any,
    extra: dict[str, Any] | None = None,
) -> None:
    payload = _record_value(response)
    print(heading)
    print("")
    print("Timestamp")
    print(datetime.now().isoformat())
    print("")
    print("Listing ID")
    print(listing_id)
    print("")
    print("Draft ID")
    print(listing_id)
    print("")
    if extra:
        upload_endpoint = extra.get("upload_endpoint")
        if upload_endpoint:
            print("Upload endpoint")
            print(endpoint)
            print("")
            print("Upload response")
            print(json.dumps(payload, indent=2, sort_keys=True))
            print("")
        verification_endpoint = extra.get("verification_endpoint")
        if verification_endpoint:
            print("Verification endpoint")
            print(endpoint)
            print("")
            print("Verification response")
            print(json.dumps(payload, indent=2, sort_keys=True))
            print("")
        for key, value in extra.items():
            if key in {"upload_endpoint", "verification_endpoint"}:
                continue
            label = key if key.startswith("Number of ") else str(key).replace("_", " ").title()
            print(label)
            print(value)
            print("")
    print("Raw JSON")
    print(json.dumps(payload, indent=2, sort_keys=True))
    print("")


def _job_by_id(queue_manager: ProductionQueueManager, job_id: str) -> ProductionJob:
    for job in queue_manager.list_jobs():
        if job.id == job_id:
            return job
    raise RuntimeError(f"Production job not found: {job_id}.")


def _latest_draft_id(memory: MemoryManager) -> str | None:
    try:
        draft = memory.load_etsy_draft_result()
    except FileNotFoundError:
        return None
    value = draft.get("etsy_listing_id")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _image_reused(report: ProductionReport) -> bool:
    image_generation = report.metadata.get("image_generation")
    if not isinstance(image_generation, dict):
        return False
    warnings = image_generation.get("warnings", ())
    return isinstance(warnings, list | tuple) and any(
        "reused existing" in str(warning).casefold() for warning in warnings
    )


def _images_uploaded_now(report: ProductionReport) -> int:
    listing_upload = report.metadata.get("listing_image_upload")
    if isinstance(listing_upload, dict):
        value = listing_upload.get("images_uploaded") or listing_upload.get("images_uploaded_now")
        if isinstance(value, int):
            return value
    return 0


if __name__ == "__main__":
    main()
