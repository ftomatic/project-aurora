"""Display the active Aurora project profile."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_PATH))

from project_aurora.config.profile_loader import (  # noqa: E402
    ProjectProfileLoader,
)


def main() -> None:
    """Load and print the RainbowMilkStudio project profile."""
    profile = ProjectProfileLoader().load(
        PROJECT_ROOT / "config" / "projects" / "rainbow_milk_studio.yaml"
    )

    print("PROJECT PROFILE")
    print("")
    print("Project:")
    print(profile.brand_name)
    print("")
    print("Marketplace:")
    print(profile.marketplace)
    print("")
    print("Shop:")
    print(profile.shop_url)
    print("")
    print("Default AI Provider:")
    print(profile.default_ai_provider)
    print("")
    print("Default Price:")
    print(f"${profile.default_price:.2f}")
    print("")
    print("Retention Policy:")
    for line in profile.retention_summary()[:3]:
        print(line)


if __name__ == "__main__":
    main()
