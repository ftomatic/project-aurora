"""Canonical product specification for Aurora production jobs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from project_aurora.planning.production_queue_manager import ProductionJob
from project_aurora.production.watercolor_scope import resolve_watercolor_scope


PRODUCT_SPECIFICATION_CONFLICT = "PRODUCT_SPECIFICATION_CONFLICT"


@dataclass(frozen=True, slots=True)
class ProductSpecification:
    """Immutable product definition consumed across the production pipeline."""

    job_id: str
    product_name: str
    canonical_product_type: str
    customer_deliverable: str
    target_customer: str = "digital printable buyers"
    intended_use: str = "commercial digital craft and printable projects"
    required_asset_count: int = 0
    required_subjects: tuple[str, ...] = field(default_factory=tuple)
    optional_subjects: tuple[str, ...] = field(default_factory=tuple)
    prohibited_subjects: tuple[str, ...] = field(default_factory=tuple)
    intended_file_format: str = ""
    intended_file_formats: tuple[str, ...] = field(default_factory=tuple)
    customer_asset_count: int = 0
    transparent_background_required: bool = False
    seamless_pattern_required: bool = False
    printable_page_required: bool = False
    mockup_required: bool = False
    listing_mockup_required: bool = False
    listing_image_plan: tuple[str, ...] = field(default_factory=tuple)
    customer_download_plan: tuple[str, ...] = field(default_factory=tuple)
    text_policy: tuple[str, ...] = field(default_factory=lambda: (
        "no text",
        "no words",
        "no letters",
        "no numbers",
        "no dates",
        "no years",
        "no logos",
        "no watermark",
        "no signature",
        "no typography",
        "no labels",
        "no captions",
    ))
    price: float = 2.49
    currency: str = "USD"

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe specification."""
        return {
            "job_id": self.job_id,
            "product_name": self.product_name,
            "canonical_product_type": self.canonical_product_type,
            "customer_deliverable": self.customer_deliverable,
            "target_customer": self.target_customer,
            "intended_use": self.intended_use,
            "required_asset_count": self.required_asset_count,
            "required_subjects": list(self.required_subjects),
            "optional_subjects": list(self.optional_subjects),
            "prohibited_subjects": list(self.prohibited_subjects),
            "intended_file_format": self.intended_file_format,
            "intended_file_formats": list(self.intended_file_formats or (self.intended_file_format,)),
            "customer_asset_count": self.customer_asset_count or self.required_asset_count,
            "transparent_background_required": self.transparent_background_required,
            "seamless_pattern_required": self.seamless_pattern_required,
            "printable_page_required": self.printable_page_required,
            "mockup_required": self.mockup_required,
            "listing_mockup_required": self.listing_mockup_required or self.mockup_required,
            "listing_image_plan": list(self.listing_image_plan),
            "customer_download_plan": list(self.customer_download_plan),
            "text_policy": list(self.text_policy),
            "price": self.price,
            "currency": self.currency,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProductSpecification":
        """Load a specification from JSON-like data."""
        return cls(
            job_id=str(data.get("job_id", "")),
            product_name=str(data.get("product_name", "")),
            canonical_product_type=str(data.get("canonical_product_type", "")),
            customer_deliverable=str(data.get("customer_deliverable", "")),
            target_customer=str(data.get("target_customer", "digital printable buyers")),
            intended_use=str(data.get("intended_use", "commercial digital craft and printable projects")),
            required_asset_count=int(data.get("required_asset_count", 0)),
            required_subjects=tuple(str(item) for item in data.get("required_subjects", ())),
            optional_subjects=tuple(str(item) for item in data.get("optional_subjects", ())),
            prohibited_subjects=tuple(str(item) for item in data.get("prohibited_subjects", ())),
            intended_file_format=str(data.get("intended_file_format", "")),
            intended_file_formats=tuple(
                str(item) for item in data.get("intended_file_formats", ())
            ),
            customer_asset_count=int(data.get("customer_asset_count") or data.get("required_asset_count", 0)),
            transparent_background_required=bool(data.get("transparent_background_required", False)),
            seamless_pattern_required=bool(data.get("seamless_pattern_required", False)),
            printable_page_required=bool(data.get("printable_page_required", False)),
            mockup_required=bool(data.get("mockup_required", False)),
            listing_mockup_required=bool(data.get("listing_mockup_required", data.get("mockup_required", False))),
            listing_image_plan=tuple(str(item) for item in data.get("listing_image_plan", ())),
            customer_download_plan=tuple(str(item) for item in data.get("customer_download_plan", ())),
            text_policy=tuple(str(item) for item in data.get("text_policy", ())) or cls.__dataclass_fields__["text_policy"].default_factory(),
            price=float(data.get("price", 2.49)),
            currency=str(data.get("currency", "USD")),
        )


def build_product_specification(job: ProductionJob) -> ProductSpecification:
    """Create the canonical product definition for one production job."""
    scope = resolve_watercolor_scope(job.product_name, job.category, job.style)
    if not scope.supported:
        raise RuntimeError(f"{PRODUCT_SPECIFICATION_CONFLICT}: {scope.reason}")
    count = max(4, min(10, job.required_image_count or 4))
    return ProductSpecification(
        job_id=job.id,
        product_name=job.product_name,
        canonical_product_type=scope.canonical_product_type,
        customer_deliverable="watercolor PNG clipart illustrations on transparent backgrounds",
        target_customer=job.target_customer or "digital printable buyers and small creative businesses",
        intended_use="commercial crafts, sublimation, stickers, stationery, scrapbooking, and printable projects",
        required_asset_count=count,
        required_subjects=_required_subjects(job),
        optional_subjects=("botanical accents", "soft country clothing", "gentle everyday props"),
        prohibited_subjects=(
            "visible text",
            "letters",
            "numbers",
            "labels",
            "title cards",
            "product covers",
            "marketing layouts",
            "posters",
            "mockups",
            "black promotional background",
            "packaging",
            "screens with text",
        ),
        intended_file_format="PNG",
        intended_file_formats=("PNG",),
        customer_asset_count=count,
        transparent_background_required=True,
        seamless_pattern_required=False,
        printable_page_required=False,
        mockup_required=False,
        listing_mockup_required=False,
        listing_image_plan=("use approved customer PNG illustrations directly as listing images",),
        customer_download_plan=("ZIP containing all final 4000x4000 PNG customer illustrations",),
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
        "watercolor_clipart_bundle": ("clipart", "digital illustration", "illustration collection"),
        "watercolor_sticker_set": ("sticker illustration set", "sticker"),
        "watercolor_animal_collection": ("animal", "woodland", "digital illustration", "illustration collection", "clipart"),
        "watercolor_botanical_collection": ("botanical", "mushroom", "floral", "clipart", "digital illustration", "illustration collection"),
        "watercolor_woodland_collection": ("woodland", "clipart", "digital illustration", "illustration collection"),
        "signature_storybook_animal_collection": ("storybook", "animal", "digital illustration", "illustration collection", "clipart"),
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
