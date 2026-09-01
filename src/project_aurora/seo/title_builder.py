"""Etsy listing title builder."""

from __future__ import annotations


ETSY_TITLE_MAX_CHARACTERS = 140
ETSY_TITLE_MAX_WORDS = 15


class TitleBuilder:
    """Build concise, readable Etsy titles without keyword repetition."""

    def build_title(
        self,
        product_name: str,
        product_type: str,
        keywords: tuple[str, ...],
    ) -> str:
        """Return a natural Etsy title using distinct buyer-intent phrases."""
        product_lower = product_name.casefold()
        type_lower = product_type.casefold()
        candidates = self._descriptor_candidates(product_lower, type_lower)

        selected = [product_name.strip()]
        used_words = set(_meaningful_words(product_name))
        for phrase in candidates:
            phrase_words = _meaningful_words(phrase)
            if not phrase_words or phrase_words & used_words:
                continue
            proposed = ", ".join((*selected, phrase))
            if len(proposed) > ETSY_TITLE_MAX_CHARACTERS:
                continue
            if len(proposed.split()) > ETSY_TITLE_MAX_WORDS:
                continue
            selected.append(phrase)
            used_words.update(phrase_words)
            if len(selected) == 4:
                break
        return ", ".join(selected)

    @staticmethod
    def _descriptor_candidates(
        product_name: str,
        product_type: str,
    ) -> tuple[str, ...]:
        combined = f"{product_name} {product_type}"
        if "invitation" in combined or "wedding" in combined:
            return (
                "Floral Printable",
                "Editable Stationery",
                "Instant Digital Download",
            )
        if "birthday" in combined or "party" in product_type:
            return (
                "Party Bundle",
                "Kids Decor",
                "Instant Digital Download",
            )
        if "clipart" in combined:
            return (
                "Commercial Use PNG Bundle",
                "Printable Craft Graphics",
                "Instant Digital Download",
            )
        if "sticker" in combined:
            return (
                "Printable Planner Set",
                "Cricut Craft Graphics",
                "Instant Digital Download",
            )
        if "paper" in combined:
            return (
                "Printable Scrapbook Pack",
                "Seamless Craft Patterns",
                "Instant Digital Download",
            )
        if "wall art" in product_type or "print" in product_name or " art" in f" {product_name} ":
            return (
                "Printable Home Decor",
                "Gallery Design",
                "Instant Digital Download",
            )
        return (product_type.title(), "Instant Digital Download")


def _meaningful_words(value: str) -> frozenset[str]:
    normalized = value.casefold().replace("&", " and ").replace("-", " ")
    return frozenset(
        word.strip("'.,/()")
        for word in normalized.split()
        if len(word.strip("'.,/()")) > 2
        and word.strip("'.,/()") not in {"and", "the", "for", "with"}
    )
