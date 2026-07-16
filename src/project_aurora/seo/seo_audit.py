"""Audit saved Etsy listing SEO packages for job-specific tags."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from project_aurora.seo.seo_engine import SEOEngine
from project_aurora.storage.memory_manager import MemoryManager

RECONSTRUCTED_SEO_SOURCE = "RECONSTRUCTED_FROM_VERIFIED_JOB_DATA"
UNRELATED_TITLE_TERMS = (
    "summer berry",
    "cupcake toppers",
    "favor tags",
    "girls party decor",
    "birthday invitation",
)


def audit_listing_seo(
    memory: MemoryManager,
    reconstruct_missing: bool = True,
    draft_listing_ids: set[str] | None = None,
) -> tuple[dict[str, Any], ...]:
    """Return SEO audit records for saved production reports."""
    records: list[dict[str, Any]] = []
    seen_tags: dict[tuple[str, ...], str] = {}
    seen_titles: dict[str, str] = {}
    for key in sorted(memory.list_records("production_reports")):
        try:
            report = memory.load_record("production_reports", key)
        except FileNotFoundError:
            continue
        job_id = report.get("job_id")
        if not isinstance(job_id, str) or key in {"latest", "latest_batch"}:
            continue
        product = str(report.get("product") or "")
        listing_id = report.get("draft_id")
        listing_id_text = str(listing_id) if listing_id else ""
        if draft_listing_ids is not None and listing_id_text not in draft_listing_ids:
            continue
        if reconstruct_missing:
            _reconstruct_job_seo_if_possible(report)
        seo = _load_job_seo(report)
        tags = tuple(str(tag) for tag in seo.get("tags", ())) if seo else ()
        title = str(seo.get("title", "")) if seo else ""
        tag_key = tuple(tag.casefold() for tag in tags)
        duplicate_with = seen_tags.get(tag_key, "") if tag_key else ""
        if tag_key and not duplicate_with:
            seen_tags[tag_key] = product
        title_key = title.casefold()
        duplicate_title_with = seen_titles.get(title_key, "") if title_key else ""
        if title_key and not duplicate_title_with:
            seen_titles[title_key] = product
        status = "VERIFIED"
        title_status = "MATCH"
        tags_status = "MATCH"
        if not seo:
            status = "MISSING_SEO"
            title_status = "MISSING"
            tags_status = "MISSING"
        elif not _seo_matches_report(seo, report):
            status = "MISMATCH"
            title_status = "MISMATCH"
        elif not _valid_tags(tags):
            status = "INVALID_TAGS"
            tags_status = "INVALID"
        elif not _valid_title(title, product):
            status = "INVALID_TITLE"
            title_status = "INVALID"
        elif duplicate_title_with:
            status = "DUPLICATE_TITLE"
            title_status = "DUPLICATE"
        elif duplicate_with:
            status = "DUPLICATE_TAGS"
            tags_status = "DUPLICATE"
        records.append(
            {
                "product": product,
                "etsy_listing_id": listing_id_text,
                "current_etsy_title": _current_title_from_report(report),
                "proposed_title": title,
                "seo_package_job_id": str(seo.get("job_id", "")) if seo else "",
                "title_match_status": title_status,
                "tags_match_status": tags_status,
                "overall_status": status,
                "tags": tags,
                "proposed_tags": tags,
                "duplicate_with_other_listing": duplicate_with,
                "status": status,
            }
        )
    return tuple(records)


def print_audit(records: tuple[dict[str, Any], ...]) -> None:
    """Print audit records."""
    for record in records:
        print("Product")
        print(record["product"])
        print("Etsy Listing ID")
        print(record["etsy_listing_id"])
        print("Current Etsy Title")
        print(record["current_etsy_title"])
        print("Proposed Job-Specific Title")
        print(record["proposed_title"])
        print("SEO Package Job ID")
        print(record["seo_package_job_id"])
        print("Title Match Status")
        print(record["title_match_status"])
        print("Tags Match Status")
        print(record["tags_match_status"])
        print("Overall Status")
        print(record["overall_status"])
        print("")


def _load_job_seo(report: dict[str, Any]) -> dict[str, Any]:
    job_paths = report.get("job_paths")
    if not isinstance(job_paths, dict):
        return {}
    job_root = job_paths.get("job_root")
    if not isinstance(job_root, str):
        return {}
    seo_path = Path(job_root) / "seo" / "seo_package.json"
    if not seo_path.exists():
        return {}
    data = json.loads(seo_path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def _reconstruct_job_seo_if_possible(report: dict[str, Any]) -> None:
    job_id = report.get("job_id")
    product_name = report.get("product")
    listing_id = report.get("draft_id")
    job_root = _job_root(report)
    if (
        not isinstance(job_id, str)
        or not isinstance(product_name, str)
        or not isinstance(listing_id, str)
        or job_root is None
    ):
        return
    seo_path = job_root / "seo" / "seo_package.json"
    if seo_path.exists():
        existing = _load_job_seo(report)
        if existing and _seo_matches_report(existing, report) and _valid_tags(
            tuple(str(tag) for tag in existing.get("tags", ()))
        ) and _valid_title(str(existing.get("title", "")), product_name):
            return
    else:
        existing = {}
    if seo_path.exists() and not existing:
        return

    package = SEOEngine().build_package(
        {
            "job_id": job_id,
            "etsy_listing_id": listing_id,
            "product_name": product_name,
            "product_type": _infer_product_type(product_name),
            "category": _infer_product_type(product_name),
            "target_buyer": "digital printable buyers",
            "audience": "digital printable buyers",
            "style": str(report.get("style") or ""),
            "source": RECONSTRUCTED_SEO_SOURCE,
        }
    )
    record = {
        "job_id": package.job_id,
        "product_name": package.product_name,
        "etsy_listing_id": listing_id,
        "product_type": package.product_type,
        "category": package.category,
        "target_buyer": package.target_buyer,
        "audience": package.audience,
        "style": package.style,
        "title": package.title,
        "description": package.description,
        "tags": list(package.tags),
        "keywords": list(package.keywords),
        "buyer_use_case": package.buyer_use_case,
        "product_positioning": package.product_positioning,
        "seo_score": package.seo_score,
        "warnings": list(package.warnings),
        "created_at": package.created_at.isoformat(),
        "generated_at": package.generated_at.isoformat(),
        "source": RECONSTRUCTED_SEO_SOURCE,
    }
    if not _seo_matches_report(record, report):
        return
    if not _valid_tags(tuple(record["tags"])):
        return
    if not _valid_title(str(record["title"]), product_name):
        return
    seo_path.parent.mkdir(parents=True, exist_ok=True)
    seo_path.write_text(
        json.dumps(record, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _seo_matches_report(seo: dict[str, Any], report: dict[str, Any]) -> bool:
    return (
        seo.get("job_id") == report.get("job_id")
        and seo.get("product_name") == report.get("product")
        and str(seo.get("etsy_listing_id") or report.get("draft_id") or "")
        == str(report.get("draft_id") or "")
    )


def _valid_tags(tags: tuple[str, ...]) -> bool:
    normalized = tuple(tag.strip() for tag in tags)
    return (
        len(normalized) == 13
        and all(normalized)
        and all(len(tag) <= 20 for tag in normalized)
        and len({tag.casefold() for tag in normalized}) == 13
    )


def _valid_title(title: str, product_name: str) -> bool:
    normalized = title.strip()
    if not normalized or len(normalized) > 140:
        return False
    lowered = normalized.casefold()
    product_lower = product_name.casefold()
    if any(term in lowered for term in UNRELATED_TITLE_TERMS):
        return False
    product_tokens = {
        token
        for token in product_lower.replace("-", " ").split()
        if len(token) > 2
    }
    title_tokens = set(lowered.replace("-", " ").replace(",", " ").split())
    if not (product_tokens & title_tokens):
        return False
    if "wildflower wedding invitation" in product_lower:
        required = ({"wildflower", "wedding", "invitation"}, {"floral"}, {"printable", "digital"})
        if not all(group & title_tokens for group in required):
            return False
    if "clipart" in product_lower and not ({"clipart", "graphics"} & title_tokens):
        return False
    if "sticker" in product_lower and "sticker" not in title_tokens and "stickers" not in title_tokens:
        return False
    if "paper" in product_lower and "paper" not in title_tokens:
        return False
    if "birthday" in product_lower and ({"wall", "art"} <= title_tokens):
        return False
    if "clipart" in product_lower and ({"wall", "art"} <= title_tokens):
        return False
    return True


def _current_title_from_report(report: dict[str, Any]) -> str:
    metadata = report.get("metadata")
    if not isinstance(metadata, dict):
        return "UNKNOWN_NOT_QUERIED"
    etsy_draft = metadata.get("etsy_draft")
    if isinstance(etsy_draft, dict):
        response = etsy_draft.get("response")
        if isinstance(response, dict) and isinstance(response.get("title"), str):
            return response["title"]
        if isinstance(etsy_draft.get("title"), str):
            return etsy_draft["title"]
    return "UNKNOWN_NOT_QUERIED"


def _job_root(report: dict[str, Any]) -> Path | None:
    job_paths = report.get("job_paths")
    if not isinstance(job_paths, dict):
        return None
    job_root = job_paths.get("job_root")
    if not isinstance(job_root, str) or not job_root.strip():
        return None
    return Path(job_root)


def _infer_product_type(product_name: str) -> str:
    lowered = product_name.casefold()
    if "invitation" in lowered or "birthday" in lowered or "party" in lowered:
        return "party printable"
    if "sticker" in lowered:
        return "sticker sheet"
    if "digital paper" in lowered or "paper" in lowered:
        return "digital paper"
    if "print" in lowered or "art" in lowered:
        return "wall art"
    return "clipart"
