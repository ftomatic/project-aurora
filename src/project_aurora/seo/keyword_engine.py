"""Deterministic keyword generation for Aurora SEO."""

from __future__ import annotations

import re


ETSY_TAG_COUNT = 13
ETSY_TAG_MAX_LENGTH = 20


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
        style: str = "",
    ) -> tuple[str, ...]:
        """Return exactly 13 Etsy tags, each 20 characters or fewer."""
        keywords = self.build_keywords(product_name, product_type, target_buyer)
        candidates = (
            *keywords,
            *self._fallback_tags(
                product_name=product_name,
                product_type=product_type,
                target_buyer=target_buyer,
                style=style,
            ),
        )
        tags = self._etsy_safe_tags(candidates)
        if len(tags) < ETSY_TAG_COUNT:
            raise ValueError("Not enough Etsy-safe tags could be generated.")
        return tags[:ETSY_TAG_COUNT]

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
        if "illustration collection" in product_type or "digital illustration" in product_type:
            return (
                "png illustrations",
                "digital art",
                "printable art",
                "art download",
                "commercial art",
                "craft graphics",
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

    def _fallback_tags(
        self,
        *,
        product_name: str,
        product_type: str,
        target_buyer: str,
        style: str,
    ) -> tuple[str, ...]:
        title_tokens = self._tokens(product_name)
        type_tokens = self._tokens(product_type)
        style_tokens = self._tokens(style)
        subject = title_tokens[0] if title_tokens else ""
        category = " ".join(type_tokens[:2])
        style_subject = (
            f"{style_tokens[0]} {subject}"
            if style_tokens and subject
            else ""
        )
        phrases: list[str] = [
            f"{subject} graphics",
            f"{subject} download",
            f"{subject} printable",
            f"{subject} design",
            f"{category} set",
            f"{category} art",
            f"{category} download",
            style_subject,
            "digital download",
            "printable design",
            "commercial art",
            "craft graphics",
        ]
        lowered = f"{product_name} {product_type} {target_buyer}".casefold()
        if "teacher" in lowered:
            phrases.extend(
                (
                    "teacher graphics",
                    "classroom clipart",
                    "school clipart",
                    "teacher art",
                    "classroom art",
                )
            )
        if "clipart" in lowered:
            phrases.extend(
                (
                    "clipart set",
                    "png graphics",
                    "digital graphics",
                    "printable clipart",
                )
            )
        if "wall art" in lowered or "poster" in lowered:
            phrases.extend(("poster print", "wall decor", "art download"))
        return tuple(phrases)

    @staticmethod
    def _tokens(value: str) -> tuple[str, ...]:
        return tuple(
            token
            for token in re.sub(r"[^a-z0-9\s]+", " ", value.casefold()).split()
            if len(token) > 2
        )

    @classmethod
    def _etsy_safe_tags(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        seen: set[str] = set()
        tags: list[str] = []
        for value in values:
            tag = re.sub(r"[^a-z0-9\s]+", " ", value.casefold())
            tag = " ".join(tag.split())
            if (
                not tag
                or len(tag) > ETSY_TAG_MAX_LENGTH
                or tag in seen
            ):
                continue
            seen.add(tag)
            tags.append(tag)
        return tuple(tags)

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
