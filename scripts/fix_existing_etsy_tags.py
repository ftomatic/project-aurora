"""Safely repair tags on existing Etsy draft listings."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Callable

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_PATH))

from project_aurora.integrations.etsy.etsy_client import EtsyClient  # noqa: E402
from project_aurora.integrations.etsy.etsy_config import EtsyConfig  # noqa: E402
from project_aurora.seo.seo_audit import audit_listing_seo  # noqa: E402
from project_aurora.storage.csv_storage import CSVStorage  # noqa: E402
from project_aurora.storage.memory_manager import MemoryManager  # noqa: E402


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Repair Etsy draft tags only.")
    parser.add_argument("--yes", action="store_true", help="Still requires FIX TAGS confirmation.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    """Preview and optionally repair existing Etsy draft tags."""
    parse_args(argv)
    memory = MemoryManager(CSVStorage(base_path=PROJECT_ROOT / "data" / "aurora"))
    config = EtsyConfig.from_environment(PROJECT_ROOT / "config" / "etsy.yaml")
    client = EtsyClient(config)
    report = repair_existing_etsy_tags(memory, client, input)
    print_repair_report(report)


def repair_existing_etsy_tags(
    memory: MemoryManager,
    client: EtsyClient,
    input_fn: Callable[[str], str],
) -> dict[str, Any]:
    """Patch only tags for current Etsy drafts with verified job-specific SEO."""
    audit = audit_listing_seo(memory)
    draft_listings = client.list_shop_draft_listings()
    draft_by_id = {
        str(listing.get("listing_id")): listing
        for listing in draft_listings
        if listing.get("listing_id")
        and str(listing.get("state", "")).casefold() == "draft"
    }
    candidates = _eligible_tag_repair_targets(audit, draft_by_id)

    print("ETSY TAG REPAIR PREVIEW")
    print("Drafts Found")
    print(len(draft_by_id))
    print("")
    print("Drafts Eligible for Tag Repair")
    print(len(candidates))
    print("")
    for record in candidates:
        _print_preview_record(record)

    if len(candidates) != 5:
        report = {
            "status": "ELIGIBLE_DRAFT_COUNT_MISMATCH",
            "drafts_found": len(draft_by_id),
            "eligible": len(candidates),
            "updated": [],
            "skipped": _skipped_records(audit, draft_by_id),
            "errors": (
                "Expected exactly 5 verified current Etsy drafts before tag repair.",
            ),
        }
        memory.save_record("etsy_tag_repairs", "latest", report)
        print("Status")
        print("ELIGIBLE_DRAFT_COUNT_MISMATCH")
        print("Reason")
        print("Expected exactly 5 verified current Etsy drafts before tag repair.")
        return report

    if input_fn("Type FIX 5 TAGS to continue\n").strip() != "FIX 5 TAGS":
        report = {
            "status": "CANCELLED",
            "drafts_found": len(draft_by_id),
            "eligible": len(candidates),
            "updated": [],
            "skipped": len(audit),
        }
        memory.save_record("etsy_tag_repairs", "latest", report)
        return report

    updated: list[dict[str, Any]] = []
    for record in candidates:
        response = client.update_listing_fields(
            str(record["etsy_listing_id"]),
            {"tags": list(record["proposed_tags"])},
        )
        updated.append(
            {
                "product": record["product"],
                "etsy_listing_id": record["etsy_listing_id"],
                "tags": list(record["proposed_tags"]),
                "response": response,
            }
        )
    report = {
        "status": "SUCCESS",
        "drafts_found": len(draft_by_id),
        "eligible": len(candidates),
        "updated": updated,
        "skipped": _skipped_records(audit, draft_by_id),
    }
    memory.save_record("etsy_tag_repairs", "latest", report)
    return report


def _eligible_tag_repair_targets(
    audit: tuple[dict[str, Any], ...],
    draft_by_id: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any], ...]:
    candidates: list[dict[str, Any]] = []
    for record in audit:
        listing_id = str(record.get("etsy_listing_id") or "")
        draft = draft_by_id.get(listing_id)
        if record.get("status") != "PASS" or draft is None:
            continue
        candidates.append(
            {
                "product": record["product"],
                "etsy_listing_id": listing_id,
                "current_state": str(draft.get("state", "")),
                "current_tags": tuple(str(tag) for tag in draft.get("tags", ()) or ()),
                "proposed_tags": tuple(str(tag) for tag in record["tags"]),
                "seo_job_id": str(record["seo_package_job_id"]),
                "verification_status": record["status"],
            }
        )
    return tuple(candidates)


def _skipped_records(
    audit: tuple[dict[str, Any], ...],
    draft_by_id: dict[str, dict[str, Any]],
) -> list[dict[str, str]]:
    skipped: list[dict[str, str]] = []
    for record in audit:
        listing_id = str(record.get("etsy_listing_id") or "")
        if record.get("status") != "PASS":
            reason = str(record.get("status") or "UNVERIFIED")
        elif listing_id not in draft_by_id:
            reason = "NOT_CURRENT_DRAFT"
        else:
            continue
        skipped.append(
            {
                "product": str(record.get("product") or ""),
                "etsy_listing_id": listing_id,
                "reason": reason,
            }
        )
    return skipped


def _print_preview_record(record: dict[str, Any]) -> None:
    print("Product")
    print(record["product"])
    print("Etsy Listing ID")
    print(record["etsy_listing_id"])
    print("Current State")
    print(record["current_state"])
    print("Current Tags")
    for tag in record["current_tags"]:
        print(tag)
    print("Proposed Tags")
    for tag in record["proposed_tags"]:
        print(tag)
    print("SEO Job ID")
    print(record["seo_job_id"])
    print("Verification Status")
    print(record["verification_status"])
    print("")


def print_repair_report(report: dict[str, Any]) -> None:
    """Print repair report."""
    print("ETSY TAG REPAIR")
    print("Status")
    print(report["status"])
    print("Updated")
    print(len(report.get("updated", ())))
    print("Skipped")
    print(len(report.get("skipped", ())) if isinstance(report.get("skipped"), list) else report.get("skipped", 0))


if __name__ == "__main__":
    main()
