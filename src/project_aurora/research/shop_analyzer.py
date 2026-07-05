"""Analyze local RainbowMilkStudio shop product data."""

from __future__ import annotations

import csv
from collections import Counter
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ShopProduct:
    """A product currently represented in the shop sample data."""

    title: str
    category: str
    theme: str
    season: str
    price: float
    sales: int
    rating: float


@dataclass(frozen=True, slots=True)
class ShopSummary:
    """Summary of the current RainbowMilkStudio catalog."""

    product_count: int
    average_price: float
    average_rating: float
    total_sales: int
    top_categories: tuple[tuple[str, int], ...]
    top_themes: tuple[tuple[str, int], ...]
    covered_categories: frozenset[str]
    covered_themes: frozenset[str]
    covered_seasons: frozenset[str]


class ShopAnalyzer:
    """Load and summarize local shop product CSV data."""

    def load_products(self, csv_path: Path) -> tuple[ShopProduct, ...]:
        """Return shop products loaded from a CSV file."""
        with csv_path.open("r", encoding="utf-8", newline="") as csv_file:
            reader = csv.DictReader(csv_file)
            return tuple(self._row_to_product(row) for row in reader)

    def summarize(self, products: tuple[ShopProduct, ...]) -> ShopSummary:
        """Return a catalog summary for the provided products."""
        if not products:
            return ShopSummary(
                product_count=0,
                average_price=0.0,
                average_rating=0.0,
                total_sales=0,
                top_categories=(),
                top_themes=(),
                covered_categories=frozenset(),
                covered_themes=frozenset(),
                covered_seasons=frozenset(),
            )

        category_counts = Counter(product.category for product in products)
        theme_counts = Counter(product.theme for product in products)
        total_sales = sum(product.sales for product in products)
        average_price = sum(product.price for product in products) / len(products)
        average_rating = sum(product.rating for product in products) / len(products)

        return ShopSummary(
            product_count=len(products),
            average_price=round(average_price, 2),
            average_rating=round(average_rating, 2),
            total_sales=total_sales,
            top_categories=tuple(category_counts.most_common(5)),
            top_themes=tuple(theme_counts.most_common(5)),
            covered_categories=frozenset(category_counts),
            covered_themes=frozenset(theme_counts),
            covered_seasons=frozenset(product.season for product in products),
        )

    @staticmethod
    def _row_to_product(row: dict[str, str]) -> ShopProduct:
        return ShopProduct(
            title=row["title"].strip(),
            category=row["category"].strip(),
            theme=row["theme"].strip(),
            season=row["season"].strip(),
            price=float(row["price"]),
            sales=int(row["sales"]),
            rating=float(row["rating"]),
        )
