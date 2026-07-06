"""Run Aurora's mock image generation engine demo."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(SRC_PATH))

from project_aurora.image_generation.image_generation_engine import (  # noqa: E402
    ImageGenerationEngine,
)
from project_aurora.storage.csv_storage import CSVStorage  # noqa: E402
from project_aurora.storage.memory_manager import MemoryManager  # noqa: E402
from scripts.run_prompt_factory import ensure_sample_queue  # noqa: E402
from project_aurora.prompt_factory.prompt_factory import PromptFactory  # noqa: E402


def ensure_prompt_package(memory: MemoryManager) -> str:
    """Create local prompt package data for the demo."""
    ensure_sample_queue()
    result = PromptFactory(memory=memory).run()
    return result.saved_package_ids[0]


def main() -> None:
    """Generate placeholder images from a stored prompt package."""
    memory = MemoryManager(
        storage=CSVStorage(base_path=PROJECT_ROOT / "data" / "aurora")
    )
    prompt_package_id = ensure_prompt_package(memory)
    engine = ImageGenerationEngine(
        memory=memory,
        output_dir=PROJECT_ROOT / "data" / "aurora" / "generated_images",
    )
    result = engine.run(prompt_package_id=prompt_package_id, provider="mock")

    print("IMAGE GENERATION ENGINE")
    print("")
    print("Provider")
    print(result.provider)
    print("")
    print("Prompt Package")
    print("Loaded")
    print("")
    print("Images Generated")
    print(len(result.generated_files))
    print("")
    print("Output Folder")
    print("data/aurora/generated_images/")
    print("")
    print("Status")
    print(result.status)


if __name__ == "__main__":
    main()
