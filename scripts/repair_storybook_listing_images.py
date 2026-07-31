"""Repair STORYBOOK Etsy draft photos to four full-scene listing images."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path
from time import sleep

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_PATH))

from project_aurora.config.local_env import load_local_env  # noqa: E402
from project_aurora.image_generation.image_generation_engine import ImageGenerationEngine  # noqa: E402
from project_aurora.image_generation.listing_family_decision import LISTING_FAMILY_STORYBOOK  # noqa: E402
from project_aurora.image_generation.listing_preview_exporter import ListingPreviewExporter  # noqa: E402
from project_aurora.image_generation.provider_registry import ImageProviderConfig  # noqa: E402
from project_aurora.integrations.etsy.etsy_client import EtsyClient  # noqa: E402
from project_aurora.integrations.etsy.etsy_config import EtsyConfig  # noqa: E402
from project_aurora.storage.csv_storage import CSVStorage  # noqa: E402
from project_aurora.storage.memory_manager import MemoryManager  # noqa: E402


REPORT_COLLECTION = "production_reports"
TARGET_STORYBOOK_SCENES = 4
LOCAL_ENV_PATH = PROJECT_ROOT / "config" / "aurora.local.env"
OPENAI_CONFIG_PATH = PROJECT_ROOT / "config" / "openai.yaml"
ETSY_CONFIG_PATH = PROJECT_ROOT / "config" / "etsy.yaml"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Repair existing STORYBOOK Etsy draft listing photos."
    )
    parser.add_argument("--job-id", action="append", default=[])
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--confirm", action="store_true")
    parser.add_argument("--skip-etsy", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    if not args.confirm:
        raise SystemExit("Refusing to repair Etsy listing images without --confirm.")
    load_local_env(LOCAL_ENV_PATH)
    memory = MemoryManager(storage=CSVStorage(base_path=PROJECT_ROOT / "data" / "aurora"))
    image_config = ImageProviderConfig.from_file(OPENAI_CONFIG_PATH)
    etsy_client = None if args.skip_etsy else EtsyClient(EtsyConfig.from_environment(ETSY_CONFIG_PATH))

    reports = _target_reports(memory, args.job_id, args.limit)
    print("STORYBOOK LISTING IMAGE REPAIR")
    print("")
    print("Targets")
    print(len(reports))
    print("")
    for report in reports:
        _repair_one(memory, image_config, etsy_client, report, skip_etsy=args.skip_etsy)


def _target_reports(
    memory: MemoryManager,
    job_ids: list[str],
    limit: int,
) -> list[dict[str, object]]:
    if job_ids:
        reports = [memory.load_record(REPORT_COLLECTION, job_id) for job_id in job_ids]
    else:
        records = []
        for path in sorted(
            (PROJECT_ROOT / "data" / "aurora" / REPORT_COLLECTION).glob("*.json"),
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        ):
            if path.name.startswith(("latest", "batch", "failed_batch")):
                continue
            try:
                record = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            if _is_storybook_repair_candidate(record):
                records.append(record)
        reports = records
    if limit > 0:
        return reports[:limit]
    return reports


def _is_storybook_repair_candidate(report: dict[str, object]) -> bool:
    draft_id = str(report.get("draft_id") or "").strip()
    if not draft_id:
        return False
    paths = report.get("job_paths")
    if not isinstance(paths, dict):
        return False
    scene_dir = Path(str(paths.get("storybook_scenes_dir") or ""))
    listing_dir = Path(str(paths.get("listing_images_dir") or ""))
    if not scene_dir.exists():
        return False
    scene_count = len(tuple(scene_dir.glob("*.png")))
    listing_count = len(tuple(listing_dir.glob("*.png"))) if listing_dir.exists() else 0
    return scene_count < TARGET_STORYBOOK_SCENES or listing_count != TARGET_STORYBOOK_SCENES


def _repair_one(
    memory: MemoryManager,
    image_config: ImageProviderConfig,
    etsy_client: EtsyClient | None,
    report: dict[str, object],
    *,
    skip_etsy: bool,
) -> None:
    job_id = str(report.get("job_id") or "").strip()
    product = str(report.get("product") or "").strip()
    listing_id = str(report.get("draft_id") or "").strip()
    job_paths = report.get("job_paths")
    if not isinstance(job_paths, dict):
        raise RuntimeError(f"{job_id}: production report is missing job_paths.")
    scene_dir = Path(str(job_paths.get("storybook_scenes_dir") or ""))
    listing_dir = Path(str(job_paths.get("listing_images_dir") or ""))
    final_dir = Path(str(job_paths.get("final_product_images_dir") or ""))
    scene_dir.mkdir(parents=True, exist_ok=True)
    listing_dir.mkdir(parents=True, exist_ok=True)

    prompt_package = memory.load_prompt_package(job_id)
    fingerprint = _art_direction_fingerprint(prompt_package, scene_dir)
    existing = tuple(sorted(scene_dir.glob("*.png"), key=lambda item: item.name))
    missing = max(0, TARGET_STORYBOOK_SCENES - len(existing))
    if missing:
        _generate_missing_scenes(
            memory=memory,
            image_config=image_config,
            job_id=job_id,
            product=product,
            prompt_package=prompt_package,
            scene_dir=scene_dir,
            start_index=len(existing) + 1,
            missing=missing,
        )
        _write_asset_manifest(scene_dir, fingerprint)

    _rebuild_previews(
        final_dir=final_dir,
        scene_dir=scene_dir,
        listing_dir=listing_dir,
        report=report,
        fingerprint=fingerprint,
    )
    uploaded = 0
    deleted = 0
    images_after = len(tuple(listing_dir.glob("*.png")))
    if not skip_etsy:
        assert etsy_client is not None
        deleted, uploaded, images_after = _replace_etsy_images(
            etsy_client,
            listing_id,
            tuple(sorted(listing_dir.glob("*.png"), key=lambda item: item.name)),
        )
    result = {
        "job_id": job_id,
        "product": product,
        "etsy_listing_id": listing_id,
        "storybook_scenes": len(tuple(scene_dir.glob("*.png"))),
        "listing_previews": len(tuple(listing_dir.glob("*.png"))),
        "etsy_deleted": deleted,
        "etsy_uploaded": uploaded,
        "etsy_images_after": images_after,
        "updated_at": datetime.now().isoformat(),
    }
    memory.save_record("storybook_listing_image_repairs", job_id, result)
    print("Product")
    print(product)
    print("Listing ID")
    print(listing_id)
    print("Storybook Scenes")
    print(result["storybook_scenes"])
    print("Listing Images")
    print(result["listing_previews"])
    print("Uploaded To Etsy")
    print(uploaded)
    print("Images After")
    print(images_after)
    print("Status")
    print("SUCCESS" if result["listing_previews"] == TARGET_STORYBOOK_SCENES and images_after == TARGET_STORYBOOK_SCENES else "NEEDS_REVIEW")
    print("")


def _generate_missing_scenes(
    *,
    memory: MemoryManager,
    image_config: ImageProviderConfig,
    job_id: str,
    product: str,
    prompt_package: dict[str, object],
    scene_dir: Path,
    start_index: int,
    missing: int,
) -> None:
    temp_dir = scene_dir / f"repair_generation_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    scene_prompt = str(
        prompt_package.get("storybook_scene_prompt")
        or prompt_package.get("image_prompt")
        or ""
    )
    repair_package = dict(prompt_package)
    repair_package["product_name"] = f"{product} Storybook Scene Variation"
    repair_package["image_prompt"] = (
        scene_prompt
        + "\n\nCreate distinct coordinated scene variations for the same Etsy listing. "
        + "Each image must be a complete warm watercolor storybook scene, not clipart, "
        + "not a grid, not a transparent asset sheet. Keep the same subject, activity, "
        + "palette, clothing style, and cozy woodland atmosphere, but vary pose, framing, "
        + "garden details, props, and background composition."
    )
    repair_package["transparent_background"] = False
    repair_package["openai_background"] = "opaque"
    repair_package_id = f"{job_id}_storybook_scene_repair"
    memory.save_prompt_package(repair_package, package_id=repair_package_id)
    result = ImageGenerationEngine(
        memory=memory,
        output_dir=temp_dir,
        provider_config=image_config,
    ).run(
        prompt_package_id=repair_package_id,
        provider=image_config.provider,
        image_type="storybook_scene",
        width=1024,
        height=1024,
        dpi=300,
        size=image_config.size,
        quality=image_config.quality,
        transparent_background=False,
        background="opaque",
        output_format=image_config.output_format,
        number_of_images=missing,
    )
    if result.status != "SUCCESS":
        raise RuntimeError("; ".join(result.errors) or "Storybook scene repair generation failed.")
    generated = tuple(Path(path) for path in result.generated_files)
    for offset, path in enumerate(generated, start=start_index):
        target = scene_dir / f"{_safe_slug(product)}_scene_{offset:02d}.png"
        shutil.move(str(path), target)
    shutil.rmtree(temp_dir, ignore_errors=True)


def _rebuild_previews(
    *,
    final_dir: Path,
    scene_dir: Path,
    listing_dir: Path,
    report: dict[str, object],
    fingerprint: str,
) -> None:
    for path in listing_dir.glob("*.png"):
        path.unlink()
    result = ListingPreviewExporter(
        final_images_dir=final_dir,
        storybook_scenes_dir=scene_dir,
        output_dir=listing_dir,
        output_prefix=f"{str(report.get('job_id') or '')[:8]}_{_safe_slug(str(report.get('product') or 'storybook'))}",
        listing_family=LISTING_FAMILY_STORYBOOK,
        art_direction_fingerprint=fingerprint,
    ).export()
    if result.status != "SUCCESS":
        raise RuntimeError("; ".join(result.errors) or "Listing preview export failed.")
    if len(result.preview_files) != TARGET_STORYBOOK_SCENES:
        raise RuntimeError(f"Expected {TARGET_STORYBOOK_SCENES} listing previews, found {len(result.preview_files)}.")


def _replace_etsy_images(
    client: EtsyClient,
    listing_id: str,
    image_files: tuple[Path, ...],
) -> tuple[int, int, int]:
    existing = client.list_listing_images(listing_id)
    uploaded = 0
    for rank, image_path in enumerate(image_files, start=1):
        _upload_listing_image_with_retry(client, listing_id, image_path, rank)
        uploaded += 1
    deleted = 0
    for record in existing:
        image_id = str(record.get("listing_image_id") or record.get("image_id") or "").strip()
        if image_id:
            client.delete_listing_image(listing_id, image_id)
            deleted += 1
    remaining = client.list_listing_images(listing_id)
    return deleted, uploaded, len(remaining)


def _upload_listing_image_with_retry(
    client: EtsyClient,
    listing_id: str,
    image_path: Path,
    rank: int,
) -> None:
    attempts = 4
    waits = (5, 15, 30)
    for attempt in range(1, attempts + 1):
        try:
            client.upload_listing_image(listing_id, image_path, rank)
            return
        except RuntimeError as error:
            if not _is_retryable_upload_error(error) or attempt >= attempts:
                raise
            wait = waits[min(attempt - 1, len(waits) - 1)]
            print("UPLOAD RETRY")
            print("File")
            print(image_path.name)
            print("Attempt")
            print(f"{attempt + 1} of {attempts}")
            print("Reason")
            print(error)
            print("Waiting")
            print(f"{wait} seconds")
            sleep(wait)


def _is_retryable_upload_error(error: RuntimeError) -> bool:
    text = str(error).casefold()
    return any(
        marker in text
        for marker in (
            "broken pipe",
            "errno 32",
            "timed out",
            "remote disconnected",
            "http 429",
            "http 500",
            "http 502",
            "http 503",
            "http 504",
        )
    )


def _art_direction_fingerprint(prompt_package: dict[str, object], scene_dir: Path) -> str:
    value = str(prompt_package.get("art_direction_fingerprint") or "").strip()
    if value:
        return value
    manifest_path = scene_dir / "asset_manifest.json"
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return ""
        return str(manifest.get("art_direction_fingerprint") or "").strip()
    return ""


def _write_asset_manifest(scene_dir: Path, fingerprint: str) -> None:
    (scene_dir / "asset_manifest.json").write_text(
        json.dumps(
            {
                "art_direction_fingerprint": fingerprint,
                "source_stage": "storybook_scene_repair",
                "scene_count": TARGET_STORYBOOK_SCENES,
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def _safe_slug(value: str) -> str:
    return (
        value.casefold()
        .replace("&", "and")
        .replace("/", "_")
        .replace(" ", "_")
        .replace("-", "_")
    )


if __name__ == "__main__":
    main()
