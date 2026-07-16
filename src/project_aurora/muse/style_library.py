"""Muse style library loader."""

from __future__ import annotations

from pathlib import Path

from project_aurora.muse.style_profile import MuseStyleProfile


class MuseStyleLibrary:
    """Load style profiles from Aurora's local style library config."""

    def __init__(self, profiles: tuple[MuseStyleProfile, ...]) -> None:
        self._profiles = profiles

    @classmethod
    def from_file(cls, path: Path) -> "MuseStyleLibrary":
        """Load the simple Aurora style library YAML format."""
        if not path.exists():
            return cls(())
        profiles: list[MuseStyleProfile] = []
        current: dict[str, object] = {}
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            if not raw_line.strip() or raw_line.strip() == "styles:":
                continue
            stripped = raw_line.strip()
            if stripped.startswith("- name:"):
                if current:
                    profiles.append(_profile_from_record(current))
                current = {"name": stripped.split(":", maxsplit=1)[1].strip()}
                continue
            if ":" in stripped and current is not None:
                key, value = stripped.split(":", maxsplit=1)
                current[key.strip()] = _parse_value(value.strip())
        if current:
            profiles.append(_profile_from_record(current))
        return cls(tuple(profiles))

    @property
    def profiles(self) -> tuple[MuseStyleProfile, ...]:
        """Return available style profiles."""
        return self._profiles

    def get(self, style_name: str) -> MuseStyleProfile:
        """Return a style by name."""
        for profile in self._profiles:
            if profile.name.casefold() == style_name.casefold():
                return profile
        raise ValueError(f"Unknown Muse style: {style_name}.")


def _parse_value(value: str) -> object:
    if value.startswith("[") and value.endswith("]"):
        items = value[1:-1].split(",")
        return tuple(item.strip().strip("\"'") for item in items if item.strip())
    if value.isdigit():
        return int(value)
    return value.strip().strip("\"'")


def _profile_from_record(record: dict[str, object]) -> MuseStyleProfile:
    return MuseStyleProfile(
        name=str(record["name"]),
        description=str(record["description"]),
        typical_color_palette=tuple(record.get("typical_color_palette", ())),
        rendering_method=str(record["rendering_method"]),
        target_audience=tuple(record.get("target_audience", ())),
        products_it_fits=tuple(record.get("products_it_fits", ())),
        avoid_using_with=tuple(record.get("avoid_using_with", ())),
        commercial_appeal=int(record["commercial_appeal"]),
        difficulty=int(record["difficulty"]),
        trend_score=int(record["trend_score"]),
        seasonality=tuple(record.get("seasonality", ())),
    )
