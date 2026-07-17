"""Safely preview and repair current Etsy draft metadata/uploads."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_PATH))

from project_aurora.integrations.etsy.etsy_client import EtsyClient  # noqa: E402
from project_aurora.integrations.etsy.etsy_config import EtsyConfig  # noqa: E402
from project_aurora.integrations.etsy.etsy_taxonomy_resolver import EtsyTaxonomyResolver  # noqa: E402
from project_aurora.merchandising.pricing_engine import PricingEngine  # noqa: E402
from project_aurora.storage.csv_storage import CSVStorage  # noqa: E402
from project_aurora.storage.memory_manager import MemoryManager  # noqa: E402


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Repair current Etsy drafts safely.")
    parser.add_argument("--preview", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    memory = MemoryManager(CSVStorage(base_path=PROJECT_ROOT / "data" / "aurora"))
    config = EtsyConfig.from_environment(PROJECT_ROOT / "config" / "etsy.yaml")
    client = EtsyClient(config)
    try:
        report = build_repair_preview(memory, client)
    except RuntimeError as error:
        print("ETSY DRAFT REPAIR PREVIEW")
        print("")
        print("Status")
        print("CONFIGURATION_REQUIRED")
        print("")
        print("Reason")
        print(str(error))
        return
    print_repair_preview(report)
    if args.preview:
        return
    expected = f"REPAIR {len(report['eligible'])} DRAFTS"
    confirmation = input(f"Type {expected} to continue: ")
    if confirmation != expected:
        print("Repair cancelled.")
        return
    # Actual updates are intentionally conservative in this sprint; upload services
    # remain the source of truth for missing files and are invoked by recovery flows.
    memory.save_record("etsy_draft_repairs", "latest", report)


def build_repair_preview(memory: MemoryManager, client: EtsyClient) -> dict[str, Any]:
    drafts = client.list_shop_draft_listings()
    draft_by_id = {
        str(draft.get("listing_id")): draft
        for draft in drafts
        if draft.get("listing_id") is not None
    }
    eligible: list[dict[str, Any]] = []
    for report_id in memory.list_records("production_reports"):
        if report_id == "latest":
            continue
        report = memory.load_record("production_reports", report_id)
        listing_id = str(report.get("draft_id") or "")
        if listing_id not in draft_by_id:
            continue
        product = str(report.get("product") or "")
        style = str(report.get("style") or "")
        job_paths = report.get("job_paths") if isinstance(report.get("job_paths"), dict) else {}
        category = _category_from_report(memory, report_id, product)
        taxonomy = EtsyTaxonomyResolver().resolve(
            product_name=product,
            product_type=category,
            category=category,
        )
        pricing = PricingEngine().resolve_price(
            product_name=product,
            product_type=category,
            category=category,
            bundle_size=4,
            image_count=4,
            commercial_license=True,
            competition_level="Medium",
            demand_score=0.85,
            confidence_score=0.85,
        )
        final_dir = Path(str(job_paths.get("final_product_images_dir", "")))
        final_files = tuple(sorted(final_dir.glob("*.png"))) if final_dir.exists() else ()
        draft = draft_by_id[listing_id]
        eligible.append(
            {
                "product": product,
                "listing_id": listing_id,
                "current_taxonomy": draft.get("taxonomy_id"),
                "proposed_taxonomy": taxonomy.taxonomy_id,
                "proposed_taxonomy_path": taxonomy.full_taxonomy_path,
                "current_price": draft.get("price"),
                "proposed_price": pricing.launch_price,
                "images_present": "unknown",
                "images_missing": max(0, 4 - len(final_files)),
                "downloads_present": "unknown",
                "downloads_missing": max(0, 4 - len(final_files)),
                "verification_status": "VERIFIED" if taxonomy.resolved and len(final_files) == 4 else "INCOMPLETE",
                "style": style,
            }
        )
    return {
        "drafts_found": len(drafts),
        "eligible": eligible,
        "created_at": datetime.now().isoformat(),
    }


def print_repair_preview(report: dict[str, Any]) -> None:
    print("ETSY DRAFT REPAIR PREVIEW")
    print("")
    print("Drafts Found")
    print(report["drafts_found"])
    for item in report["eligible"]:
        print("")
        print("Product")
        print(item["product"])
        print("Listing ID")
        print(item["listing_id"])
        print("Current Taxonomy")
        print(item["current_taxonomy"])
        print("Proposed Taxonomy")
        print(item["proposed_taxonomy"])
        print("Current Price")
        print(item["current_price"])
        print("Proposed Price")
        print(item["proposed_price"])
        print("Images Present")
        print(item["images_present"])
        print("Images Missing")
        print(item["images_missing"])
        print("Downloads Present")
        print(item["downloads_present"])
        print("Downloads Missing")
        print(item["downloads_missing"])
        print("Verification Status")
        print(item["verification_status"])


def _category_from_report(memory: MemoryManager, report_id: str, product: str) -> str:
    try:
        seo = memory.load_seo_package(report_id)
    except FileNotFoundError:
        return product
    return str(seo.get("product_type") or seo.get("category") or product)


if __name__ == "__main__":
    main()
