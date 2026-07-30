"""Canonical product art direction shared by related image prompts."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import re
from typing import Any


@dataclass(frozen=True, slots=True)
class ArtDirectionPackage:
    """One visual specification for a product's clipart and scene assets."""

    subject: str
    animal_species: tuple[str, ...]
    character_type: str
    clothing: tuple[str, ...]
    activity: str
    props: tuple[str, ...]
    palette: tuple[str, ...]
    painting_medium: str
    line_quality: str
    facial_style: str
    proportions: str
    lighting: str
    season: str
    environment: str
    mood: str
    composition_vocabulary: tuple[str, ...]

    @property
    def fingerprint(self) -> str:
        """Stable fingerprint for stale-asset invalidation."""
        payload = json.dumps(self.to_dict(include_fingerprint=False), sort_keys=True)
        return sha256(payload.encode("utf-8")).hexdigest()[:16]

    def to_dict(self, *, include_fingerprint: bool = True) -> dict[str, Any]:
        """Return JSON-safe package data."""
        data: dict[str, Any] = {
            "subject": self.subject,
            "animal_species": list(self.animal_species),
            "character_type": self.character_type,
            "clothing": list(self.clothing),
            "activity": self.activity,
            "props": list(self.props),
            "palette": list(self.palette),
            "painting_medium": self.painting_medium,
            "line_quality": self.line_quality,
            "facial_style": self.facial_style,
            "proportions": self.proportions,
            "lighting": self.lighting,
            "season": self.season,
            "environment": self.environment,
            "mood": self.mood,
            "composition_vocabulary": list(self.composition_vocabulary),
        }
        if include_fingerprint:
            data["fingerprint"] = self.fingerprint
        return data

    def descriptor(self) -> str:
        """Concise prompt descriptor shared by scene and clipart prompts."""
        return (
            f"Subject: {self.subject}. "
            f"Animal species: {', '.join(self.animal_species)}. "
            f"Character type: {self.character_type}. "
            f"Clothing: {', '.join(self.clothing)}. "
            f"Activity: {self.activity}. "
            f"Props: {', '.join(self.props)}. "
            f"Palette: {', '.join(self.palette)}. "
            f"Painting medium: {self.painting_medium}. "
            f"Line quality: {self.line_quality}. "
            f"Facial style: {self.facial_style}. "
            f"Proportions: {self.proportions}. "
            f"Lighting: {self.lighting}. "
            f"Season: {self.season}. "
            f"Environment: {self.environment}. "
            f"Mood: {self.mood}. "
            f"Composition vocabulary: {', '.join(self.composition_vocabulary)}."
        )


def build_art_direction_package(
    *,
    product_name: str,
    product_category: str,
    style: str,
    season: str,
    palette: str,
    mood: str,
) -> ArtDirectionPackage:
    """Create deterministic brand-aligned art direction from product context."""
    text = f"{product_name} {product_category} {style}".casefold()
    species = _species_from_text(text)
    activity = _activity_from_text(text)
    props = _props_from_text(text)
    resolved_palette = _palette_from_text(text, palette)
    clothing = _clothing_from_text(text)
    environment = _environment_from_text(text)
    return ArtDirectionPackage(
        subject=product_name,
        animal_species=species,
        character_type=_character_type_from_text(text),
        clothing=clothing,
        activity=activity,
        props=props,
        palette=resolved_palette,
        painting_medium="soft watercolor and gentle gouache",
        line_quality="delicate vintage storybook linework",
        facial_style="gentle expressive faces with warm friendly eyes",
        proportions="rounded vintage children's book proportions, full bodies visible",
        lighting="warm soft natural lighting",
        season=season or "evergreen",
        environment=environment,
        mood=mood or "cozy whimsical cottagecore",
        composition_vocabulary=(
            "full body visible",
            "10 percent safe padding",
            "cohesive commercial bundle",
            "matching characters and props",
        ),
    )


