"""Run Prompt Factory 2.0 composer demo."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_PATH))

from project_aurora.prompt_factory.prompt_composer import (  # noqa: E402
    PromptComposer,
)
from project_aurora.storage.csv_storage import CSVStorage  # noqa: E402
from project_aurora.storage.memory_manager import MemoryManager  # noqa: E402


def main() -> None:
    """Compose and save a sample Prompt Factory 2.0 recipe."""
    memory = MemoryManager(
        storage=CSVStorage(base_path=PROJECT_ROOT / "data" / "aurora")
    )
    recipe = PromptComposer(memory=memory).compose(
        subject="Summer strawberry birthday party printable collection",
        character="Main Strawberry Girl with berry dress and ribbon details",
        style_name="Storybook Watercolor",
        palette_name="Strawberry Summer",
        composition_name="Centered",
    )

    print("PROMPT FACTORY 2.0")
    print("")
    print("Recipe")
    print(recipe.style)
    print("")
    print("Palette")
    print(recipe.color_palette)
    print("")
    print("Composition")
    print(recipe.composition)
    print("")
    print("Prompt")
    print("Generated")
    print("")
    print("Status")
    print("SUCCESS")


if __name__ == "__main__":
    main()
