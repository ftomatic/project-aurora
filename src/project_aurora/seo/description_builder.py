"""Product description builder for Aurora SEO."""

from __future__ import annotations


RAINBOW_MILK_STUDIO_DESCRIPTION = """YOUR PURCHASE INCLUDES:

4 high-quality 300 DPI PNG files
FREE COMMERCIAL LICENSE

EACH IMAGE SIZE:
12" × 12"
300 DPI
3600 × 3600 pixels

Use these handmade-style images to create mouse mats, mugs, T-shirts, cushions, cards, scrapbook pages, crafts, and mixed-media projects.

Download and start creating!

After purchase, access your files by visiting:
Etsy Profile > Purchases and Reviews

PLEASE NOTE:

This is an instant digital download. No physical product will be shipped.

Colors may differ slightly because of variations in monitor and printer settings.

Please email me with any questions or if you need a different size."""


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
        return RAINBOW_MILK_STUDIO_DESCRIPTION
