"""Deterministic layout templates for products that need placement guidance."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


STICKER_SHEET_TEMPLATE_FILENAME = "sticker_sheet_template.json"


@dataclass(frozen=True, slots=True)
class LayoutTemplateResult:
    """Result of creating a local production layout template."""

    status: str
    template_path: str
    product_type: str
    item_count: int
    notes: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "template_path": self.template_path,
            "product_type": self.product_type,
            "item_count": self.item_count,
            "notes": list(self.notes),
        }


class LayoutTemplateEngine:
    """Create local layout guidance before paid image generation."""

    def create_for_product(
        self,
        *,
        product_name: str,
        category: str,
        output_dir: Path,
        item_count: int = 8,
    ) -> LayoutTemplateResult:
        """Create the required template for supported layout-based products."""
        lowered = f"{product_name} {category}".casefold()
        if "sticker" not in lowered:
            return LayoutTemplateResult(
                status="SKIPPED",
                template_path="",
                product_type=category,
                item_count=0,
                notes=("No layout template required for this product.",),
            )
        output_dir.mkdir(parents=True, exist_ok=True)
        template_path = output_dir / STICKER_SHEET_TEMPLATE_FILENAME
        payload = _sticker_sheet_template(product_name, category, item_count)
        template_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return LayoutTemplateResult(
            status="SUCCESS",
            template_path=str(template_path),
            product_type="sticker sheet",
            item_count=item_count,
            notes=(
                "Template requires individual cuttable sticker elements.",
                "White outlines and clean spacing are required.",
            ),
        )


def _sticker_sheet_template(
    product_name: str,
    category: str,
    item_count: int,
) -> dict[str, Any]:
    slots = []
    columns = 4
    rows = max(1, (item_count + columns - 1) // columns)
    for index in range(item_count):
        row = index // columns
        column = index % columns
        slots.append(
            {
                "slot": index + 1,
                "x_percent": round((column + 0.5) * (100 / columns), 2),
                "y_percent": round((row + 0.5) * (100 / rows), 2),
                "safe_zone_percent": 8,
                "outline": "white kiss-cut outline",
            }
        )
    return {
        "template_type": "sticker_sheet",
        "product_name": product_name,
        "category": category,
        "canvas": {
            "width_px": 4000,
            "height_px": 4000,
            "dpi": 300,
            "background": "transparent customer PNGs with separate sticker sheet preview",
        },
        "item_count": item_count,
        "layout": {
            "columns": columns,
            "rows": rows,
            "spacing": "even spacing between cuttable sticker elements",
            "requirements": [
                "one sticker element per generated customer file",
                "transparent background",
                "white outline around each sticker motif",
                "no overlapping elements",
                "no page mockup",
            ],
            "slots": slots,
        },
        "created_at": datetime.now().isoformat(),
    }


def layout_template_exists(path: Path | None) -> bool:
    """Return whether a sticker sheet layout template exists under a path."""
    if path is None:
        return False
    candidates = (
        path / STICKER_SHEET_TEMPLATE_FILENAME,
        path / "templates" / STICKER_SHEET_TEMPLATE_FILENAME,
    )
    return any(candidate.exists() and candidate.stat().st_size > 0 for candidate in candidates)
