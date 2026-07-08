"""Run Aurora Style Intelligence Engine demo."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_PATH))

from project_aurora.config.profile_loader import (  # noqa: E402
    ProjectProfileLoader,
)
from project_aurora.creative.collection_plan import CollectionPlan  # noqa: E402
from project_aurora.storage.csv_storage import CSVStorage  # noqa: E402
from project_aurora.storage.memory_manager import MemoryManager  # noqa: E402
from project_aurora.style_intelligence.style_engine import (  # noqa: E402
    StyleEngine,
)


def main() -> None:
    """Build style profiles and select the best style for the sample collection."""
    profile = ProjectProfileLoader().load(
        PROJECT_ROOT / "config" / "projects" / "rainbow_milk_studio.yaml"
    )
    collection_plan = CollectionPlan(
        collection_name="Strawberry Birthday",
        theme="Storybook Watercolor",
        season="Summer",
        target_customer="Parents planning girls' summer birthday parties",
        art_style="Storybook Watercolor Cottagecore",
        primary_palette=("berry red", "blush pink", "cream"),
        secondary_palette=("sage", "warm yellow"),
        recommended_products=("Invitation", "Cupcake Toppers", "Favor Tags"),
        master_assets=("Main Strawberry Girl", "Berry Pattern"),
        shared_elements=("strawberries", "flowers", "ribbons"),
        cross_sell_products=("Matching Clipart",),
        upsell_products=("Deluxe Party Bundle",),
        estimated_revenue=120.0,
        estimated_generation_cost=0.62,
        priority="High",
    )
    trend_research = {
        "theme": "strawberry birthday storybook watercolor summer party",
        "audience": "parents digital printable buyers",
        "product": "party printable",
    }
    result = StyleEngine(
        memory=MemoryManager(
            storage=CSVStorage(base_path=PROJECT_ROOT / "data" / "aurora")
        )
    ).run(
        project_profile=profile,
        trend_research=trend_research,
        collection_plan=collection_plan,
    )

    print("STYLE INTELLIGENCE")
    print("")
    print("Styles Available")
    print(result.styles_available)
    print("")
    print("Selected Style")
    print(result.selection.style_profile.style_name)
    print("")
    print("Reason")
    print(result.selection.reason)
    print("")
    print("Confidence")
    print(f"{result.selection.confidence:.0%}")
    print("")
    print("Status")
    print(result.status)


if __name__ == "__main__":
    main()
