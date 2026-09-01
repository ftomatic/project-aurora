"""Build Pinterest's supported bulk-upload CSV from active Etsy listings."""

from __future__ import annotations

import csv
import html
import json
from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Protocol
from zoneinfo import ZoneInfo


PINTEREST_COLUMNS = (
    "Title",
    "Media URL",
    "Pinterest board",
    "Thumbnail",
    "Description",
    "Link",
    "Publish date",
    "Keywords",
)


def daily_publish_dates(day: str, count: int) -> tuple[str, ...]:
    """Distribute Pins at 9 AM, 1 PM and 6 PM Eastern in groups of 3, 3 and 4."""
    target = date.fromisoformat(day)
    slots = ((9, 3), (13, 3), (18, 4))
    eastern = ZoneInfo("America/New_York")
    utc = ZoneInfo("UTC")
    values: list[str] = []
    for hour, quantity in slots:
        scheduled = datetime(
            target.year,
            target.month,
            target.day,
            hour,
            tzinfo=eastern,
        ).astimezone(utc)
        values.extend(scheduled.strftime("%Y-%m-%dT%H:%M:%S") for _ in range(quantity))
    return tuple(values[:count])


class EtsyListingReader(Protocol):
    """Etsy operations needed by the Pinterest exporter."""

    def list_shop_active_listings(self) -> tuple[dict[str, Any], ...]: ...

    def list_listing_images(self, listing_id: str) -> tuple[dict[str, Any], ...]: ...


@dataclass(frozen=True, slots=True)
class PinterestBulkPin:
    """One Pinterest bulk-upload row."""

    etsy_listing_id: str
    title: str
    media_url: str
    board: str
    description: str
    link: str
    keywords: str
    publish_date: str = ""

    def csv_row(self) -> dict[str, str]:
        return {
            "Title": self.title,
            "Media URL": self.media_url,
            "Pinterest board": self.board,
            "Thumbnail": "",
            "Description": self.description,
            "Link": self.link,
            "Publish date": self.publish_date,
            "Keywords": self.keywords,
        }


@dataclass(frozen=True, slots=True)
class PinterestBulkResult:
    """Result of preparing a Pinterest bulk upload."""

    csv_path: str
    manifest_path: str
    pins_prepared: int
    skipped_prepared: int
    skipped_without_images: int
    listing_ids: tuple[str, ...]


