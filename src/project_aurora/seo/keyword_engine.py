"""Deterministic keyword generation for Aurora SEO."""

from __future__ import annotations


class KeywordEngine:
    """Generate Etsy-friendly keyword sets and tags."""

    def build_keywords(
        self,
        product_name: str,
        product_type: str,
        target_buyer: str,
    ) -> tuple[str, ...]:
        """Return a deduplicated keyword set for the listing."""
        base_keywords = (
            "strawberry party",
            "birthday printable",
            "berry birthday",
            "girls party decor",
            "summer party",
            "cupcake toppers",
            "favor tags",
            "party invitation",
            "printable bundle",
            "cottagecore party",
            "kids birthday",
            "strawberry decor",
            "party download",
            "thank you cards",
            "digital papers",
            "party printable bundle",
        )
        contextual = tuple(
            token
            for token in (
                product_name.lower(),
                product_type.lower(),
                target_buyer.lower(),
            )
            if token
        )
        return self._dedupe((*base_keywords, *contextual))

    def build_tags(
        self,
        product_name: str,
        product_type: str,
        target_buyer: str,
    ) -> tuple[str, ...]:
        """Return exactly 13 Etsy tags, each 20 characters or fewer."""
        keywords = self.build_keywords(product_name, product_type, target_buyer)
        tags = tuple(keyword for keyword in keywords if len(keyword) <= 20)
        if len(tags) < 13:
            raise ValueError("Not enough Etsy-safe tags could be generated.")
        return tags[:13]

    @staticmethod
    def _dedupe(values: tuple[str, ...]) -> tuple[str, ...]:
        seen: set[str] = set()
        deduped: list[str] = []
        for value in values:
            normalized = " ".join(value.strip().split())
            if normalized and normalized not in seen:
                seen.add(normalized)
                deduped.append(normalized)
        return tuple(deduped)
