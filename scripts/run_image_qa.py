"""Run Aurora's local image QA engine."""

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
from project_aurora.image_qa.qa_engine import ImageQAEngine  # noqa: E402
from project_aurora.image_qa.qa_report import QAReport  # noqa: E402
from project_aurora.storage.csv_storage import CSVStorage  # noqa: E402
from project_aurora.storage.memory_manager import MemoryManager  # noqa: E402
from scripts.run_image_generation_demo import ensure_prompt_package  # noqa: E402


def ensure_generated_images(memory: MemoryManager) -> None:
    """Create local mock image-generation output for QA."""
    prompt_package_id = ensure_prompt_package(memory)
    engine = ImageGenerationEngine(
        memory=memory,
        output_dir=PROJECT_ROOT / "data" / "aurora" / "mock_generated_images",
    )
    engine.run(prompt_package_id=prompt_package_id, provider="mock")


def main() -> None:
    """Run image QA and print a console report."""
    memory = MemoryManager(
        storage=CSVStorage(base_path=PROJECT_ROOT / "data" / "aurora")
    )
    ensure_generated_images(memory)
    results = ImageQAEngine(memory=memory).run()
    print(QAReport(results=results).render())


if __name__ == "__main__":
    main()
