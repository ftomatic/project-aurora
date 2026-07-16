"""Product description builder for Aurora SEO."""

from __future__ import annotations


PURCHASE_SECTION = """YOUR PURCHASE INCLUDES:

4 high-quality 300 DPI PNG files
FREE COMMERCIAL LICENSE

EACH IMAGE SIZE:
12" × 12"
300 DPI
3600 × 3600 pixels"""

DOWNLOAD_DISCLAIMER_SECTION = """After purchase, access your files by visiting:
Etsy Profile > Purchases and Reviews

PLEASE NOTE:

This is an instant digital download. No physical product will be shipped.

Colors may differ slightly because of variations in monitor and printer settings.

Please email me with any questions or if you need a different size."""

RAINBOW_MILK_STUDIO_DESCRIPTION = f"""{PURCHASE_SECTION}

Use these handmade-style images to create mouse mats, mugs, T-shirts, cushions, cards, scrapbook pages, crafts, and mixed-media projects.

Download and start creating!

{DOWNLOAD_DISCLAIMER_SECTION}"""


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
        intro = self._intro(product_name, product_type, target_buyer, product_positioning, tags)
        perfect_for = self._perfect_for(product_name, product_type)
        return f"""{intro}

Perfect for:
{perfect_for}

{PURCHASE_SECTION}

{DOWNLOAD_DISCLAIMER_SECTION}"""

    @staticmethod
    def _intro(
        product_name: str,
        product_type: str,
        target_buyer: str,
        product_positioning: str,
        tags: tuple[str, ...],
    ) -> str:
        primary_keywords = ", ".join(tags[:3])
        return (
            f"{product_name} is a digital {product_type.lower()} designed for "
            f"{target_buyer}. This SEO-ready printable download works beautifully "
            f"for shoppers searching Etsy for {primary_keywords}.\n\n"
            f"The collection has a {product_positioning.lower()} Handmade-style PNG "
            "art makes it easy to create coordinated products, gifts, and craft projects."
        )

    @staticmethod
    def _perfect_for(product_name: str, product_type: str) -> str:
        lowered = f"{product_name} {product_type}".casefold()
        if "invitation" in lowered or "wedding" in lowered:
            uses = (
                "wedding invitations",
                "bridal shower stationery",
                "floral RSVP cards",
                "save-the-date graphics",
                "wedding signs",
                "thank-you cards",
            )
        elif "sticker" in lowered or "planner" in lowered:
            uses = (
                "planner stickers",
                "journal pages",
                "calendar layouts",
                "habit trackers",
                "scrapbook accents",
                "digital planning projects",
            )
        elif "nursery" in lowered or "wall art" in lowered or "print" in lowered:
            uses = (
                "nursery wall art",
                "kids room decor",
                "gallery wall prints",
                "baby shower gifts",
                "framed printable art",
                "seasonal home decor",
            )
        elif "clipart" in lowered or "animal" in lowered or "woodland" in lowered:
            uses = (
                "commercial clipart projects",
                "mugs and tumblers",
                "T-shirt graphics",
                "stickers and labels",
                "scrapbook pages",
                "craft market products",
            )
        elif "paper" in lowered:
            uses = (
                "digital scrapbook paper",
                "junk journal pages",
                "card making",
                "printable backgrounds",
                "craft paper packs",
                "mixed-media projects",
            )
        elif "birthday" in lowered or "party" in lowered:
            uses = (
                "birthday party invitations",
                "party signs",
                "cupcake toppers",
                "favor tags",
                "thank-you cards",
                "party craft projects",
            )
        else:
            uses = (
                "mugs and tumblers",
                "T-shirt graphics",
                "cards and tags",
                "scrapbook pages",
                "craft projects",
                "small business product designs",
            )
        return "\n".join(f"- {use}" for use in uses)
