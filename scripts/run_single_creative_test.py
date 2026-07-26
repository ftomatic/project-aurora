"""Run one creative image test and stop before Etsy upload unless requested."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(SRC_PATH))

from project_aurora.integrations.etsy.etsy_config import EtsyConfig  # noqa: E402
from project_aurora.image_generation.provider_registry import ImageProviderConfig  # noqa: E402
from project_aurora.planning.production_queue_manager import ProductionQueueManager  # noqa: E402
from project_aurora.production.product_factory import DefaultProductFactoryStageRunner  # noqa: E402
from project_aurora.storage.csv_storage import CSVStorage  # noqa: E402
from project_aurora.storage.memory_manager import MemoryManager  # noqa: E402
from scripts.run_batch_factory import load_openai_api_key  # noqa: E402


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run one Aurora creative test.")
    parser.add_argument("--count", type=int, default=1)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--upload", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    if not args.live:
        print("SINGLE CREATIVE TEST")
        print("Status")
        print("DRY_RUN_ONLY")
        print("Use --live to generate images. Etsy upload is still disabled unless --upload is supplied.")
        return
    if args.upload:
        raise SystemExit("Use scripts/run_batch_factory.py --live for Etsy upload.")
    _run_live_without_upload(args.count)


def _run_live_without_upload(count: int) -> None:
    queue = ProductionQueueManager(
        queue_path=PROJECT_ROOT / "data" / "aurora" / "production_queue" / "queue.json"
    )
    job = queue.next_ready_job()
    if job is None:
        print("SINGLE CREATIVE TEST")
        print("Status")
        print("NO_READY_JOB")
        return
    memory = MemoryManager(CSVStorage(base_path=PROJECT_ROOT / "data" / "aurora"))
    etsy_config = EtsyConfig.from_environment(
        PROJECT_ROOT / "config" / "etsy.yaml",
        PROJECT_ROOT / "config" / "aurora.local.env",
    )
    image_config = ImageProviderConfig.from_file(PROJECT_ROOT / "config" / "openai.yaml")
    openai_api_key = load_openai_api_key(PROJECT_ROOT / "config" / "aurora.local.env")
    if not openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is required in config/aurora.local.env.")
    image_config = ImageProviderConfig(
        provider=image_config.provider,
        model=image_config.model,
        size=image_config.size,
        quality=image_config.quality,
        background=image_config.background,
        output_format=image_config.output_format,
        number_of_images=image_config.number_of_images,
        prompt_version=image_config.prompt_version,
        openai_api_key=openai_api_key,
    )
    runner = DefaultProductFactoryStageRunner(
        memory=memory,
        etsy_config=etsy_config,
        image_config=image_config,
    )
    print("SINGLE CREATIVE TEST")
    print("Product")
    print(job.product_name)
    prompt = runner.compose_prompts(job)
    images = runner.generate_images(job)
    qa = runner.run_image_qa(job)
    export = runner.export_commercial_images(job)
    commercial = runner.run_commercial_image_qa(job)
    print("Images Generated")
    print(len(getattr(images, "generated_files", ())))
    print("Image QA Results")
    print(len(qa) if isinstance(qa, tuple) else 0)
    print("Final Files")
    print(len(getattr(export, "exported_files", ())))
    print("Commercial QA")
    print(getattr(commercial, "status", ""))
    print("Status")
    print("STOPPED_BEFORE_ETSY_UPLOAD")


if __name__ == "__main__":
    main()
