"""Art direction models for Aurora collection planning."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ArtDirection:
    """Visual direction for a planned collection."""

    art_style: str
    primary_palette: tuple[str, ...]
    secondary_palette: tuple[str, ...]
    shared_elements: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.art_style.strip():
            raise ValueError("art_style cannot be empty.")
        if not self.primary_palette:
            raise ValueError("primary_palette cannot be empty.")
        if not self.secondary_palette:
            raise ValueError("secondary_palette cannot be empty.")
        if not self.shared_elements:
            raise ValueError("shared_elements cannot be empty.")

        object.__setattr__(self, "primary_palette", tuple(self.primary_palette))
        object.__setattr__(
            self,
            "secondary_palette",
            tuple(self.secondary_palette),
        )
        object.__setattr__(self, "shared_elements", tuple(self.shared_elements))
