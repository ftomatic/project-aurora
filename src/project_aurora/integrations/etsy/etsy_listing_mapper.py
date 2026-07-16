"""Map Aurora listing packages to Etsy draft payloads."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from project_aurora.integrations.etsy.etsy_config import EtsyConfig
from project_aurora.image_generation.commercial_image_exporter import (
    validate_commercial_png,
)
from project_aurora.listing.listing_package import ListingPackage
from project_aurora.seo.description_builder import (
    DOWNLOAD_DISCLAIMER_SECTION,
    PURCHASE_SECTION,
)
from project_aurora.seo.seo_package import SEOPackage


DEFAULT_AI_DISCLOSURE = "It’s created with help from an AI generator."
AI_DISCLOSURE_API_FIELD: str | None = None
RENEWAL_API_FIELD = "should_auto_renew"


@dataclass(frozen=True, slots=True)
class EtsyListingDefaults:
    """Configurable Etsy listing creation defaults."""

    ai_disclosure: str = DEFAULT_AI_DISCLOSURE
    should_auto_renew: bool = True
    who_made: str = "i_did"
    when_made: str = "made_to_order"
    digital_listing_type: str = "download"
    quantity: int = 999
    price: float = 1.99


@dataclass(frozen=True, slots=True)
class EtsyDraftListingPayload:
    """Etsy draft listing payload."""

    title: str
    description: str
    tags: tuple[str, ...]
    price: float
    quantity: int
    taxonomy_id: int | None
    listing_type: str
    who_made: str
    when_made: str
    is_supply: bool
    item_weight: float | None
    item_weight_unit: str | None
    processing_profile_id: int | None
    shipping_profile_id: int | None
    is_digital: bool
    image_files: tuple[str, ...]
    digital_files: tuple[str, ...]
    ai_disclosure: str
    should_auto_renew: bool

    def to_dict(self) -> dict[str, Any]:
        """Return API-ready payload values."""
        payload: dict[str, Any] = {
            "title": self.title,
            "description": self.description,
            "tags": list(self.tags),
            "price": self.price,
            "quantity": self.quantity,
            "taxonomy_id": self.taxonomy_id,
            "type": self.listing_type,
            "who_made": self.who_made,
            "when_made": self.when_made,
            "is_supply": self.is_supply,
            "item_weight": self.item_weight,
            "item_weight_unit": self.item_weight_unit,
            "processing_profile_id": self.processing_profile_id,
            "shipping_profile_id": self.shipping_profile_id,
            "is_digital": self.is_digital,
            "image_files": list(self.image_files),
            "digital_files": list(self.digital_files),
            RENEWAL_API_FIELD: self.should_auto_renew,
            "state": "draft",
        }
        return {
            key: value for key, value in payload.items() if value is not None
        }


class EtsyListingMapper:
    """Convert Aurora ListingPackage and SEO data to Etsy draft payloads."""

    def map_to_draft(
        self,
        listing_package: ListingPackage,
        seo_package: SEOPackage,
        config: EtsyConfig,
        defaults: EtsyListingDefaults | None = None,
    ) -> EtsyDraftListingPayload:
        """Return an Etsy draft listing payload."""
        defaults = defaults or EtsyListingDefaults()
        is_digital = listing_package.is_digital_download
        listing_type = defaults.digital_listing_type if is_digital else "physical"
        return EtsyDraftListingPayload(
            title=seo_package.title,
            description=seo_package.description,
            tags=seo_package.tags,
            price=defaults.price if is_digital else listing_package.price,
            quantity=defaults.quantity if is_digital else config.default_quantity,
            taxonomy_id=config.taxonomy_id,
            listing_type=listing_type,
            who_made=defaults.who_made,
            when_made=defaults.when_made,
            is_supply=False,
            item_weight=None,
            item_weight_unit=None,
            processing_profile_id=(
                None if is_digital else config.processing_profile_id
            ),
            shipping_profile_id=(
                None if is_digital else config.shipping_profile_id
            ),
            is_digital=is_digital,
            image_files=listing_package.approved_mockup_files,
            digital_files=listing_package.approved_generated_image_files,
            ai_disclosure=defaults.ai_disclosure,
            should_auto_renew=defaults.should_auto_renew,
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
        if payload.price != 1.99:
            errors.append("RainbowMilkStudio listing price must be 1.99.")
        if payload.quantity <= 0:
            errors.append("Quantity must be greater than zero.")
        if PURCHASE_SECTION not in payload.description:
            errors.append("Required RainbowMilkStudio purchase section is missing.")
        if DOWNLOAD_DISCLAIMER_SECTION not in payload.description:
            errors.append("Required RainbowMilkStudio download disclaimer is missing.")
        if "FREE COMMERCIAL LICENSE" not in payload.description:
            errors.append("FREE COMMERCIAL LICENSE is required in the description.")
        if payload.ai_disclosure != DEFAULT_AI_DISCLOSURE:
            errors.append("Default AI disclosure is required.")
        if not payload.should_auto_renew:
            errors.append("Etsy renewal must be automatic.")
        if payload.who_made != "i_did":
            errors.append("who_made must default to i_did.")
        if payload.when_made != "made_to_order":
            errors.append("when_made must default to made_to_order.")
        if payload.is_digital and payload.listing_type != "download":
            errors.append("Digital listing type must be download.")
        if payload.is_digital and payload.quantity != 999:
            errors.append("Digital listing quantity must be 999.")
        if payload.is_digital:
            if len(payload.image_files) != 4:
                errors.append("Exactly 4 final commercial PNG files are required.")
            for image_file in payload.image_files:
                image_errors = validate_commercial_png(Path(image_file))
                errors.extend(
                    f"{Path(image_file).name}: {error}"
                    for error in image_errors
                )
        if (
            payload.listing_type == "physical"
            and payload.shipping_profile_id is None
        ):
            errors.append("shipping_profile_id is required for physical listings.")
        return tuple(errors)