class PinterestBulkExporter:
    """Create an idempotent Pinterest CSV from Etsy's active listings."""

    def __init__(
        self,
        client: EtsyListingReader,
        output_dir: Path,
        board: str = "RainbowMilkStudio Digital Downloads",
        manifest_path: Path | None = None,
    ) -> None:
        self._client = client
        self._output_dir = output_dir
        self._board = board.strip()
        self._manifest_path = manifest_path or output_dir / "manifest.json"
        if not self._board:
            raise ValueError("Pinterest board name cannot be empty.")

    def export(
        self,
        count: int = 25,
        publish_dates: tuple[str, ...] = (),
    ) -> PinterestBulkResult:
        """Prepare up to count new Pin rows and persist their source IDs."""
        if count < 1 or count > 200:
            raise ValueError("Pinterest bulk count must be between 1 and 200.")
        prepared_ids = self._load_prepared_ids()
        listings = sorted(
            self._client.list_shop_active_listings(),
            key=_listing_sort_key,
            reverse=True,
        )
        pins: list[PinterestBulkPin] = []
        skipped_prepared = 0
        skipped_without_images = 0
        for listing in listings:
            listing_id = str(listing.get("listing_id") or "").strip()
            if not listing_id:
                continue
            if listing_id in prepared_ids:
                skipped_prepared += 1
                continue
            images = self._client.list_listing_images(listing_id)
            media_url = _primary_image_url(images)
            if not media_url:
                skipped_without_images += 1
                continue
            publish_date = publish_dates[len(pins)] if len(publish_dates) > len(pins) else ""
            pins.append(
                _pin_from_listing(
                    listing,
                    media_url,
                    self._board,
                    publish_date=publish_date,
                )
            )
            if len(pins) == count:
                break

        self._output_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        csv_path = self._output_dir / f"pinterest_etsy_{count}_{stamp}.csv"
        with csv_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=PINTEREST_COLUMNS)
            writer.writeheader()
            writer.writerows(pin.csv_row() for pin in pins)

        records = self._load_manifest_records()
        records.extend(
            {
                **asdict(pin),
                "status": "PREPARED",
                "prepared_at": datetime.now().isoformat(),
                "csv_path": str(csv_path),
            }
            for pin in pins
        )
        self._manifest_path.parent.mkdir(parents=True, exist_ok=True)
        self._manifest_path.write_text(
            json.dumps({"pins": records}, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return PinterestBulkResult(
            csv_path=str(csv_path),
            manifest_path=str(self._manifest_path),
            pins_prepared=len(pins),
            skipped_prepared=skipped_prepared,
            skipped_without_images=skipped_without_images,
            listing_ids=tuple(pin.etsy_listing_id for pin in pins),
        )

    def _load_manifest_records(self) -> list[dict[str, Any]]:
        if not self._manifest_path.exists():
            return []
        try:
            payload = json.loads(self._manifest_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return []
        pins = payload.get("pins", []) if isinstance(payload, dict) else []
        return [item for item in pins if isinstance(item, dict)]

    def _load_prepared_ids(self) -> set[str]:
        return {
            str(item.get("etsy_listing_id"))
            for item in self._load_manifest_records()
            if item.get("etsy_listing_id")
        }


def _pin_from_listing(
    listing: dict[str, Any],
    media_url: str,
    board: str,
    publish_date: str = "",
) -> PinterestBulkPin:
    listing_id = str(listing["listing_id"])
    raw_title = html.unescape(str(listing.get("title") or "Digital download"))
    tags = _distinct_keyword_phrases(listing.get("tags", ()))
    title = _pinterest_title(raw_title, tags)
    description = _pinterest_description(title, tags)
    url = str(listing.get("url") or f"https://www.etsy.com/listing/{listing_id}")
    return PinterestBulkPin(
        etsy_listing_id=listing_id,
        title=title,
        media_url=media_url,
        board=board,
        description=description,
        link=url,
        keywords=", ".join(tags[:10]),
        publish_date=publish_date,
    )


def _pinterest_title(raw_title: str, tags: tuple[str, ...]) -> str:
    """Build a readable search title without repeating equivalent phrases."""
    base = raw_title.rsplit(" - ", maxsplit=1)[0].strip(" ,.-")
    phrases = [base]
    normalized_base = _normalize_phrase(base)
    for tag in tags:
        normalized_tag = _normalize_phrase(tag)
        if not normalized_tag or normalized_tag in normalized_base:
            continue
        candidate = ", ".join((*phrases, tag.title()))
        if len(candidate) > 100:
            break
        phrases.append(tag.title())
    return _trim_words(", ".join(phrases), 100)


def _pinterest_description(title: str, tags: tuple[str, ...]) -> str:
    """Write Pinterest-oriented copy using distinct, relevant search phrases."""
    use_terms = tags[:4]
    search_context = ", ".join(use_terms)
    if search_context:
        detail = f"Perfect for shoppers searching for {search_context}. "
    else:
        detail = "Perfect for digital craft and printable art projects. "
    return _trim_words(
        f"Discover {title}. {detail}"
        "Use this original RainbowMilkStudio artwork for creative projects, "
        "card making, scrapbooking and thoughtful gifts. "
        "Save this Pin for inspiration and visit Etsy for the complete instant download.",
        500,
    )


def _distinct_keyword_phrases(values: Any) -> tuple[str, ...]:
    """Keep useful Pinterest phrases while removing exact and near duplicates."""
    result: list[str] = []
    normalized: list[str] = []
    for value in values or ():
        phrase = " ".join(html.unescape(str(value)).split()).strip(" ,.-")
        key = _normalize_phrase(phrase)
        if not key or key in normalized:
            continue
        if any(key in existing or existing in key for existing in normalized):
            continue
        result.append(phrase)
        normalized.append(key)
    return tuple(result)


def _normalize_phrase(value: str) -> str:
    return " ".join(
        token
        for token in "".join(
            character.lower() if character.isalnum() else " " for character in value
        ).split()
        if token
    )


def _primary_image_url(images: tuple[dict[str, Any], ...]) -> str:
    ranked = sorted(images, key=lambda item: int(item.get("rank") or 999))
    for image in ranked:
        for key in ("url_fullxfull", "url_570xN", "url_300x300"):
            value = str(image.get(key) or "").strip()
            if value.startswith("https://"):
                return value
    return ""


def _listing_sort_key(listing: dict[str, Any]) -> int:
    for key in ("creation_timestamp", "created_timestamp", "last_modified_timestamp"):
        try:
            return int(listing.get(key) or 0)
        except (TypeError, ValueError):
            pass
    return 0


def _trim_words(value: str, limit: int) -> str:
    clean = " ".join(value.split())
    if len(clean) <= limit:
        return clean
    return clean[: limit + 1].rsplit(" ", maxsplit=1)[0].rstrip(" ,.-")
