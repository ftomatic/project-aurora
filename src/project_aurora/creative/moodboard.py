"""Structured internal moodboard generation."""

from __future__ import annotations

from project_aurora.creative.creative_brief import Moodboard
from project_aurora.creative.style_library import CreativeStyle


class MoodboardGenerator:
    """Create non-copyrighted design guidance moodboards."""

    def generate(
        self,
        *,
        theme: str,
        audience: str,
        emotion: str,
        style: CreativeStyle,
        composition: str,
    ) -> Moodboard:
        motifs = _motifs(theme)
        return Moodboard(
            moodboard_id=_moodboard_id(theme, style.style_id),
            mood_keywords=tuple(dict.fromkeys((*style.visual_mood, emotion, audience))),
            visual_motifs=motifs,
            materials=(style.texture, "print-ready digital artwork", "commercial Etsy preview layout"),
            textures=(style.texture, style.rendering_approach),
            lighting=(_lighting_for(emotion), "consistent collection lighting"),
            composition_examples=(composition, "coordinated collection rhythm", "clear buyer-facing preview hierarchy"),
        )


def _motifs(theme: str) -> tuple[str, ...]:
    lowered = theme.casefold()
    if "woodland" in lowered:
        return ("baby animals", "leaves", "soft trees", "tiny mushrooms")
    if "strawberry" in lowered:
        return ("strawberries", "flowers", "ribbon", "summer party accents")
    if "wedding" in lowered:
        return ("wildflowers", "delicate stems", "stationery borders", "soft florals")
    if "teacher" in lowered:
        return ("rainbows", "alphabet forms", "classroom labels", "friendly icons")
    if "kitchen" in lowered:
        return ("herbs", "ceramic jars", "linen", "botanical stems")
    if "academia" in lowered:
        return ("books", "candles", "ink", "antique keys")
    return ("hero motif", "supporting accents", "texture details", "collection markers")


def _lighting_for(emotion: str) -> str:
    lowered = emotion.casefold()
    if "moody" in lowered:
        return "warm low directional light"
    if "bright" in lowered or "playful" in lowered:
        return "bright soft studio light"
    return "soft commercial natural light"


def _moodboard_id(theme: str, style_id: str) -> str:
    return "_".join(f"{theme}_{style_id}_moodboard".casefold().replace("-", "_").split())
