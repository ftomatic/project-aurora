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
from project_aurora.storage.csv_storage import CSVStorage  # noqa: E402
from project_aurora.storage.memory_manager import MemoryManager  # noqa: E402
from scripts.audit_etsy_listing_seo import audit_listing_seo  # noqa: E402


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
    """Patch only tags for listings with verified job-specific SEO."""
    audit = audit_listing_seo(memory)
    candidates = tuple(
        record
        for record in audit
        if record["status"] == "PASS" and record["etsy_listing_id"]
    )
    print("ETSY TAG REPAIR PREVIEW")
    for record in candidates:
        print(record["product"])
        print(record["etsy_listing_id"])
        for tag in record["tags"]:
            print(tag)
        print("")
    if input_fn("Type FIX TAGS to continue\n").strip() != "FIX TAGS":
        report = {"status": "CANCELLED", "updated": [], "skipped": len(audit)}
        memory.save_record("etsy_tag_repairs", "latest", report)
        return report
    updated: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for record in audit:
        if record not in candidates:
            skipped.append({"product": record["product"], "reason": record["status"]})
            continue
        response = client.update_listing_fields(
            str(record["etsy_listing_id"]),
            {"tags": list(record["tags"])},
        )
        updated.append(
            {
                "product": record["product"],
                "etsy_listing_id": record["etsy_listing_id"],
                "tags": list(record["tags"]),
                "response": response,
            }
        )
    report = {"status": "SUCCESS", "updated": updated, "skipped": skipped}
    memory.save_record("etsy_tag_repairs", "latest", report)
    return report


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
