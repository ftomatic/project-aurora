"""Read-only Etsy shop data normalization."""

from __future__ import annotations

from typing import Any

from project_aurora.etsy_intelligence.intelligence_models import (
    UNAVAILABLE,
    DataAvailability,
    ListingSnapshot,
    ShopSnapshot,
)
from project_aurora.integrations.etsy.etsy_client import EtsyClient


class EtsyShopReader:
    """Read available shop data without writing to Etsy."""

    def __init__(self, client: EtsyClient | None = None) -> None:
        self._client = client

    def read(self) -> tuple[ShopSnapshot, tuple[ListingSnapshot, ...], tuple[str, ...]]:
        """Return a normalized shop snapshot and available listing snapshots."""
        warnings: list[str] = []
        raw_drafts: tuple[dict[str, Any], ...] = ()
        if self._client is None:
            warnings.append("Etsy client unavailable; using Aurora memory-only intelligence.")
        else:
            try:
                raw_drafts = self._client.list_shop_draft_listings()
            except RuntimeError as error:
                warnings.append(f"Etsy draft listing read unavailable: {error}")
            except Exception as error:  # pragma: no cover - defensive boundary
                warnings.append(f"Etsy draft listing read failed: {type(error).__name__}")
        listings = tuple(_listing_snapshot(record) for record in raw_drafts)
        categories = tuple(sorted({item.taxonomy_id for item in listings if item.taxonomy_id}))
        availability = (
            DataAvailability("active_listings", UNAVAILABLE, "Not requested from Etsy in Sprint 35-36 read-only pass."),
            DataAvailability("expired_listings", UNAVAILABLE, "Endpoint not wired for this read-only report."),
            DataAvailability("sold_out_listings", UNAVAILABLE, "Endpoint not wired for this read-only report."),
            DataAvailability("views", UNAVAILABLE, "Etsy Open API listing reads may not expose shop analytics metrics."),
            DataAvailability("favorites", UNAVAILABLE, "Favorites are not fabricated when unavailable."),
            DataAvailability("orders", UNAVAILABLE, "Orders require future shop receipt/sales integration."),
            DataAvailability("revenue", UNAVAILABLE, "Revenue requires future sales reports or receipt integration."),
        )
        shop = ShopSnapshot(
            active_listings=0,
            draft_listings=len(listings),
            expired_listings=UNAVAILABLE,
            sold_out_listings=UNAVAILABLE,
            categories=categories,
            data_availability=availability,
        )
        return shop, listings, tuple(warnings)


def _listing_snapshot(record: dict[str, Any]) -> ListingSnapshot:
    tags = record.get("tags")
    price = _price(record.get("price"))
    return ListingSnapshot(
        listing_id=str(record.get("listing_id") or record.get("listing_id_string") or ""),
        title=str(record.get("title") or ""),
        state=str(record.get("state") or ""),
        price=price,
        tags=tuple(str(item) for item in tags) if isinstance(tags, list) else (),
        taxonomy_id=str(record.get("taxonomy_id") or ""),
        is_digital=bool(record.get("is_digital")) if "is_digital" in record else UNAVAILABLE,
        image_count=int(record.get("num_favorers") or 0) if False else UNAVAILABLE,
    )


def _price(value: Any) -> float | None:
    if isinstance(value, dict):
        amount = value.get("amount")
        divisor = value.get("divisor") or 1
        try:
            return round(float(amount) / float(divisor), 2)
        except (TypeError, ValueError, ZeroDivisionError):
            return None
    if isinstance(value, int | float | str):
        try:
            return round(float(str(value).replace("$", "")), 2)
        except ValueError:
            return None
    return None
