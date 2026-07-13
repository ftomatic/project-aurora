"""Export final commercial RainbowMilkStudio PNG files."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_PATH))

from project_aurora.image_generation.commercial_image_exporter import (  # noqa: E402
    CommercialImageExporter,
)


def main() -> None:
    """Export four final 3600x3600 commercial PNG images."""
    exporter = CommercialImageExporter(
        source_dir=PROJECT_ROOT / "data" / "aurora" / "generated_images",
        output_dir=PROJECT_ROOT / "data" / "aurora" / "final_product_images",
    )
    result = exporter.export()

    print("COMMERCIAL IMAGE EXPORT")
    print("")
    print("Images Exported")
    print(len(result.exported_files))
    print("")
    print("Status")
    print(result.status)
    if result.errors:
        print("")
        print("Errors")
        for error in result.errors:
            print(error)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
