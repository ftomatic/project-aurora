"""Build RainbowMilkStudio brand_profile.json from the configured Etsy shop."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_PATH))

from project_aurora.brand_profile import (  # noqa: E402
    DEFAULT_BRAND_PROFILE_PATH,
    build_brand_profile_from_listings,
    save_brand_profile,
)
from project_aurora.config.local_env import load_local_env  # noqa: E402
from project_aurora.integrations.etsy.etsy_client import EtsyClient  # noqa: E402
from project_aurora.integrations.etsy.etsy_config import EtsyConfig  # noqa: E402


def main() -> None:
    """Read RainbowMilkStudio Etsy data and save brand_profile.json."""
    load_local_env(PROJECT_ROOT / "config" / "aurora.local.env")
    config = EtsyConfig.from_environment(PROJECT_ROOT / "config" / "etsy.yaml")
    if config.is_mock_mode:
        raise SystemExit("AURORA_ETSY_MODE must be live to build the shop brand profile.")
    missing = config.validate_for_api(is_digital=True)
    if missing:
        raise SystemExit("Missing Etsy configuration: " + ", ".join(missing))

    client = EtsyClient(config)
    active = client.list_shop_active_listings()
    try:
        sold = client.list_shop_sold_listings()
    except Exception as error:
        print("Sold Listings")
        print(f"Unavailable: {error}")
        sold = ()
    listings = active + sold
    if not listings:
        raise SystemExit("No Etsy listings were returned for this shop.")

    profile = build_brand_profile_from_listings(listings)
    save_brand_profile(profile, DEFAULT_BRAND_PROFILE_PATH)

    print("BRAND PROFILE")
    print("")
    print("Shop")
    print(profile["brand_name"])
    print("")
    print("Listings Analyzed")
    print(len(listings))
    print("")
    print("Primary Brand")
    print(profile["primary_brand"])
    print("")
    print("Popular Animals")
    for animal in profile["popular_animals"]:
        print(animal.title())
    print("")
    print("Popular Themes")
    for theme in profile["popular_themes"]:
        print(theme.title())
    print("")
    print("Saved")
    print(DEFAULT_BRAND_PROFILE_PATH)


if __name__ == "__main__":
    main()
