"""Review Muse style selection for today's products."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_PATH))

from project_aurora.muse.muse_engine import MuseEngine  # noqa: E402
from project_aurora.storage.csv_storage import CSVStorage  # noqa: E402
from project_aurora.storage.memory_manager import MemoryManager  # noqa: E402


TODAYS_PRODUCTS = (
    ("Wedding Invitation", "brides", "Wedding Season", "Medium", "party printable"),
    ("Teacher Stickers", "teachers", "Back to School", "Low", "sticker sheet"),
    ("Kitchen Art", "home decor buyers", "Evergreen", "Medium", "wall art"),
    ("Dark Academia", "students and readers", "Autumn", "High", "wall art"),
    ("Coastal Digital Paper", "scrapbookers", "Summer", "Medium", "digital paper"),
    ("Autumn Mushroom", "crafters", "Autumn", "Low", "clipart"),
)


def main() -> None:
    """Print style review for sample daily products."""
    memory = MemoryManager(CSVStorage(base_path=PROJECT_ROOT / "data" / "aurora"))
    engine = MuseEngine(memory=memory)
    chosen: list[str] = []
    print("STYLE SELECTION REVIEW")
    print("")
    print("Today's Products")
    for product, audience, season, competition, product_type in TODAYS_PRODUCTS:
        direction = engine.select_style(
            product=product,
            audience=audience,
            season=season,
            competition=competition,
            current_portfolio=tuple(chosen),
            product_type=product_type,
        )
        chosen.append(direction.recommended_style)
        print(product)
        print("Chosen Style")
        print(direction.recommended_style)
        print("Why Chosen")
        print(direction.reason)
        print("Alternative Styles")
        for style, score in direction.alternative_styles:
            print(f"{style}: {score}")
        print("Portfolio Diversity")
        print(direction.portfolio_diversity)
        print("")


if __name__ == "__main__":
    main()
