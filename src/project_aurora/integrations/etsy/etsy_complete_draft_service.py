"""Create a complete Etsy draft with images and digital download file."""

from __future__ import annotations

from pathlib import Path

from project_aurora.integrations.etsy.etsy_client import EtsyClient
from project_aurora.integrations.etsy.etsy_config import EtsyConfig
from project_aurora.integrations.etsy.etsy_digital_file_service import (
    EtsyDigitalFileService,
)
from project_aurora.integrations.etsy.etsy_draft_service import EtsyDraftService
from project_aurora.integrations.etsy.etsy_image_upload_service import (
    EtsyImageUploadService,
)
from project_aurora.integrations.etsy.etsy_result import EtsyCompleteDraftResult
from project_aurora.listing.listing_package import (
    READY_FOR_ETSY_DRAFT,
    ListingPackage,
)
from project_aurora.production.digital_download_builder import DigitalDownloadBuilder
from project_aurora.seo.seo_engine import SEOEngine
from project_aurora.storage.memory_manager import MemoryManager


PRODUCT_DATA = {
    "product_name": "Summer Strawberry Birthday Collection",
    "product_type": "Party Printable Bundle",
    "target_buyer": "Parents planning girls' summer birthday parties",
}


class EtsyCompleteDraftService:
    """Run Aurora's permanent Etsy draft creation workflow."""

    def __init__(
        self,
        config: EtsyConfig,
        memory: MemoryManager,
        final_images_dir: Path,
        digital_downloads_dir: Path,
        client: EtsyClient | None = None,
    ) -> None:
        self._config = config
        self._memory = memory
        self._final_images_dir = final_images_dir
        self._digital_downloads_dir = digital_downloads_dir
        self._client = client or EtsyClient(config)

    def run(self) -> EtsyCompleteDraftResult:
        """Create draft, upload images, upload digital ZIP, then stop."""
        if self._config.is_mock_mode:
            result = self._result(
                status="CONFIGURATION_REQUIRED",
                errors=("AURORA_ETSY_MODE must be live.",),
                failed_stage="configuration",
            )
            self._save(result)
            return result

        seo_package = SEOEngine().build_package(PRODUCT_DATA)
        image_files = self._final_image_files()
        listing_package = ListingPackage(
            product_name=PRODUCT_DATA["product_name"],
            collection_name=PRODUCT_DATA["product_name"],
            listing_status=READY_FOR_ETSY_DRAFT,
            seo_package_id="latest",
            prompt_package_id="latest",
            approved_mockup_files=tuple(str(path) for path in image_files),
            approved_generated_image_files=tuple(str(path) for path in image_files),
            is_digital_download=True,
            price=1.99,
        )

        draft_result = EtsyDraftService(
            config=self._config,
            memory=self._memory,
            client=self._client,
        ).create_draft(
            listing_package=listing_package,
            seo_package=seo_package,
        )
        if draft_result.status != "DRAFT_CREATED" or not draft_result.etsy_listing_id:
            result = self._result(
                status=draft_result.status,
                draft_created=False,
                errors=draft_result.errors,
                warnings=draft_result.warnings,
                failed_stage="draft_creation",
            )
            self._save(result)
            return result

        listing_id = draft_result.etsy_listing_id
        completed = ["draft_created"]

        image_result = EtsyImageUploadService(
            config=self._config,
            memory=self._memory,
            images_dir=self._final_images_dir,
            client=self._client,
        ).upload_latest_draft_images()
        if image_result.status != "SUCCESS":
            result = self._result(
                status="PARTIAL_FAILURE",
                etsy_listing_id=listing_id,
                draft_url=draft_result.draft_url,
                draft_created=True,
                images_uploaded=image_result.images_uploaded,
                image_count=image_result.images_found,
                completed_stages=tuple(completed),
                failed_stage="image_upload",
                errors=image_result.errors,
                warnings=image_result.warnings,
            )
            self._save(result)
            return result
        completed.append("images_uploaded")

        download_result = DigitalDownloadBuilder(
            final_images_dir=self._final_images_dir,
            output_dir=self._digital_downloads_dir,
        ).build()
        if download_result.status != "SUCCESS" or not download_result.zip_path:
            result = self._result(
                status="PARTIAL_FAILURE",
                etsy_listing_id=listing_id,
                draft_url=draft_result.draft_url,
                draft_created=True,
                images_uploaded=image_result.images_uploaded,
                image_count=image_result.images_found,
                completed_stages=tuple(completed),
                failed_stage="digital_download_package",
                errors=download_result.errors,
            )
            self._save(result)
            return result
        completed.append("digital_download_package_created")

        digital_result = EtsyDigitalFileService(
            config=self._config,
            memory=self._memory,
            client=self._client,
        ).upload_digital_file(
            listing_id=listing_id,
            file_path=Path(download_result.zip_path),
        )
        if digital_result.status != "SUCCESS":
            result = self._result(
                status="PARTIAL_FAILURE",
                etsy_listing_id=listing_id,
                draft_url=draft_result.draft_url,
                draft_created=True,
                images_uploaded=image_result.images_uploaded,
                image_count=image_result.images_found,
                digital_file_path=download_result.zip_path,
                completed_stages=tuple(completed),
                failed_stage="digital_file_upload",
                errors=digital_result.errors,
                warnings=digital_result.warnings,
            )
            self._save(result)
            return result
        completed.append("digital_file_uploaded")

        result = self._result(
            status="SUCCESS",
            etsy_listing_id=listing_id,
            draft_url=draft_result.draft_url,
            draft_created=True,
            images_uploaded=image_result.images_uploaded,
            image_count=image_result.images_found,
            digital_file_uploaded=True,
            digital_file_path=digital_result.digital_file_path,
            completed_stages=tuple(completed),
        )
        self._save(result)
        return result

    def _final_image_files(self) -> tuple[Path, ...]:
        if not self._final_images_dir.exists():
            return ()
        return tuple(sorted(self._final_images_dir.glob("*.png"), key=lambda p: p.name))

    @staticmethod
    def _result(
        status: str,
        etsy_listing_id: str | None = None,
        draft_url: str | None = None,
        draft_created: bool = False,
        images_uploaded: int = 0,
        image_count: int = 0,
        digital_file_uploaded: bool = False,
        digital_file_path: str | None = None,
        completed_stages: tuple[str, ...] = (),
        failed_stage: str | None = None,
        warnings: tuple[str, ...] = (),
        errors: tuple[str, ...] = (),
    ) -> EtsyCompleteDraftResult:
        return EtsyCompleteDraftResult(
            etsy_listing_id=etsy_listing_id,
            draft_url=draft_url,
            draft_created=draft_created,
            images_uploaded=images_uploaded,
            image_count=image_count,
            digital_file_uploaded=digital_file_uploaded,
            digital_file_path=digital_file_path,
            price=1.99,
            status=status,
            completed_stages=completed_stages,
            failed_stage=failed_stage,
            warnings=warnings,
            errors=errors,
        )

    def _save(self, result: EtsyCompleteDraftResult) -> None:
        self._memory.save_etsy_complete_draft_result(result)
