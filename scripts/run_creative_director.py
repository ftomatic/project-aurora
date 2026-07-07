"""Run Aurora Creative Director demo."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_PATH))

from project_aurora.config.profile_loader import (  # noqa: E402
    ProjectProfileLoader,
)
from project_aurora.creative.creative_director import (  # noqa: E402
    CreativeDirector,
)


def main() -> None:
    """Plan a sample Summer Strawberry Birthday collection."""
    profile = ProjectProfileLoader().load(
        PROJECT_ROOT / "config" / "projects" / "rainbow_milk_studio.yaml"
    )
    research = {
        "production_selection": {
            "best_product": {
                "name": "Strawberry Birthday Party Printable",
                "theme": "Strawberry Birthday",
                "season": "Summer",
            }
        }
    }
    strategy = {
        "selected_product": "Strawberry Birthday Party Printable",
        "product_type": "Party Printable Bundle",
        "collection_name": "Summer Strawberry Birthday Collection",
        "asset_count": 36,
        "target_buyer": "Parents planning girls' summer birthday parties",
        "positioning": "Cute cottagecore strawberry printable party bundle",
        "production_priority": "High",
    }
    plan = CreativeDirector().plan_collection(
        research=research,
        strategy=strategy,
        project_profile=profile,
    )

    print("CREATIVE DIRECTOR")
    print("")
    print("Collection")
    print(plan.collection_name)
    print("")
    print("Theme")
    print(plan.theme)
    print("")
    print("Products Planned")
    print(len(plan.recommended_products))
    print("")
    print("Master Assets")
    print(len(plan.master_assets))
    print("")
    print("Estimated Revenue")
    print(f"${plan.estimated_revenue:.0f}")
    print("")
    print("Generation Cost")
    print(f"${plan.estimated_generation_cost:.2f}")
    print("")
    print("Status")
    print(plan.status)


if __name__ == "__main__":
    main()
