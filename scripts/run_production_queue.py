"""Generate a sample Aurora content production queue."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_PATH))

from project_aurora.production.production_queue import (  # noqa: E402
    ProductionQueue,
)
from project_aurora.strategy.product_plan import (  # noqa: E402
    BundleItem,
    ProductPlan,
)


def make_sample_strategy() -> ProductPlan:
    """Return local mock product strategy data for queue generation."""
    return ProductPlan(
        selected_product="Strawberry Birthday Party Printable",
        product_type="Party Printable Bundle",
        collection_name="Summer Strawberry Birthday Collection",
        asset_count=36,
        bundle_structure=(
            BundleItem(quantity=8, name="invitations"),
            BundleItem(quantity=8, name="cupcake toppers"),
            BundleItem(quantity=8, name="favor tags"),
            BundleItem(quantity=6, name="thank-you cards"),
            BundleItem(quantity=6, name="digital papers"),
        ),
        target_buyer="Parents planning girls' summer birthday parties",
        positioning="Cute cottagecore strawberry printable party bundle",
        expansion_ideas=(
            "Matching strawberry thank-you set",
            "Strawberry first birthday printable mini bundle",
        ),
        estimated_commercial_potential="High",
        production_priority="High",
        ceo_summary=(
            "Today the studio should produce Strawberry Birthday Party "
            "Printable as a Party Printable Bundle."
        ),
    )


def main() -> None:
    """Create and save sample production queue items."""
    queue = ProductionQueue(
        queue_dir=PROJECT_ROOT / "data" / "aurora" / "production_queue"
    )
    items = queue.create_queue_from_strategy(make_sample_strategy())
    save_result = queue.save_queue(items)
    pending_items = queue.list_pending(items)

    print("AURORA PRODUCTION QUEUE")
    print("")
    print(f"Queue File\n{save_result.path}")
    print("")
    print(f"Items Created\n{save_result.item_count}")
    print("")
    print(f"Pending Items\n{len(pending_items)}")
    print("")
    print("Platforms")
    for platform in sorted({item.platform for item in items}):
        print(f"- {platform}")


if __name__ == "__main__":
    main()
