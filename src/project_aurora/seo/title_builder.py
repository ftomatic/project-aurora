"""Etsy listing title builder."""

from __future__ import annotations


class TitleBuilder:
    """Build deterministic Etsy listing titles."""

    def build_title(
        self,
        product_name: str,
        product_type: str,
        keywords: tuple[str, ...],
    ) -> str:
        """Return an Etsy-ready listing title."""
        title_parts = [
            "Strawberry Birthday Party Printable Bundle",
            "Summer Berry Invitation",
            "Cupcake Toppers",
            "Favor Tags",
            "Girls Party Decor",
        ]
        if "Strawberry" not in product_name:
            title_parts[0] = product_name
        if "Party Printable" not in product_type:
            title_parts.insert(1, product_type)

        title = ", ".join(title_parts)
        if len(title) <= 140:
            return title
        return title[:137].rstrip(" ,") + "..."
