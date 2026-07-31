"""Replace Etsy draft listing photos with current local listing previews."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(SRC_PATH))

from project_aurora.config.local_env import load_local_env  # noqa: E402
from project_aurora.integrations.etsy.etsy_client import EtsyClient  # noqa: E402
from project_aurora.integrations.etsy.etsy_config import EtsyConfig  # noqa: E402
from project_aurora.integrations.etsy.etsy_result import EtsyDraftResult  # noqa: E402
from project_aurora.storage.csv_storage import CSVStorage  # noqa: E402
from project_aurora.storage.memory_manager import MemoryManager  # noqa: E402


REPORT_COLLECTION = "production_reports"
LOCAL_ENV_PATH = PROJECT_ROOT / "config" / "aurora.local.env"
ETSY_CONFIG_PATH = PROJECT_ROOT / "config" / "etsy.yaml"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Replace photos on one Etsy draft.")
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--confirm", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    if not args.confirm:
        raise SystemExit("Refusing to replace Etsy listing images without --confirm.")
    load_local_env(LOCAL_ENV_PATH)
    memory = MemoryManager(storage=CSVStorage(base_path=PROJECT_ROOT / "data" / "aurora"))
    report = memory.load_record(REPORT_COLLECTION, args.job_id)
    listing_id = str(report.get("draft_id") or "").strip()
    if not listing_id:
        raise SystemExit("Production report does not contain a draft_id.")
    listing_images_dir = Path(str(report.get("job_paths", {}).get("listing_images_dir") or ""))
    if not listing_images_dir.exists():
        raise SystemExit("Listing images directory does not exist.")
    image_files = tuple(sorted(listing_images_dir.glob("*.png"), key=lambda path: path.name))
    if not image_files:
        raise SystemExit("No local listing preview PNGs found.")
    config = EtsyConfig.from_environment(ETSY_CONFIG_PATH)
    client = EtsyClient(config)
    uploaded = 0
    existing = client.list_listing_images(listing_id)
    for rank, image_path in enumerate(image_files, start=1):
        client.upload_listing_image(listing_id, image_path, rank)
        uploaded += 1
    deleted = 0
    delete_errors: list[str] = []
    for record in existing:
        image_id = _image_id(record)
        if not image_id:
            continue
        try:
            client.delete_listing_image(listing_id, image_id)
            deleted += 1
        except RuntimeError as error:
            delete_errors.append(f"{image_id}: {error}")
    remaining = client.list_listing_images(listing_id)
    result = {
        "job_id": args.job_id,
        "etsy_listing_id": listing_id,
        "deleted_existing_images": deleted,
        "uploaded_images": uploaded,
        "images_after": len(remaining),
        "local_images": [path.name for path in image_files],
        "errors": delete_errors,
    }
    memory.save_record("etsy_image_replacements", args.job_id, result)
    print("ETSY LISTING IMAGE REPLACEMENT")
    print("")
    print("Listing ID")
    print(listing_id)
    print("")
    print("Deleted Existing")
    print(deleted)
    print("")
    print("Uploaded")
    print(uploaded)
    print("")
    print("Images After")
    print(len(remaining))
    print("")
    if delete_errors:
        print("Errors")
        for error in delete_errors:
            print(error)
        print("")
    print("Status")
    print(
        "SUCCESS"
        if len(remaining) == uploaded and not delete_errors
        else "NEEDS_REVIEW"
    )


def _image_id(record: dict[str, object]) -> str:
    value = record.get("listing_image_id") or record.get("image_id")
    return str(value).strip() if value is not None else ""


if __name__ == "__main__":
    main()
