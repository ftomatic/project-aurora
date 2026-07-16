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
        product_lower = product_name.casefold()
        type_lower = product_type.casefold()
        title_parts = [product_name]
        if "invitation" in product_lower and "birthday" not in product_lower:
            title_parts.extend(("Floral Printable Invitation", "Digital Wedding Invite"))
        elif "birthday" in product_lower or "party" in product_lower or "party" in type_lower:
            title_parts.extend(("Party Printable Bundle", "Digital Party Download"))
            if "strawberry" in product_lower:
                title_parts.append("Berry Birthday Printable")
        elif "clipart" in product_lower or "clipart" in type_lower:
            title_parts.extend(("PNG Clipart Bundle", "Commercial Use Graphics"))
        elif "sticker" in product_lower or "sticker" in type_lower:
            title_parts.extend(("Printable Planner Stickers", "Digital Sticker Sheet"))
        elif "paper" in product_lower or "digital paper" in type_lower:
            title_parts.extend(("Digital Paper Pack", "Printable Scrapbook Paper"))
        elif (
            "wall art" in type_lower
            or "print" in product_lower
            or " art" in f" {product_lower} "
        ):
            title_parts.extend(("Printable Wall Art", "Digital Art Download"))
        else:
            title_parts.append(product_type)

        for keyword in keywords:
            if len(title_parts) >= 4:
                break
            legacy_party_terms = {
                "cupcake toppers",
                "favor tags",
                "girls party decor",
                "summer berry invitation",
            }
            if (
                len(keyword) <= 32
                and keyword.casefold() not in product_lower
                and keyword.casefold() not in legacy_party_terms
            ):
                title_parts.append(keyword.title())

        title = ", ".join(title_parts)
        if len(title) <= 140:
            return title
        return title[:137].rstrip(" ,") + "..."
