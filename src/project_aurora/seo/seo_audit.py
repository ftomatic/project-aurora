"""Audit saved Etsy listing SEO packages for job-specific tags."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from project_aurora.seo.seo_engine import SEOEngine
from project_aurora.storage.memory_manager import MemoryManager

RECONSTRUCTED_SEO_SOURCE = "RECONSTRUCTED_FROM_VERIFIED_JOB_DATA"


def audit_listing_seo(
    memory: MemoryManager,
    reconstruct_missing: bool = True,
    draft_listing_ids: set[str] | None = None,
) -> tuple[dict[str, Any], ...]:
    """Return SEO audit records for saved production reports."""
    records: list[dict[str, Any]] = []
    seen_tags: dict[tuple[str, ...], str] = {}
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
        tag_key = tuple(tag.casefold() for tag in tags)
        duplicate_with = seen_tags.get(tag_key, "") if tag_key else ""
        if tag_key and not duplicate_with:
            seen_tags[tag_key] = product
        status = "VERIFIED"
        if not seo:
            status = "MISSING_SEO"
        elif not _seo_matches_report(seo, report):
            status = "MISMATCH"
        elif not _valid_tags(tags):
            status = "INVALID_TAGS"
        elif duplicate_with:
            status = "DUPLICATE_TAGS"
        records.append(
            {
                "product": product,
                "etsy_listing_id": listing_id_text,
                "seo_package_job_id": str(seo.get("job_id", "")) if seo else "",
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
        print("SEO Package Job ID")
        print(record["seo_package_job_id"])
        print("Tags")
        for tag in record["tags"]:
            print(tag)
        print("Proposed Tags")
        for tag in record["proposed_tags"]:
            print(tag)
        print("Duplicate With Other Listing")
        print(record["duplicate_with_other_listing"] or "None")
        print("Status")
        print(record["status"])
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
        return

    package = SEOEngine().build_package(
        {
            "job_id": job_id,
            "product_name": product_name,
            "product_type": _infer_product_type(product_name),
            "target_buyer": "digital printable buyers",
        }
    )
    record = {
        "job_id": package.job_id,
        "product_name": package.product_name,
        "etsy_listing_id": listing_id,
        "product_type": package.product_type,
        "target_buyer": package.target_buyer,
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