def art_direction_package_from_dict(data: dict[str, Any]) -> ArtDirectionPackage:
    """Rehydrate an art direction package from saved prompt data."""
    return ArtDirectionPackage(
        subject=str(data.get("subject") or ""),
        animal_species=tuple(str(item) for item in data.get("animal_species", ())),
        character_type=str(data.get("character_type") or ""),
        clothing=tuple(str(item) for item in data.get("clothing", ())),
        activity=str(data.get("activity") or ""),
        props=tuple(str(item) for item in data.get("props", ())),
        palette=tuple(str(item) for item in data.get("palette", ())),
        painting_medium=str(data.get("painting_medium") or ""),
        line_quality=str(data.get("line_quality") or ""),
        facial_style=str(data.get("facial_style") or ""),
        proportions=str(data.get("proportions") or ""),
        lighting=str(data.get("lighting") or ""),
        season=str(data.get("season") or ""),
        environment=str(data.get("environment") or ""),
        mood=str(data.get("mood") or ""),
        composition_vocabulary=tuple(
            str(item) for item in data.get("composition_vocabulary", ())
        ),
    )


def _species_from_text(text: str) -> tuple[str, ...]:
    candidates = (
        "rabbit",
        "bunny",
        "fox",
        "mouse",
        "bear",
        "hedgehog",
        "deer",
        "squirrel",
    )
    found = tuple(candidate for candidate in candidates if candidate in text)
    if "bunny" in found and "rabbit" not in found:
        found = ("rabbit", *tuple(item for item in found if item != "bunny"))
    return found or ("woodland animal",)


def _activity_from_text(text: str) -> str:
    activity_terms = {
        "tea": "sharing a cozy tea party",
        "party": "celebrating together",
        "bak": "baking sweet treats",
        "garden": "gardening among flowers",
        "reading": "reading together",
        "library": "reading in a cozy library",
        "mushroom": "gathering near mushroom cottages",
    }
    for token, activity in activity_terms.items():
        if token in text:
            return activity
    return "posing together with matching props"


def _props_from_text(text: str) -> tuple[str, ...]:
    props: list[str] = []
    mapping = {
        "tea": ("tea table", "teapot", "teacups", "flowers", "chairs"),
        "bak": ("mixing bowl", "wooden spoon", "cake", "apron"),
        "garden": ("watering can", "flower basket", "seed packets", "garden tools"),
        "reading": ("storybook", "books", "reading chair", "lamp"),
        "library": ("storybook", "bookshelves", "reading chair", "lamp"),
        "mushroom": ("mushroom house", "tiny flowers", "woodland path"),
    }
    for token, values in mapping.items():
        if token in text:
            props.extend(values)
    return tuple(dict.fromkeys(props or ["botanical sprigs", "small cottagecore accessories"]))


def _palette_from_text(text: str, palette: str) -> tuple[str, ...]:
    if "tea" in text or "rabbit" in text or "bunny" in text:
        return ("warm cream", "sage green", "muted blue", "soft coral")
    if palette:
        parts = tuple(part.strip() for part in re.split(r"[,/]", palette) if part.strip())
        if parts:
            return parts
    return ("warm cream", "sage green", "soft brown", "dusty rose")


def _clothing_from_text(text: str) -> tuple[str, ...]:
    if "tea" in text and ("rabbit" in text or "bunny" in text):
        return (
            "mother rabbit in sage green dress",
            "father rabbit in muted blue jacket",
            "two young rabbits in soft cream outfits",
        )
    return ("coordinated cottagecore clothing where characters are present",)


def _character_type_from_text(text: str) -> str:
    if "family" in text or "tea" in text:
        return "coordinated woodland family characters"
    return "coordinated whimsical woodland characters"


def _environment_from_text(text: str) -> str:
    if "tea" in text or "garden" in text:
        return "cozy cottage garden with flowers and woodland atmosphere"
    if "library" in text or "reading" in text:
        return "cozy woodland reading nook with books and warm interior details"
    return "warm cottagecore woodland setting"
