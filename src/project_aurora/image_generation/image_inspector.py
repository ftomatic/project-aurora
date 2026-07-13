"""Inspect generated PNG files for visible image content."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from PIL import Image, UnidentifiedImageError


ImageClassification = Literal[
    "VALID",
    "FULLY_TRANSPARENT",
    "ALL_WHITE",
    "INVALID_IMAGE",
    "EMPTY_FILE",
]


@dataclass(frozen=True, slots=True)
class GeneratedImageInspection:
    """Diagnostic details for one generated PNG file."""

    filename: str
    file_size: int
    dimensions: tuple[int, int] | None
    image_mode: str | None
    alpha_minimum: int | None
    alpha_maximum: int | None
    visible_pixels: int
    all_visible_pixels_white: bool
    classification: ImageClassification

    @property
    def is_valid(self) -> bool:
        """Return whether the image appears usable for production."""
        return self.classification == "VALID"


def inspect_png(path: Path) -> GeneratedImageInspection:
    """Inspect a PNG file for visible nonblank pixels."""
    file_size = path.stat().st_size if path.exists() else 0
    if file_size <= 0:
        return GeneratedImageInspection(
            filename=path.name,
            file_size=file_size,
            dimensions=None,
            image_mode=None,
            alpha_minimum=None,
            alpha_maximum=None,
            visible_pixels=0,
            all_visible_pixels_white=False,
            classification="EMPTY_FILE",
        )

    try:
        with Image.open(path) as image:
            image.verify()
        with Image.open(path) as image:
            original_mode = image.mode
            rgba = image.convert("RGBA")
            width, height = rgba.size
            pixel_data = (
                rgba.get_flattened_data()
                if hasattr(rgba, "get_flattened_data")
                else rgba.getdata()
            )
            pixels = list(pixel_data)
    except (OSError, SyntaxError, UnidentifiedImageError):
        return GeneratedImageInspection(
            filename=path.name,
            file_size=file_size,
            dimensions=None,
            image_mode=None,
            alpha_minimum=None,
            alpha_maximum=None,
            visible_pixels=0,
            all_visible_pixels_white=False,
            classification="INVALID_IMAGE",
        )

    alpha_values = [alpha for _, _, _, alpha in pixels]
    alpha_minimum = min(alpha_values)
    alpha_maximum = max(alpha_values)
    visible = [
        (red, green, blue)
        for red, green, blue, alpha in pixels
        if alpha > 0
    ]
    visible_pixels = len(visible)
    all_visible_pixels_white = bool(visible) and all(
        red == 255 and green == 255 and blue == 255
        for red, green, blue in visible
    )
    if alpha_maximum == 0:
        classification: ImageClassification = "FULLY_TRANSPARENT"
    elif all_visible_pixels_white:
        classification = "ALL_WHITE"
    else:
        classification = "VALID"

    return GeneratedImageInspection(
        filename=path.name,
        file_size=file_size,
        dimensions=(width, height),
        image_mode=original_mode,
        alpha_minimum=alpha_minimum,
        alpha_maximum=alpha_maximum,
        visible_pixels=visible_pixels,
        all_visible_pixels_white=all_visible_pixels_white,
        classification=classification,
    )


def inspect_png_directory(directory: Path) -> tuple[GeneratedImageInspection, ...]:
    """Inspect every PNG in a directory sorted by filename."""
    if not directory.exists():
        return ()
    return tuple(inspect_png(path) for path in sorted(directory.glob("*.png")))
