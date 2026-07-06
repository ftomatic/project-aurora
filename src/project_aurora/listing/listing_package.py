"""Etsy draft readiness package model."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


READY_FOR_ETSY_DRAFT = "READY_FOR_ETSY_DRAFT"
POSTED_TO_ETSY = "POSTED_TO_ETSY"

CLEANUP_NOT_STARTED = "NOT_STARTED"
CLEANUP_COMPLETE = "COMPLETE"
CLEANUP_FAILED = "FAILED"

RETENTION_KEEP_METADATA_DELETE_LOCAL_TEMP = (
    "KEEP_METADATA_PROMPTS_SEO_ETSY_ID_HISTORY_DELETE_LOCAL_RUNTIME_FILES"
)


@dataclass(frozen=True, slots=True)
class StatusHistoryEntry:
    """A timestamped listing status transition."""

    status: str
    note: str
    created_at: datetime = field(default_factory=datetime.now)


@dataclass(frozen=True, slots=True)
class ListingPackage:
    """Package representing readiness to create an Etsy draft."""

    product_name: str
    collection_name: str
    listing_status: str
    seo_package_id: str
    prompt_package_id: str
    approved_mockup_files: tuple[str, ...]
    approved_generated_image_files: tuple[str, ...]
    etsy_listing_id: str | None = None
    local_asset_cleanup_status: str = CLEANUP_NOT_STARTED
    local_files_retention_policy: str = (
        RETENTION_KEEP_METADATA_DELETE_LOCAL_TEMP
    )
    posted_at: datetime | None = None
    status_history: tuple[StatusHistoryEntry, ...] = field(default_factory=tuple)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    def __post_init__(self) -> None:
        self._require_text("product_name", self.product_name)
        self._require_text("collection_name", self.collection_name)
        self._require_text("listing_status", self.listing_status)
        self._require_text("seo_package_id", self.seo_package_id)
        self._require_text("prompt_package_id", self.prompt_package_id)

        if self.listing_status != READY_FOR_ETSY_DRAFT:
            raise ValueError(
                "New listing packages must use READY_FOR_ETSY_DRAFT status."
            )
        if self.local_asset_cleanup_status not in {
            CLEANUP_NOT_STARTED,
            CLEANUP_COMPLETE,
            CLEANUP_FAILED,
        }:
            raise ValueError(
                "Unsupported local asset cleanup status: "
                f"{self.local_asset_cleanup_status}."
            )

        object.__setattr__(
            self,
            "approved_mockup_files",
            tuple(self.approved_mockup_files),
        )
        object.__setattr__(
            self,
            "approved_generated_image_files",
            tuple(self.approved_generated_image_files),
        )
        object.__setattr__(
            self,
            "status_history",
            tuple(self.status_history)
            or (
                StatusHistoryEntry(
                    status=READY_FOR_ETSY_DRAFT,
                    note="Listing package is ready for future Etsy draft creation.",
                    created_at=self.created_at,
                ),
            ),
        )

    @staticmethod
    def _require_text(field_name: str, value: str) -> None:
        if not value.strip():
            raise ValueError(f"{field_name} cannot be empty.")
