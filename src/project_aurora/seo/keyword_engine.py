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
        name = product_name.casefold()
        product_type_lower = product_type.casefold()
        tokens = tuple(
            token
            for token in name.replace("&", " ").replace("-", " ").split()
            if len(token) > 2
        )
        phrases = self._product_phrases(tokens, product_type_lower)
        type_phrases = self._type_phrases(product_type_lower)
        audience_phrases = self._audience_phrases(target_buyer)
        return self._dedupe((*phrases, *type_phrases, *audience_phrases))

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

    def _product_phrases(
        self,
        tokens: tuple[str, ...],
        product_type: str,
    ) -> tuple[str, ...]:
        phrases: list[str] = []
        for token in tokens:
            phrases.append(token)
        if "strawberry" in tokens and "birthday" in tokens:
            phrases.append("strawberry party")
        for left, right in zip(tokens, tokens[1:]):
            phrases.append(f"{left} {right}")
        if tokens:
            phrases.append(f"{tokens[0]} printable")
            phrases.append(f"{tokens[0]} clipart")
            phrases.append(f"{tokens[0]} art")
        if len(tokens) >= 2:
            phrases.append(f"{tokens[0]} {tokens[-1]}")
        if "invitation" in product_type:
            phrases.append("party invitation")
        return tuple(phrases)

    @staticmethod
    def _type_phrases(product_type: str) -> tuple[str, ...]:
        if "party" in product_type:
            return (
                "party printable",
                "printable bundle",
                "party decor",
                "party download",
                "favor tags",
                "cupcake toppers",
                "thank you cards",
            )
        if "wall art" in product_type:
            return (
                "wall art",
                "printable art",
                "digital print",
                "home decor",
                "instant download",
                "gallery wall",
            )
        if "digital paper" in product_type:
            return (
                "digital paper",
                "scrapbook paper",
                "seamless pattern",
                "paper pack",
                "craft paper",
                "digital download",
            )
        if "sticker" in product_type:
            return (
                "planner stickers",
                "sticker sheet",
                "printable sticker",
                "planner icons",
                "digital stickers",
                "label stickers",
            )
        if "journal" in product_type:
            return (
                "junk journal",
                "journal kit",
                "printable journal",
                "scrapbook kit",
                "vintage paper",
            )
        return (
            "clipart bundle",
            "commercial use",
            "png clipart",
            "digital clipart",
            "printable graphics",
            "instant download",
        )

    @staticmethod
    def _audience_phrases(target_buyer: str) -> tuple[str, ...]:
        buyer = target_buyer.casefold()
        phrases: list[str] = []
        if "parent" in buyer:
            phrases.extend(("kids decor", "children party"))
        if "teacher" in buyer:
            phrases.extend(("teacher printable", "classroom decor"))
        if "crafter" in buyer:
            phrases.extend(("craft supply", "craft download"))
        if "bride" in buyer:
            phrases.extend(("bridal printable", "wedding decor"))
        phrases.append("etsy download")
        return tuple(phrases)

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
