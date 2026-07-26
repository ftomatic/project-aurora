"""Canonical product specification for Aurora production jobs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from project_aurora.planning.production_queue_manager import ProductionJob


PRODUCT_SPECIFICATION_CONFLICT = "PRODUCT_SPECIFICATION_CONFLICT"


@dataclass(frozen=True, slots=True)
class ProductSpecification:
    """Immutable product definition consumed across the production pipeline."""

    job_id: str
    product_name: str
    canonical_product_type: str
    customer_deliverable: str
    required_asset_count: int
    required_subjects: tuple[str, ...]
    prohibited_subjects: tuple[str, ...]
    intended_file_format: str
    transparent_background_required: bool
    seamless_pattern_required: bool
    printable_page_required: bool
    mockup_required: bool
    listing_image_plan: tuple[str, ...]
    customer_download_plan: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe specification."""
        return {
            "job_id": self.job_id,
            "product_name": self.product_name,
            "canonical_product_type": self.canonical_product_type,
            "customer_deliverable": self.customer_deliverable,
            "required_asset_count": self.required_asset_count,
            "required_subjects": list(self.required_subjects),
            "prohibited_subjects": list(self.prohibited_subjects),
            "intended_file_format": self.intended_file_format,
            "transparent_background_required": self.transparent_background_required,
            "seamless_pattern_required": self.seamless_pattern_required,
            "printable_page_required": self.printable_page_required,
            "mockup_required": self.mockup_required,
            "listing_image_plan": list(self.listing_image_plan),
            "customer_download_plan": list(self.customer_download_plan),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProductSpecification":
        """Load a specification from JSON-like data."""
        return cls(
            job_id=str(data.get("job_id", "")),
            product_name=str(data.get("product_name", "")),
            canonical_product_type=str(data.get("canonical_product_type", "")),
            customer_deliverable=str(data.get("customer_deliverable", "")),
            required_asset_count=int(data.get("required_asset_count", 0)),
            required_subjects=tuple(str(item) for item in data.get("required_subjects", ())),
            prohibited_subjects=tuple(str(item) for item in data.get("prohibited_subjects", ())),
            intended_file_format=str(data.get("intended_file_format", "")),
            transparent_background_required=bool(data.get("transparent_background_required", False)),
            seamless_pattern_required=bool(data.get("seamless_pattern_required", False)),
            printable_page_required=bool(data.get("printable_page_required", False)),
            mockup_required=bool(data.get("mockup_required", False)),
            listing_image_plan=tuple(str(item) for item in data.get("listing_image_plan", ())),
            customer_download_plan=tuple(str(item) for item in data.get("customer_download_plan", ())),
        )


def build_product_specification(job: ProductionJob) -> ProductSpecification:
    """Create the canonical product definition for one production job."""
    lowered = f"{job.product_name} {job.category}".casefold()
    if "clipart" in lowered or "illustration collection" in lowered:
        return ProductSpecification(
            job_id=job.id,
            product_name=job.product_name,
            canonical_product_type="clipart_bundle",
            customer_deliverable=_clipart_deliverable(job.product_name),
            required_asset_count=max(4, job.required_image_count or 4),
            required_subjects=_required_subjects(job),
            prohibited_subjects=(
                "visible text",
                "labels",
                "title cards",
                "product covers",
                "black promotional background",
                "packaging",
                "posters",
            ),
            intended_file_format="PNG",
            transparent_background_required=True,
            seamless_pattern_required=False,
            printable_page_required=False,
            mockup_required=False,
            listing_image_plan=(
                "hero collage from approved customer assets",
                "complete collection overview from approved customer assets",
                "detail preview from approved customer assets",
                "truthful use-case mockup composed locally",
            ),
            customer_download_plan=("individual transparent PNG customer assets",),
        )
    if "digital paper" in lowered:
        return ProductSpecification(
            job_id=job.id,
            product_name=job.product_name,
            canonical_product_type="digital_paper",
            customer_deliverable="seamless printable scrapbook paper JPG files",
            required_asset_count=max(12, job.required_image_count or 12),
            required_subjects=_required_subjects(job),
            prohibited_subjects=("visible text", "labels", "mockup covers", "paper stacks"),
            intended_file_format="JPG",
            transparent_background_required=False,
            seamless_pattern_required=True,
            printable_page_required=False,
            mockup_required=False,
            listing_image_plan=("collage preview composed locally",),
            customer_download_plan=("twelve seamless JPG papers", "ZIP package"),
        )
    if "wall art" in lowered or "poster" in lowered:
        return ProductSpecification(
            job_id=job.id,
            product_name=job.product_name,
            canonical_product_type="printable_wall_art",
            customer_deliverable="printable wall art files in multiple ratios",
            required_asset_count=max(5, job.required_image_count or 5),
            required_subjects=_required_subjects(job),
            prohibited_subjects=("visible text", "labels", "cropped artwork"),
            intended_file_format="JPG",
            transparent_background_required=False,
            seamless_pattern_required=False,
            printable_page_required=True,
            mockup_required=True,
            listing_image_plan=("lifestyle mockup composed from approved art",),
            customer_download_plan=("ratio JPG files",),
        )
    return ProductSpecification(
        job_id=job.id,
        product_name=job.product_name,
        canonical_product_type="digital_product",
        customer_deliverable="customer-ready digital artwork files",
        required_asset_count=max(4, job.required_image_count or 4),
        required_subjects=_required_subjects(job),
        prohibited_subjects=("visible text", "labels", "product covers"),
        intended_file_format="PNG",
        transparent_background_required=False,
        seamless_pattern_required=False,
        printable_page_required=False,
        mockup_required=False,
        listing_image_plan=("marketing images composed after customer asset approval",),
        customer_download_plan=("customer digital artwork files",),
    )


def validate_product_specification_alignment(
    job: ProductionJob,
    specification: ProductSpecification,
    observed_product_type: str,
) -> None:
    """Fail when downstream components reinterpret the product type."""
    expected = specification.canonical_product_type.casefold()
    observed = observed_product_type.casefold()
    compatible = {
        "clipart_bundle": ("clipart", "digital illustration", "illustration collection", "sticker illustration set"),
        "digital_paper": ("digital paper",),
        "printable_wall_art": ("wall art", "poster", "printable wall art"),
        "digital_product": (observed,),
    }
    if specification.job_id != job.id or specification.product_name != job.product_name:
        raise RuntimeError(f"{PRODUCT_SPECIFICATION_CONFLICT}: specification does not match current job")
    if not any(term in observed for term in compatible.get(expected, ())):
        raise RuntimeError(
            f"{PRODUCT_SPECIFICATION_CONFLICT}: {observed_product_type} conflicts with {specification.canonical_product_type}"
        )


def _clipart_deliverable(product_name: str) -> str:
    lowered = product_name.casefold()
    if "mushroom" in lowered:
        return "individual autumn mushroom watercolor PNG clipart elements"
    return "individual isolated transparent PNG clipart elements"


def _required_subjects(job: ProductionJob) -> tuple[str, ...]:
    text = f"{job.product_name} {' '.join(job.keywords)}".casefold()
    subjects: list[str] = []
    for keyword in (
        "mushroom",
        "autumn leaves",
        "acorns",
        "teacher",
        "alphabet",
        "wedding",
        "botanical",
        "woodland",
        "bunny",
        "strawberry",
    ):
        if keyword in text:
            subjects.append(keyword)
    if "mushroom" in text:
        subjects.extend(["red-capped mushrooms", "brown woodland mushrooms", "mushroom clusters"])
    return tuple(dict.fromkeys(subjects or tuple(job.keywords[:3]) or ("main product subject",)))
