"""Job-specific merchant package for Etsy draft readiness."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class MerchantPackage:
    """Merchant decisions required before Etsy draft creation."""

    job_id: str
    product_name: str
    product_type: str
    capability_mode: str
    etsy_taxonomy_id: int
    etsy_taxonomy_path: str
    taxonomy_confidence: int
    price_range: tuple[float, float, float]
    recommended_price: float
    launch_price: float
    pricing_reason: str
    pricing_source: str
    selected_style: str
    style_confidence: int
    composition: str
    background: str
    product_capability_result: dict[str, Any]
    warnings: tuple[str, ...] = field(default_factory=tuple)
    generated_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "product_name": self.product_name,
            "product_type": self.product_type,
            "capability_mode": self.capability_mode,
            "etsy_taxonomy_id": self.etsy_taxonomy_id,
            "etsy_taxonomy_path": self.etsy_taxonomy_path,
            "taxonomy_confidence": self.taxonomy_confidence,
            "price_range": list(self.price_range),
            "recommended_price": self.recommended_price,
            "launch_price": self.launch_price,
            "pricing_reason": self.pricing_reason,
            "pricing_source": self.pricing_source,
            "selected_style": self.selected_style,
            "style_confidence": self.style_confidence,
            "composition": self.composition,
            "background": self.background,
            "product_capability_result": self.product_capability_result,
            "warnings": list(self.warnings),
            "generated_at": self.generated_at.isoformat(),
        }


def merchant_package_from_dict(data: dict[str, Any]) -> MerchantPackage:
    return MerchantPackage(
        job_id=str(data["job_id"]),
        product_name=str(data["product_name"]),
        product_type=str(data["product_type"]),
        capability_mode=str(data["capability_mode"]),
        etsy_taxonomy_id=int(data["etsy_taxonomy_id"]),
        etsy_taxonomy_path=str(data["etsy_taxonomy_path"]),
        taxonomy_confidence=int(data["taxonomy_confidence"]),
        price_range=tuple(float(value) for value in data["price_range"]),  # type: ignore[arg-type]
        recommended_price=float(data["recommended_price"]),
        launch_price=float(data["launch_price"]),
        pricing_reason=str(data["pricing_reason"]),
        pricing_source=str(data["pricing_source"]),
        selected_style=str(data["selected_style"]),
        style_confidence=int(data["style_confidence"]),
        composition=str(data["composition"]),
        background=str(data["background"]),
        product_capability_result=dict(data["product_capability_result"]),
        warnings=tuple(str(item) for item in data.get("warnings", ())),
        generated_at=datetime.fromisoformat(str(data["generated_at"])),
    )
