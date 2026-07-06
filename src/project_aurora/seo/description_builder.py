"""Product description builder for Aurora SEO."""

from __future__ import annotations


class DescriptionBuilder:
    """Build deterministic Etsy product descriptions."""

    def build_description(
        self,
        product_name: str,
        product_type: str,
        target_buyer: str,
        buyer_use_case: str,
        product_positioning: str,
        tags: tuple[str, ...],
    ) -> str:
        """Return a buyer-focused Etsy listing description."""
        return "\n\n".join(
            (
                (
                    f"Bring a sweet summer berry moment to the party with the "
                    f"{product_name}."
                ),
                (
                    f"This {product_type.lower()} is designed for "
                    f"{target_buyer.lower()} and includes coordinated printable "
                    "party pieces that feel cheerful, polished, and easy to use."
                ),
                f"Best for: {buyer_use_case}.",
                f"Positioning: {product_positioning}.",
                (
                    "SEO focus: "
                    f"{', '.join(tags[:6])}. Digital download only; no physical "
                    "item will be shipped."
                ),
            )
        )
