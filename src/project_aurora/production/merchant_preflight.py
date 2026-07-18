"""Merchant preflight validation before Etsy draft creation."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from project_aurora.planning.production_queue_manager import ProductionJob
from project_aurora.production.merchant_package import MerchantPackage
from project_aurora.production.merchant_specification import MerchantSpecificationQA


READY_FOR_ETSY_DRAFT = "READY_FOR_ETSY_DRAFT"
PREFLIGHT_FAILED = "PREFLIGHT_FAILED"


@dataclass(frozen=True, slots=True)
class MerchantPreflightResult:
    """Merchant preflight decision."""

    status: str
    product_name: str
    capability: str
    category: str
    etsy_taxonomy_path: str
    taxonomy_id: int | None
    price: float | None
    pricing_source: str
    style: str
    rendering_family: str
    listing_images_ready: int
    customer_files_ready: int
    seo_status: str
    specification_version: str = ""
    merchant_qa_status: str = ""
    manifest: dict[str, Any] = field(default_factory=dict)
    errors: tuple[str, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "product_name": self.product_name,
            "capability": self.capability,
            "category": self.category,
            "etsy_taxonomy_path": self.etsy_taxonomy_path,
            "taxonomy_id": self.taxonomy_id,
            "price": self.price,
            "pricing_source": self.pricing_source,
            "style": self.style,
            "rendering_family": self.rendering_family,
            "listing_images_ready": self.listing_images_ready,
            "customer_files_ready": self.customer_files_ready,
            "seo_status": self.seo_status,
            "specification_version": self.specification_version,
            "merchant_qa_status": self.merchant_qa_status,
            "manifest": self.manifest,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "created_at": self.created_at.isoformat(),
        }

    def render(self) -> str:
        return "\n\n".join(
            (
                "MERCHANT PREFLIGHT",
                f"Product\n{self.product_name}",
                f"Capability\n{self.capability}",
                f"Category\n{self.category}",
                f"Etsy Taxonomy\n{self.etsy_taxonomy_path}",
                f"Taxonomy ID\n{self.taxonomy_id or ''}",
                f"Price\n{self.price or ''}",
                f"Pricing Source\n{self.pricing_source}",
                f"Style\n{self.style}",
                f"Rendering Family\n{self.rendering_family}",
                f"Listing Images\n{self.listing_images_ready} ready",
                f"Customer Files\n{self.customer_files_ready} ready",
                f"SEO\n{self.seo_status}",
                f"Merchant QA\n{self.merchant_qa_status}",
                f"Specification Version\n{self.specification_version}",
                f"Status\n{self.status}",
            )
        )


class MerchantPreflight:
    """Validate merchant package, SEO and local files before Etsy draft."""

    def run(
        self,
        *,
        job: ProductionJob,
        merchant_package: MerchantPackage,
        seo_package: Any,
        final_images_dir: Path,
        image_qa_approved: bool = True,
    ) -> MerchantPreflightResult:
        errors: list[str] = []
        if merchant_package.job_id != job.id:
            errors.append("Merchant package job_id does not match current job.")
        if merchant_package.product_name != job.product_name:
            errors.append("Merchant package product_name does not match current job.")
        if not merchant_package.product_capability_result.get("supported"):
            errors.append("Product capability is not supported.")
        if not merchant_package.etsy_taxonomy_id:
            errors.append("Etsy taxonomy was not resolved.")
        if merchant_package.taxonomy_confidence < 80:
            errors.append("Etsy taxonomy confidence is below threshold.")
        if merchant_package.launch_price <= 0:
            errors.append("Price was not resolved.")
        if merchant_package.launch_price == 1.99 and merchant_package.pricing_source == "CONFIGURED_FALLBACK":
            errors.append("Price appears to be stale global default 1.99.")
        if getattr(seo_package, "job_id", "") != job.id:
            errors.append("SEO package does not match current job.")
        if getattr(seo_package, "product_name", "") != job.product_name:
            errors.append("SEO package product name does not match current job.")
        if not image_qa_approved:
            errors.append("Image QA has not passed or been manually approved.")
        merchant_qa = MerchantSpecificationQA().validate(
            category=job.category,
            product_dir=final_images_dir,
            product_name=job.product_name,
        )
        errors.extend(merchant_qa.errors)
        status = READY_FOR_ETSY_DRAFT if not errors else PREFLIGHT_FAILED
        ready_count = len(merchant_qa.manifest.files) if merchant_qa.status == "PASS" else 0
        return MerchantPreflightResult(
            status=status,
            product_name=job.product_name,
            capability=merchant_package.capability_mode,
            category=job.category,
            etsy_taxonomy_path=merchant_package.etsy_taxonomy_path,
            taxonomy_id=merchant_package.etsy_taxonomy_id,
            price=merchant_package.launch_price,
            pricing_source=merchant_package.pricing_source,
            style=merchant_package.selected_style,
            rendering_family=str(getattr(seo_package, "style", "") or merchant_package.selected_style),
            listing_images_ready=ready_count,
            customer_files_ready=ready_count,
            seo_status="PASS" if not any("SEO package" in error for error in errors) else "FAIL",
            specification_version=merchant_qa.manifest.specification_version,
            merchant_qa_status=merchant_qa.status,
            manifest=merchant_qa.manifest.to_dict(),
            errors=tuple(errors),
        )
