"""Audit saved Etsy listing SEO packages for job-specific tags."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from project_aurora.storage.memory_manager import MemoryManager


def audit_listing_seo(memory: MemoryManager) -> tuple[dict[str, Any], ...]:
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
        seo = _load_job_seo(report)
        tags = tuple(str(tag) for tag in seo.get("tags", ())) if seo else ()
        tag_key = tuple(tag.casefold() for tag in tags)
        duplicate_with = seen_tags.get(tag_key, "") if tag_key else ""
        if tag_key and not duplicate_with:
            seen_tags[tag_key] = product
        status = "PASS"
        if not seo:
            status = "MISSING_SEO"
        elif seo.get("job_id") != job_id or seo.get("product_name") != product:
            status = "MISMATCH"
        elif duplicate_with:
            status = "DUPLICATE_TAGS"
        records.append(
            {
                "product": product,
                "etsy_listing_id": str(listing_id) if listing_id else "",
                "seo_package_job_id": str(seo.get("job_id", "")) if seo else "",
                "tags": tags,
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
