"""Run Aurora's local SEO and keyword demo."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_PATH))

from project_aurora.seo.seo_engine import SEOEngine  # noqa: E402
from project_aurora.storage.csv_storage import CSVStorage  # noqa: E402
from project_aurora.storage.memory_manager import MemoryManager  # noqa: E402


SAMPLE_PRODUCT_DATA = {
    "product_name": "Summer Strawberry Birthday Collection",
    "product_type": "Party Printable Bundle",
    "target_buyer": "Parents planning girls' summer birthday parties",
}


def main() -> None:
    """Generate and save a sample Etsy SEO package."""
    memory = MemoryManager(
        storage=CSVStorage(base_path=PROJECT_ROOT / "data" / "aurora")
    )
    package = SEOEngine(memory=memory).run(SAMPLE_PRODUCT_DATA)

    print("SEO ENGINE")
    print("")
    print("Product:")
    print(package.product_name)
    print("")
    print("Title:")
    print(package.title)
    print("")
    print("Tags:")
    for tag in package.tags:
        print(tag)
    print("")
    print("SEO Score:")
    print(package.seo_score)
    print("")
    print("Status:")
    print(package.status)


if __name__ == "__main__":
    main()
