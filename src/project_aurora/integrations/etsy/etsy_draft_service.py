"""Aurora Etsy draft creation service."""

from __future__ import annotations

from project_aurora.integrations.etsy.etsy_client import EtsyClient
from project_aurora.integrations.etsy.etsy_config import EtsyConfig
from project_aurora.integrations.etsy.etsy_listing_mapper import (
    EtsyListingMapper,
)
from project_aurora.integrations.etsy.etsy_result import EtsyDraftResult
from project_aurora.listing.listing_package import (
    READY_FOR_ETSY_DRAFT,
    ListingPackage,
)
from project_aurora.seo.seo_package import SEOPackage
from project_aurora.storage.memory_manager import MemoryManager


class EtsyDraftService:
    """Coordinate Aurora listing data into Etsy draft creation."""

    def __init__(
        self,
        config: EtsyConfig,
        memory: MemoryManager | None = None,
        client: EtsyClient | None = None,
        mapper: EtsyListingMapper | None = None,
    ) -> None:
        self._config = config
        self._memory = memory
        self._client = client or EtsyClient(config)
        self._mapper = mapper or EtsyListingMapper()

    def create_draft(
        self,
        listing_package: ListingPackage,
        seo_package: SEOPackage,
    ) -> EtsyDraftResult:
        """Validate and create an Etsy draft listing."""
        if listing_package.listing_status != READY_FOR_ETSY_DRAFT:
            result = EtsyDraftResult(
                status="VALIDATION_FAILED",
                etsy_listing_id=None,
                draft_url=None,
                errors=("Listing is not READY_FOR_ETSY_DRAFT.",),
                metadata={"api_called": False},
            )
            self._save_result(result)
            return result

        payload = self._mapper.map_to_draft(
            listing_package=listing_package,
            seo_package=seo_package,
            config=self._config,
        )
        validation_errors = self._mapper.validate_payload(payload)
        if validation_errors:
            result = EtsyDraftResult(
                status="VALIDATION_FAILED",
                etsy_listing_id=None,
                draft_url=None,
                errors=validation_errors,
                metadata={"api_called": False},
            )
            self._save_result(result)
            return result

        if not self._config.is_mock_mode:
            missing = self._config.validate_for_api(
                is_digital=payload.is_digital
            )
            if missing:
                result = EtsyDraftResult(
                    status="CONFIGURATION_REQUIRED",
                    etsy_listing_id=None,
                    draft_url=None,
                    errors=(
                        "Missing Etsy configuration: "
                        f"{', '.join(missing)}.",
                    ),
                    metadata={
                        "api_called": False,
                        "missing": missing,
                        "mode": self._config.mode,
                    },
                )
                self._save_result(result)
                return result

        result = self._client.create_draft_listing(payload)
        self._save_result(result)
        return result

    def _save_result(self, result: EtsyDraftResult) -> None:
        if self._memory is not None:
            self._memory.save_etsy_draft_result(result)
