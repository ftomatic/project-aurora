"""Inspect generated Aurora PNG files for blank or invalid images."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_PATH))

from project_aurora.image_generation.image_inspector import (  # noqa: E402
    inspect_png_directory,
)


def main() -> None:
    """Print diagnostics for generated Aurora PNG images."""
    image_dir = (
        Path(sys.argv[1])
        if len(sys.argv) > 1
        else PROJECT_ROOT / "data" / "aurora" / "generated_images"
    )
    if not image_dir.is_absolute():
        image_dir = PROJECT_ROOT / image_dir
    inspections = inspect_png_directory(image_dir)

    print("GENERATED IMAGE INSPECTION")
    print("")
    print("Directory")
    print(image_dir)
    print("")
    print("Images Found")
    print(len(inspections))

    for inspection in inspections:
        dimensions = (
            ""
            if inspection.dimensions is None
            else f"{inspection.dimensions[0]}x{inspection.dimensions[1]}"
        )
        print("")
        print("Filename")
        print(inspection.filename)
        print("File Size")
        print(inspection.file_size)
        print("Dimensions")
        print(dimensions)
        print("Image Mode")
        print(inspection.image_mode or "")
        print("Alpha Minimum")
        print("" if inspection.alpha_minimum is None else inspection.alpha_minimum)
        print("Alpha Maximum")
        print("" if inspection.alpha_maximum is None else inspection.alpha_maximum)
        print("Visible Pixels")
        print(inspection.visible_pixels)
        print("All Visible Pixels White")
        print(inspection.all_visible_pixels_white)
        print("Classification")
        print(inspection.classification)


if __name__ == "__main__":
    main()
