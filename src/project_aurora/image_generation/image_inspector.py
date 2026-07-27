"""Inspect generated PNG files for visible image content."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from PIL import Image, ImageStat, UnidentifiedImageError


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

    red_channel, green_channel, blue_channel, alpha_channel = rgba.split()
    alpha_minimum, alpha_maximum = alpha_channel.getextrema()
    alpha_histogram = alpha_channel.histogram()
    visible_pixels = (width * height) - alpha_histogram[0]
    visible_mask = alpha_channel.point(lambda alpha: 255 if alpha > 0 else 0)
    all_visible_pixels_white = _all_visible_pixels_white(
        rgba,
        visible_mask,
        visible_pixels,
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


def _all_visible_pixels_white(
    rgba: Image.Image,
    visible_mask: Image.Image,
    visible_pixels: int,
) -> bool:
    if not visible_pixels:
        return False
    bbox = visible_mask.getbbox()
    if bbox is None:
        return False
    if visible_pixels > 500_000:
        cropped = rgba.crop(bbox)
        width, height = cropped.size
        step = max(1, int((width * height / 10_000) ** 0.5))
        pixels = cropped.load()
        for x in range(0, width, step):
            for y in range(0, height, step):
                red, green, blue, alpha = pixels[x, y]
                if alpha > 0 and (red < 250 or green < 250 or blue < 250):
                    return False
        return True
    red_channel, green_channel, blue_channel, _alpha_channel = rgba.split()
    return all(
        extrema == (255, 255)
        for extrema in ImageStat.Stat(
            red_channel,
            visible_mask,
        ).extrema
        + ImageStat.Stat(green_channel, visible_mask).extrema
        + ImageStat.Stat(blue_channel, visible_mask).extrema
    )


def inspect_png_directory(directory: Path) -> tuple[GeneratedImageInspection, ...]:
    """Inspect every PNG in a directory sorted by filename."""
    if not directory.exists():
        return ()
    return tuple(inspect_png(path) for path in sorted(directory.glob("*.png")))
