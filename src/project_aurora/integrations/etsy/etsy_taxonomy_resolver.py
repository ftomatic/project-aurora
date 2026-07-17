"""Product-specific Etsy taxonomy resolution for Aurora."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class EtsyTaxonomyResult:
    """Resolved Etsy taxonomy and listing attributes."""

    taxonomy_id: int | None
    taxonomy_name: str
    full_taxonomy_path: str
    validated_product_type: str
    supported_etsy_attributes: dict[str, str]
    occasion: str = ""
    holiday: str = ""
    recipient: str = ""
    room: str = ""
    orientation: str = ""
    primary_color: str = ""
    secondary_color: str = ""
    materials: tuple[str, ...] = field(default_factory=tuple)
    confidence: int = 0
    resolution_reason: str = ""
    generated_at: datetime = field(default_factory=datetime.now)

    @property
    def resolved(self) -> bool:
        return self.taxonomy_id is not None and self.confidence >= 80

    def to_dict(self) -> dict[str, Any]:
        return {
            "taxonomy_id": self.taxonomy_id,
            "taxonomy_name": self.taxonomy_name,
            "full_taxonomy_path": self.full_taxonomy_path,
            "validated_product_type": self.validated_product_type,
            "supported_etsy_attributes": self.supported_etsy_attributes,
            "occasion": self.occasion,
            "holiday": self.holiday,
            "recipient": self.recipient,
            "room": self.room,
            "orientation": self.orientation,
            "primary_color": self.primary_color,
            "secondary_color": self.secondary_color,
            "materials": list(self.materials),
            "confidence": self.confidence,
            "resolution_reason": self.resolution_reason,
            "generated_at": self.generated_at.isoformat(),
        }


class EtsyTaxonomyResolver:
    """Resolve Etsy taxonomy from product/category signals."""

    def __init__(self, cache_path: Path | None = None) -> None:
        self._cache_path = cache_path or Path(__file__).resolve().parents[4] / "config" / "etsy_taxonomy_cache.yaml"
        self._cache = _load_taxonomy_cache(self._cache_path)

    def resolve(
        self,
        *,
        product_name: str,
        product_type: str,
        category: str,
        subcategory: str = "",
        intended_use: str = "",
        audience: str = "",
        occasion: str = "",
        holiday: str = "",
        room: str = "",
        orientation: str = "",
        digital_physical_type: str = "download",
    ) -> EtsyTaxonomyResult:
        """Resolve one product to a supported Etsy taxonomy."""
        key = _taxonomy_key(product_name, product_type, category, subcategory, intended_use)
        record = self._cache.get(key)
        if record is None:
            return EtsyTaxonomyResult(
                taxonomy_id=None,
                taxonomy_name="",
                full_taxonomy_path="",
                validated_product_type=key,
                supported_etsy_attributes={},
                confidence=0,
                resolution_reason=f"No verified taxonomy mapping for product type: {key}.",
            )
        attrs = {
            "type": digital_physical_type,
            "taxonomy_name": str(record["taxonomy_name"]),
        }
        return EtsyTaxonomyResult(
            taxonomy_id=int(record["taxonomy_id"]),
            taxonomy_name=str(record["taxonomy_name"]),
            full_taxonomy_path=str(record["full_taxonomy_path"]),
            validated_product_type=key,
            supported_etsy_attributes=attrs,
            occasion=occasion or _occasion(product_name, category),
            holiday=holiday or _holiday(product_name),
            recipient=_recipient(audience, product_name),
            room=room or _room(product_name, category),
            orientation=orientation or _orientation(product_name, category),
            primary_color=_primary_color(product_name, category),
            secondary_color=_secondary_color(product_name, category),
            materials=("digital png", "instant download"),
            confidence=92,
            resolution_reason=f"Resolved from configured verified taxonomy cache for {key}.",
        )


def _taxonomy_key(*values: str) -> str:
    lowered = " ".join(values).casefold()
    if "digital paper" in lowered:
        return "digital paper"
    if "seamless" in lowered or "pattern" in lowered:
        return "seamless pattern"
    if "nursery" in lowered and ("wall art" in lowered or "art" in lowered):
        return "nursery wall art"
    if "botanical" in lowered or "floral art" in lowered:
        return "botanical print"
    if "wall art" in lowered or "poster" in lowered or "print" in lowered:
        return "printable wall art"
    if "sticker" in lowered:
        return "sticker sheet"
    if "gift tag" in lowered or "favor tag" in lowered:
        return "gift tags"
    if "scrapbook" in lowered or "journal" in lowered:
        return "scrapbook kit"
    if "stationery" in lowered or "recipe card" in lowered or "bridal shower" in lowered:
        return "stationery"
    if "party" in lowered or "birthday" in lowered:
        return "party printable"
    if "clipart" in lowered or "graphics" in lowered:
        return "clipart"
    return "unknown"


def _load_taxonomy_cache(path: Path) -> dict[str, dict[str, object]]:
    records: dict[str, dict[str, object]] = {}
    current_key = ""
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.strip().startswith("#"):
            continue
        if line.startswith("  ") and not line.startswith("    ") and line.strip().endswith(":"):
            current_key = line.strip().removesuffix(":")
            records[current_key] = {}
        elif line.startswith("    ") and current_key:
            key, raw = line.strip().split(":", maxsplit=1)
            value = raw.strip()
            records[current_key][key] = int(value) if key == "taxonomy_id" and value.isdigit() else value
    return records


def _occasion(product_name: str, category: str) -> str:
    lowered = f"{product_name} {category}".casefold()
    if "wedding" in lowered or "bridal" in lowered:
        return "wedding"
    if "birthday" in lowered:
        return "birthday"
    if "baby shower" in lowered:
        return "baby shower"
    return ""


def _holiday(product_name: str) -> str:
    lowered = product_name.casefold()
    for holiday in ("christmas", "halloween", "easter", "mother's day", "new year"):
        if holiday in lowered:
            return holiday.title()
    return ""


def _recipient(audience: str, product_name: str) -> str:
    lowered = f"{audience} {product_name}".casefold()
    if "teacher" in lowered:
        return "teachers"
    if "baby" in lowered or "nursery" in lowered:
        return "babies"
    if "bride" in lowered or "wedding" in lowered:
        return "brides"
    return "adults"


def _room(product_name: str, category: str) -> str:
    lowered = f"{product_name} {category}".casefold()
    if "nursery" in lowered:
        return "nursery"
    if "kitchen" in lowered:
        return "kitchen"
    if "classroom" in lowered:
        return "classroom"
    return ""


def _orientation(product_name: str, category: str) -> str:
    lowered = f"{product_name} {category}".casefold()
    if "wall art" in lowered or "poster" in lowered:
        return "square"
    return ""


def _primary_color(product_name: str, category: str) -> str:
    lowered = f"{product_name} {category}".casefold()
    if "strawberry" in lowered:
        return "red"
    if "boho" in lowered:
        return "beige"
    if "dark academia" in lowered:
        return "brown"
    if "spring" in lowered:
        return "green"
    return "multicolor"


def _secondary_color(product_name: str, category: str) -> str:
    lowered = f"{product_name} {category}".casefold()
    if "strawberry" in lowered:
        return "pink"
    if "boho" in lowered:
        return "cream"
    if "dark academia" in lowered:
        return "black"
    if "spring" in lowered:
        return "yellow"
    return ""
