"""Safely repair descriptions on existing Etsy draft listings."""

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
    parser = argparse.ArgumentParser(description="Repair Etsy draft descriptions only.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    """Preview and optionally repair existing Etsy draft descriptions."""
    parse_args(argv)
    memory = MemoryManager(CSVStorage(base_path=PROJECT_ROOT / "data" / "aurora"))
    config = EtsyConfig.from_environment(PROJECT_ROOT / "config" / "etsy.yaml")
    client = EtsyClient(config)
    report = repair_existing_etsy_descriptions(memory, client, input)
    print_description_repair_report(report)


def repair_existing_etsy_descriptions(
    memory: MemoryManager,
    client: EtsyClient,
    input_fn: Callable[[str], str],
) -> dict[str, Any]:
    """Patch only descriptions for current Etsy drafts with verified job SEO."""
    drafts = client.list_shop_draft_listings()
    draft_by_id = {
        str(draft.get("listing_id")): draft
        for draft in drafts
        if draft.get("listing_id")
        and str(draft.get("state", "")).casefold() == "draft"
    }
    audit = audit_listing_seo(memory, reconstruct_missing=True)
    candidates = _eligible_description_repair_targets(audit, draft_by_id)
    skipped = _skipped_records(audit, draft_by_id)

    print("ETSY DESCRIPTION REPAIR PREVIEW")
    print("Drafts Found")
    print(len(draft_by_id))
    print("")
    print("Verified Drafts")
    print(len(candidates))
    print("")
    print("Unverified Drafts")
    print(len(skipped))
    print("")
    for record in candidates:
        _print_preview_record(record)

    expected_confirmation = f"FIX {len(candidates)} DESCRIPTIONS"
    if not candidates:
        report = {
            "status": "NO_VERIFIED_DESCRIPTION_REPAIRS",
            "drafts_found": len(draft_by_id),
            "verified_drafts": 0,
            "updated": [],
            "skipped": skipped,
        }
        memory.save_record("etsy_description_repairs", "latest", report)
        return report
    if input_fn(f"Type {expected_confirmation} to continue\n").strip() != expected_confirmation:
        report = {
            "status": "CANCELLED",
            "drafts_found": len(draft_by_id),
            "verified_drafts": len(candidates),
            "updated": [],
            "skipped": skipped,
        }
        memory.save_record("etsy_description_repairs", "latest", report)
        return report

    updated: list[dict[str, Any]] = []
    for record in candidates:
        response = client.update_listing_fields(
            str(record["etsy_listing_id"]),
            {"description": str(record["proposed_description"])},
        )
        updated.append(
            {
                "product": record["product"],
                "etsy_listing_id": record["etsy_listing_id"],
                "description": record["proposed_description"],
                "response": response,
            }
        )
    report = {
        "status": "SUCCESS",
        "drafts_found": len(draft_by_id),
        "verified_drafts": len(candidates),
        "updated": updated,
        "skipped": skipped,
    }
    memory.save_record("etsy_description_repairs", "latest", report)
    return report


def _eligible_description_repair_targets(
    audit: tuple[dict[str, Any], ...],
    draft_by_id: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any], ...]:
    candidates: list[dict[str, Any]] = []
    for record in audit:
        listing_id = str(record.get("etsy_listing_id") or "")
        draft = draft_by_id.get(listing_id)
        description = str(record.get("proposed_description") or "").strip()
        if (
            record.get("overall_status") != "VERIFIED"
            or record.get("description_match_status") not in {"MATCH", "UNKNOWN"}
            or draft is None
            or not description
            or len(description) > 13000
        ):
            continue
        candidates.append(
            {
                "product": record["product"],
                "etsy_listing_id": listing_id,
                "current_state": str(draft.get("state", "")),
                "current_description": str(draft.get("description", "")),
                "proposed_description": description,
                "seo_job_id": str(record["seo_package_job_id"]),
                "verification_status": record["overall_status"],
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
        if listing_id not in draft_by_id:
            reason = "NOT_CURRENT_DRAFT"
        elif record.get("overall_status") != "VERIFIED":
            reason = str(record.get("overall_status") or "UNVERIFIED")
        elif not str(record.get("proposed_description") or "").strip():
            reason = "MISSING_DESCRIPTION"
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
    print("Current Description")
    print(record["current_description"])
    print("Proposed Description")
    print(record["proposed_description"])
    print("SEO Job ID")
    print(record["seo_job_id"])
    print("Verification Status")
    print(record["verification_status"])
    print("")


def print_description_repair_report(report: dict[str, Any]) -> None:
    """Print description repair report."""
    print("ETSY DESCRIPTION REPAIR")
    print("Status")
    print(report["status"])
    print("Updated")
    print(len(report.get("updated", ())))
    print("Skipped")
    print(len(report.get("skipped", ())) if isinstance(report.get("skipped"), list) else report.get("skipped", 0))


if __name__ == "__main__":
    main()
