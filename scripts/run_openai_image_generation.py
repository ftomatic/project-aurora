"""Run Aurora image generation with the configured provider."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(SRC_PATH))

from project_aurora.image_generation.image_cost_estimator import (  # noqa: E402
    ImageCostEstimator,
)
from project_aurora.image_generation.image_generation_engine import (  # noqa: E402
    ImageGenerationEngine,
)
from project_aurora.image_generation.provider_registry import (  # noqa: E402
    ImageProviderConfig,
)
from project_aurora.storage.csv_storage import CSVStorage  # noqa: E402
from project_aurora.storage.memory_manager import MemoryManager  # noqa: E402
from scripts.run_image_generation_demo import ensure_prompt_package  # noqa: E402


def main() -> None:
    """Generate images using Aurora's configured image provider."""
    config = ImageProviderConfig.from_file(
        PROJECT_ROOT / "config" / "openai.yaml"
    )
    memory = MemoryManager(
        storage=CSVStorage(base_path=PROJECT_ROOT / "data" / "aurora")
    )
    prompt_package_id = ensure_prompt_package(memory)
    prompt_package = memory.load_prompt_package(prompt_package_id)
    cost_estimate = ImageCostEstimator().estimate(
        provider=config.provider,
        quality=config.quality,
        number_of_images=config.number_of_images,
    )

    print("IMAGE GENERATION")
    print("")
    print("Provider")
    print("OpenAI GPT Image" if config.provider == "openai" else config.provider)
    print("")
    print("Collection")
    print(prompt_package.get("collection", "Unknown Collection"))
    print("")
    print("Images")
    print(config.number_of_images)
    print("")
    print("Estimated Cost")
    print(cost_estimate.render())
    print("")

    try:
        engine = ImageGenerationEngine(
            memory=memory,
            provider_config=config,
            output_dir=PROJECT_ROOT / "data" / "aurora" / "generated_images",
        )
        result = engine.run(
            prompt_package_id=prompt_package_id,
            provider=config.provider,
            size=config.size,
            quality=config.quality,
            background=config.background,
            output_format=config.output_format,
            number_of_images=config.number_of_images,
        )
    except RuntimeError as error:
        print("Status")
        print("CONFIGURATION_REQUIRED")
        print("")
        print("Reason")
        print(error)
        raise SystemExit(1) from error

    print("Status")
    print(result.status)


if __name__ == "__main__":
    main()
