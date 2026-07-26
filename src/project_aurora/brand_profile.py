"""RainbowMilkStudio brand profile learning and scoring."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
import json
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BRAND_PROFILE_PATH = PROJECT_ROOT / "data" / "aurora" / "brand_profile.json"

DEFAULT_PROFILE: dict[str, Any] = {
    "brand_name": "RainbowMilkStudio",
    "primary_brand": "Storybook watercolor woodland illustrations",
    "popular_animals": ["rabbit", "fox", "mouse", "bear", "hedgehog"],
    "popular_themes": [
        "tea party",
        "baking",
        "gardening",
        "reading",
        "baby animals",
        "nursery",
        "cottage",
        "cottagecore",
        "mushroom",
        "woodland homes",
    ],
    "popular_style": [
        "soft watercolor",
        "warm lighting",
        "vintage storybook",
        "whimsical",
        "gentle expressions",
        "cozy interiors",
        "natural backgrounds",
        "cottagecore",
    ],
    "popular_keywords": [
        "watercolor",
        "clipart",
        "woodland",
        "storybook",
        "cottagecore",
        "nursery",
        "animal",
        "botanical",
    ],
    "blocked_terms": [
        "teacher",
        "classroom",
        "planner",
        "digital paper",
        "wall art",
        "template",
        "typography",
        "alphabet",
        "worksheet",
    ],
    "minimum_brand_score": 45,
    "updated_at": "",
    "source": "DEFAULT_RAINBOWMILKSTUDIO_DNA",
}


@dataclass(frozen=True, slots=True)
class BrandScore:
    """Brand-fit score for one product idea."""

    score: int
    accepted: bool
    matched_terms: tuple[str, ...] = field(default_factory=tuple)
    blocked_terms: tuple[str, ...] = field(default_factory=tuple)
    reason: str = ""


def load_brand_profile(path: Path = DEFAULT_BRAND_PROFILE_PATH) -> dict[str, Any]:
    """Load the persisted brand profile, falling back to safe RainbowMilkStudio DNA."""
    if not path.exists():
        return dict(DEFAULT_PROFILE)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return dict(DEFAULT_PROFILE)
    if not isinstance(data, dict):
        return dict(DEFAULT_PROFILE)
    merged = dict(DEFAULT_PROFILE)
    merged.update(data)
    for key in ("popular_animals", "popular_themes", "popular_style", "popular_keywords", "blocked_terms"):
        merged[key] = _merge_terms(data.get(key), DEFAULT_PROFILE.get(key))
    return merged


def save_brand_profile(profile: dict[str, Any], path: Path = DEFAULT_BRAND_PROFILE_PATH) -> Path:
    """Persist a brand profile JSON file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(profile)
    payload["updated_at"] = datetime.now().isoformat()
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return path


def score_brand_fit(
    product_name: str,
    category: str = "",
    style: str = "",
    profile: dict[str, Any] | None = None,
) -> BrandScore:
    """Score whether a product belongs in RainbowMilkStudio."""
    profile = profile or load_brand_profile()
    text = f"{product_name} {category} {style}".casefold().replace("_", " ")
    blocked = tuple(term for term in _terms(profile, "blocked_terms") if term in text)
    if blocked:
        return BrandScore(
            score=0,
            accepted=False,
            blocked_terms=blocked,
            reason="Rejected because it contains terms outside RainbowMilkStudio.",
        )

    weighted_groups = (
        ("popular_animals", 25),
        ("popular_themes", 20),
        ("popular_style", 15),
        ("popular_keywords", 10),
    )
    matched: list[str] = []
    score = 0
    for key, weight in weighted_groups:
        hits = [term for term in _terms(profile, key) if term in text]
        if hits:
            matched.extend(hits)
            score += min(weight, 8 + len(hits) * 6)
    if "watercolor" in text and "clipart" in text:
        score += 20
    if "storybook" in text or "woodland" in text:
        score += 15
    score = min(score, 100)
    threshold = int(profile.get("minimum_brand_score") or 45)
    accepted = score >= threshold
    return BrandScore(
        score=score,
        accepted=accepted,
        matched_terms=tuple(dict.fromkeys(matched)),
        blocked_terms=blocked,
        reason=(
            "Fits RainbowMilkStudio brand DNA."
            if accepted
            else "Rejected because brand score is below threshold."
        ),
    )


def build_brand_profile_from_listings(listings: tuple[dict[str, Any], ...]) -> dict[str, Any]:
    """Infer a compact brand profile from Etsy listing records."""
    text_parts: list[str] = []
    titles: list[str] = []
    tags: list[str] = []
    for listing in listings:
        title = str(listing.get("title") or "")
        titles.append(title)
        text_parts.append(title)
        description = str(listing.get("description") or "")
        text_parts.append(description)
        raw_tags = listing.get("tags") or ()
        if isinstance(raw_tags, list | tuple):
            tags.extend(str(tag) for tag in raw_tags)
            text_parts.extend(str(tag) for tag in raw_tags)
    corpus = " ".join(text_parts).casefold()
    profile = dict(DEFAULT_PROFILE)
    profile.update(
        {
            "source": "ETSY_SHOP_ANALYSIS",
            "listing_count": len(listings),
            "sample_titles": titles[:20],
            "popular_animals": _rank_terms(corpus, DEFAULT_PROFILE["popular_animals"]),
            "popular_themes": _rank_terms(corpus, DEFAULT_PROFILE["popular_themes"]),
            "popular_style": _rank_terms(corpus, DEFAULT_PROFILE["popular_style"]),
            "popular_keywords": _top_keywords(tags, corpus),
        }
    )
    return profile


def _terms(profile: dict[str, Any], key: str) -> tuple[str, ...]:
    value = profile.get(key) or ()
    if not isinstance(value, list | tuple):
        return ()
    return tuple(str(item).casefold().strip() for item in value if str(item).strip())


def _merge_terms(primary: object, fallback: object) -> list[str]:
    terms: list[str] = []
    for value in (primary, fallback):
        if not isinstance(value, list | tuple):
            continue
        for item in value:
            text = str(item).strip()
            if text and text.casefold() not in {term.casefold() for term in terms}:
                terms.append(text)
    return terms


def _rank_terms(corpus: str, terms: list[str]) -> list[str]:
    ranked = sorted(
        ((term, corpus.count(term.casefold())) for term in terms),
        key=lambda item: (-item[1], item[0]),
    )
    found = [term for term, count in ranked if count > 0]
    return found or list(terms)


def _top_keywords(tags: list[str], corpus: str) -> list[str]:
    counter: Counter[str] = Counter()
    for tag in tags:
        cleaned = tag.casefold().strip()
        if cleaned:
            counter[cleaned] += 3
    for word in ("watercolor", "clipart", "woodland", "storybook", "cottagecore", "nursery", "animal", "botanical"):
        if word in corpus:
            counter[word] += corpus.count(word)
    return [term for term, _count in counter.most_common(20)] or list(DEFAULT_PROFILE["popular_keywords"])
