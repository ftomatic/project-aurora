"""Transform researched opportunities into simple production-ready products."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime

from project_aurora.integrations.etsy.etsy_taxonomy_resolver import (
    EtsyTaxonomyResolver,
)
from project_aurora.production.product_capability_resolver import (
    ProductCapabilityResolver,
)
from project_aurora.research.market_opportunity import MarketOpportunity


TRANSFORMED_PRODUCT_TYPE = "digital illustration collection"
TRANSFORMED_IMAGE_COUNT = 4
TRANSFORMED_STYLE = "Whimsical Storybook Watercolor"


@dataclass(frozen=True, slots=True)
class ProductTransformation:
    """Production packaging decision for one researched opportunity."""

    researched_product_name: str
    researched_product_type: str
    production_product_name: str
    production_product_type: str
    production_style: str
    etsy_taxonomy_category: str
    required_image_count: int
    requires_zip_package: bool
    requires_template_engine: bool
    requires_layout_engine: bool
    eligible: bool
    transformation_reason: str
    whimsical_batch_designation: bool = False
    warnings: tuple[str, ...] = field(default_factory=tuple)
    created_at: datetime = field(default_factory=datetime.now)

    def to_queue_metadata(self) -> dict[str, object]:
        """Return metadata fields persisted with the production job."""
        return {
            "original_product_name": self.researched_product_name,
            "original_product_type": self.researched_product_type,
            "transformation_reason": self.transformation_reason,
            "required_image_count": self.required_image_count,
            "requires_zip_package": self.requires_zip_package,
            "requires_template_engine": self.requires_template_engine,
            "requires_layout_engine": self.requires_layout_engine,
            "etsy_taxonomy_category": self.etsy_taxonomy_category,
            "whimsical_batch_designation": self.whimsical_batch_designation,
        }


class ProductTransformationEngine:
    """Package broad research opportunities as four-illustration products."""

    def __init__(
        self,
        *,
        capability_resolver: ProductCapabilityResolver | None = None,
        taxonomy_resolver: EtsyTaxonomyResolver | None = None,
        required_image_count: int = TRANSFORMED_IMAGE_COUNT,
    ) -> None:
        self._capability_resolver = capability_resolver or ProductCapabilityResolver()
        self._taxonomy_resolver = taxonomy_resolver or EtsyTaxonomyResolver()
        self._required_image_count = required_image_count

    def transform(
        self,
        opportunity: MarketOpportunity,
        *,
        whimsical_batch_designation: bool = False,
    ) -> ProductTransformation:
        """Return the production-safe transformation for one opportunity."""
        product_name = _production_name(opportunity)
        style = (
            TRANSFORMED_STYLE
            if whimsical_batch_designation
            else _production_style(opportunity)
        )
        capability = self._capability_resolver.resolve(
            product_name=product_name,
            product_type=TRANSFORMED_PRODUCT_TYPE,
            category=TRANSFORMED_PRODUCT_TYPE,
        )
        taxonomy = self._taxonomy_resolver.resolve(
            product_name=product_name,
            product_type=TRANSFORMED_PRODUCT_TYPE,
            category=TRANSFORMED_PRODUCT_TYPE,
            audience=opportunity.target_audience,
            holiday=opportunity.season,
        )
        warnings: list[str] = []
        if capability.required_deliverable_count not in (0, self._required_image_count):
            warnings.append(
                f"Capability returned {capability.required_deliverable_count} deliverables."
            )
        eligible = (
            capability.supported
            and taxonomy.resolved
            and not capability.requires_zip_package
            and not capability.requires_layout_engine
            and self._required_image_count == TRANSFORMED_IMAGE_COUNT
        )
        reason = (
            "Transformed broad research opportunity into an honest four-illustration "
            "digital product with no ZIP, template, layout, or large-pack dependency."
        )
        if not eligible:
            reason = "; ".join(
                value
                for value in (
                    capability.reason if not capability.supported else "",
                    taxonomy.resolution_reason if not taxonomy.resolved else "",
                    "ZIP package is not allowed." if capability.requires_zip_package else "",
                    "Layout engine is not allowed." if capability.requires_layout_engine else "",
                )
                if value
            )
        return ProductTransformation(
            researched_product_name=opportunity.keyword,
            researched_product_type=opportunity.product_type,
            production_product_name=product_name,
            production_product_type=TRANSFORMED_PRODUCT_TYPE,
            production_style=style,
            etsy_taxonomy_category=taxonomy.validated_product_type,
            required_image_count=self._required_image_count,
            requires_zip_package=False,
            requires_template_engine=False,
            requires_layout_engine=False,
            eligible=eligible,
            transformation_reason=reason,
            whimsical_batch_designation=whimsical_batch_designation,
            warnings=tuple(warnings),
        )

    def transform_batch(
        self,
        opportunities: tuple[MarketOpportunity, ...],
        *,
        minimum_whimsical: int = 2,
    ) -> tuple[ProductTransformation, ...]:
        """Transform a daily batch while reserving whimsical storybook slots."""
        whimsical_indexes = _whimsical_indexes(opportunities, minimum_whimsical)
        return tuple(
            self.transform(
                opportunity,
                whimsical_batch_designation=index in whimsical_indexes,
            )
            for index, opportunity in enumerate(opportunities)
        )


def _production_name(opportunity: MarketOpportunity) -> str:
    theme = _clean_theme(opportunity.keyword)
    lowered = f"{opportunity.keyword} {opportunity.product_type}".casefold()
    if "sticker" in lowered:
        suffix = "Sticker Illustration Set"
    elif "planner" in lowered:
        suffix = "Planner Illustration Collection"
    elif "journal" in lowered or "ephemera" in lowered:
        suffix = "Junk Journal Illustration Collection"
    elif "paper" in lowered or "scrapbook" in lowered:
        suffix = "Digital Illustration Collection"
    elif "clipart" in lowered or "clip art" in lowered:
        suffix = "Clipart Illustration Set"
    else:
        suffix = "Digital Illustration Collection"
    if suffix.casefold() in theme.casefold():
        return _title_case(theme)
    return _title_case(f"{theme} {suffix}")


def _clean_theme(value: str) -> str:
    cleaned = re.sub(
        r"\b(12|20|24|pack|bundle|kit|set|sheet|sheets|sticker|stickers|pages|page|template|templates)\b",
        " ",
        value,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"\b(digital paper|scrapbook paper|planner stickers|sticker sheet|junk journal|journal kit|clipart bundle|clipart set)\b",
        " ",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = " ".join(cleaned.replace("&", " ").replace("-", " ").split())
    return cleaned or "Digital Art"


def _production_style(opportunity: MarketOpportunity) -> str:
    if _is_whimsical(opportunity):
        return TRANSFORMED_STYLE
    style = " ".join(opportunity.recommended_artistic_style.split())
    return style or "Commercial Digital Illustration"


def _whimsical_indexes(
    opportunities: tuple[MarketOpportunity, ...],
    minimum_whimsical: int,
) -> set[int]:
    indexes = [index for index, opportunity in enumerate(opportunities) if _is_whimsical(opportunity)]
    if len(indexes) < minimum_whimsical:
        indexes.extend(
            index
            for index, _opportunity in enumerate(opportunities)
            if index not in indexes
        )
    return set(indexes[:minimum_whimsical])


def _is_whimsical(opportunity: MarketOpportunity) -> bool:
    lowered = (
        f"{opportunity.keyword} {opportunity.primary_niche} "
        f"{opportunity.recommended_artistic_style} {opportunity.target_audience}"
    ).casefold()
    return any(
        term in lowered
        for term in (
            "storybook",
            "woodland",
            "rabbit",
            "bunny",
            "mouse",
            "mice",
            "fox",
            "hedgehog",
            "squirrel",
            "duck",
            "bird",
            "cottage",
            "mushroom",
            "garden",
            "tea party",
            "forest",
            "nursery",
            "animal",
        )
    )


def _title_case(value: str) -> str:
    small_words = {"and", "or", "of", "the", "for"}
    words = []
    for index, word in enumerate(value.split()):
        lowered = word.casefold()
        words.append(lowered if index and lowered in small_words else lowered.title())
    return " ".join(words)
