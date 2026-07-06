"""Map Aurora listing packages to Etsy draft payloads."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from project_aurora.integrations.etsy.etsy_config import EtsyConfig
from project_aurora.listing.listing_package import ListingPackage
from project_aurora.seo.seo_package import SEOPackage


@dataclass(frozen=True, slots=True)
class EtsyDraftListingPayload:
    """Etsy draft listing payload."""

    title: str
    description: str
    tags: tuple[str, ...]
    price: float
    quantity: int
    taxonomy_id: int | None
    who_made: str
    when_made: str
    is_supply: bool
    item_weight: float | None
    item_weight_unit: str | None
    processing_profile_id: int | None
    is_digital: bool
    image_files: tuple[str, ...]
    digital_files: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        """Return API-ready payload values."""
        return {
            "title": self.title,
            "description": self.description,
            "tags": list(self.tags),
            "price": self.price,
            "quantity": self.quantity,
            "taxonomy_id": self.taxonomy_id,
            "who_made": self.who_made,
            "when_made": self.when_made,
            "is_supply": self.is_supply,
            "item_weight": self.item_weight,
            "item_weight_unit": self.item_weight_unit,
            "processing_profile_id": self.processing_profile_id,
            "is_digital": self.is_digital,
            "image_files": list(self.image_files),
            "digital_files": list(self.digital_files),
            "state": "draft",
        }


class EtsyListingMapper:
    """Convert Aurora ListingPackage and SEO data to Etsy draft payloads."""

    def map_to_draft(
        self,
        listing_package: ListingPackage,
        seo_package: SEOPackage,
        config: EtsyConfig,
    ) -> EtsyDraftListingPayload:
        """Return an Etsy draft listing payload."""
        return EtsyDraftListingPayload(
            title=seo_package.title,
            description=seo_package.description,
            tags=seo_package.tags,
            price=config.default_price,
            quantity=config.default_quantity,
            taxonomy_id=config.taxonomy_id,
            who_made="i_did",
            when_made="made_to_order",
            is_supply=False,
            item_weight=None,
            item_weight_unit=None,
            processing_profile_id=config.processing_profile_id,
            is_digital=True,
            image_files=listing_package.approved_mockup_files,
            digital_files=listing_package.approved_generated_image_files,
        )

    def validate_payload(
        self,
        payload: EtsyDraftListingPayload,
    ) -> tuple[str, ...]:
        """Return validation errors for Etsy draft payload."""
        errors: list[str] = []
        if not payload.title:
            errors.append("Title is required.")
        if len(payload.title) > 140:
            errors.append("Title exceeds Etsy's 140-character limit.")
        if not payload.description:
            errors.append("Description is required.")
        if len(payload.tags) != 13:
            errors.append("Exactly 13 tags are required.")
        for tag in payload.tags:
            if len(tag) > 20:
                errors.append(f"Tag exceeds 20 characters: {tag}.")
        if payload.price <= 0:
            errors.append("Price must be greater than zero.")
        if payload.quantity <= 0:
            errors.append("Quantity must be greater than zero.")
        return tuple(errors)
