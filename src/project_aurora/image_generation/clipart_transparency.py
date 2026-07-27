"""Validate and repair true transparency for clipart customer PNG files."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from PIL import Image


TRANSPARENCY_REQUIRED = "TRANSPARENCY_REQUIRED"
MIN_TRANSPARENT_PIXEL_RATIO = 0.10
TRANSPARENT_ALPHA_THRESHOLD = 250
CORNER_ALPHA_THRESHOLD = 32


@dataclass(frozen=True, slots=True)
class ClipartTransparencyResult:
    """Transparency validation and repair result for one clipart image."""

    status: str
    image_path: str
    image_mode: str
    transparent_pixel_percentage: float
    corner_alpha_values: tuple[int, int, int, int]
    background_removal_attempted: bool
    regeneration_required: bool
    final_validation_result: str
    errors: tuple[str, ...] = ()


def ensure_clipart_transparency(image: Image.Image) -> tuple[Image.Image, ClipartTransparencyResult]:
    """Return an RGBA image with true transparent background or failure details."""
    original_mode = image.mode
    rgba = image.convert("RGBA")
    initial = validate_clipart_transparency(rgba, image_mode=original_mode)
    if initial.status == "PASS":
        return rgba, initial

    repaired = remove_edge_connected_light_background(rgba)
    repaired_validation = validate_clipart_transparency(
        repaired,
        image_mode=original_mode,
        background_removal_attempted=True,
    )
    return repaired, repaired_validation


def validate_clipart_file(path: Path) -> ClipartTransparencyResult:
    """Validate one PNG file as true transparent clipart."""
    try:
        with Image.open(path) as image:
            result = validate_clipart_transparency(
                image.convert("RGBA"),
                image_path=str(path),
                image_mode=image.mode,
            )
    except OSError as error:
        return ClipartTransparencyResult(
            status="FAIL",
            image_path=str(path),
            image_mode="",
            transparent_pixel_percentage=0.0,
            corner_alpha_values=(255, 255, 255, 255),
            background_removal_attempted=False,
            regeneration_required=True,
            final_validation_result=TRANSPARENCY_REQUIRED,
            errors=(f"Invalid PNG: {error}",),
        )
    return result


def validate_clipart_transparency(
    image: Image.Image,
    *,
    image_path: str = "",
    image_mode: str = "",
    background_removal_attempted: bool = False,
) -> ClipartTransparencyResult:
    """Validate alpha transparency from pixels, not visual background patterns."""
    rgba = image.convert("RGBA")
    width, height = rgba.size
    alpha = rgba.getchannel("A")
    histogram = alpha.histogram()
    transparent_pixels = sum(histogram[:TRANSPARENT_ALPHA_THRESHOLD])
    transparent_percentage = (transparent_pixels / max(1, width * height)) * 100
    corners = _corner_alpha_values(rgba)
    errors: list[str] = []
    if "A" not in rgba.getbands():
        errors.append("No alpha channel exists.")
    if transparent_percentage < MIN_TRANSPARENT_PIXEL_RATIO * 100:
        errors.append(
            "Fewer than 10 percent of pixels have alpha below 250."
        )
    if any(value > CORNER_ALPHA_THRESHOLD for value in corners):
        errors.append("All four corners must be transparent or nearly transparent.")
    if _opaque_light_border_ratio(rgba) > 0.75:
        errors.append("Large opaque light-colored background region remains.")
    if _edge_grid_or_checker_pattern_detected(rgba):
        errors.append("Grid or checkerboard background remains.")

    status = "FAIL" if errors else "PASS"
    return ClipartTransparencyResult(
        status=status,
        image_path=image_path,
        image_mode=image_mode or rgba.mode,
        transparent_pixel_percentage=round(transparent_percentage, 3),
        corner_alpha_values=corners,
        background_removal_attempted=background_removal_attempted,
        regeneration_required=bool(errors),
        final_validation_result="PASS" if not errors else TRANSPARENCY_REQUIRED,
        errors=tuple(errors),
    )


def remove_edge_connected_light_background(image: Image.Image) -> Image.Image:
    """Remove only edge-connected light/paper/grid background pixels."""
    rgba = image.convert("RGBA")
    width, height = rgba.size
    pixels = rgba.load()
    visited: set[tuple[int, int]] = set()
    queue: deque[tuple[int, int]] = deque()
    seed_colors = _border_background_colors(rgba)

    for point in _border_points(width, height):
        if _is_background_pixel(pixels[point], seed_colors):
            queue.append(point)
            visited.add(point)

    while queue:
        x, y = queue.popleft()
        for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if nx < 0 or ny < 0 or nx >= width or ny >= height:
                continue
            point = (nx, ny)
            if point in visited:
                continue
            if _is_background_pixel(pixels[point], seed_colors):
                visited.add(point)
                queue.append(point)

    repaired = rgba.copy()
    repaired_pixels = repaired.load()
    for x, y in visited:
        red, green, blue, _alpha = repaired_pixels[x, y]
        repaired_pixels[x, y] = (red, green, blue, 0)
    return repaired


def _corner_alpha_values(image: Image.Image) -> tuple[int, int, int, int]:
    width, height = image.size
    return (
        image.getpixel((0, 0))[3],
        image.getpixel((width - 1, 0))[3],
        image.getpixel((0, height - 1))[3],
        image.getpixel((width - 1, height - 1))[3],
    )


def _opaque_light_border_ratio(image: Image.Image) -> float:
    points = tuple(_border_points(*image.size))
    if not points:
        return 0.0
    opaque_light = sum(1 for point in points if _is_light_opaque(image.getpixel(point)))
    return opaque_light / len(points)


def _edge_grid_or_checker_pattern_detected(image: Image.Image) -> bool:
    width, height = image.size
    if width < 8 or height < 8:
        return False
    edge_pixels = [image.getpixel(point) for point in _border_points(width, height)]
    light_opaque = [pixel for pixel in edge_pixels if _is_light_opaque(pixel)]
    if len(light_opaque) < len(edge_pixels) * 0.60:
        return False
    unique_light = {
        (round(pixel[0] / 12), round(pixel[1] / 12), round(pixel[2] / 12))
        for pixel in light_opaque
    }
    return len(unique_light) >= 2


def _border_background_colors(image: Image.Image) -> tuple[tuple[int, int, int], ...]:
    colors: list[tuple[int, int, int]] = []
    for point in _border_points(*image.size):
        pixel = image.getpixel(point)
        if _is_light_opaque(pixel):
            colors.append(pixel[:3])
    if not colors:
        return ()
    sampled = colors[:: max(1, len(colors) // 64)]
    return tuple(dict.fromkeys(sampled))


def _border_points(width: int, height: int) -> Iterable[tuple[int, int]]:
    for x in range(width):
        yield (x, 0)
        yield (x, height - 1)
    for y in range(1, height - 1):
        yield (0, y)
        yield (width - 1, y)


def _is_background_pixel(
    pixel: tuple[int, int, int, int],
    seed_colors: tuple[tuple[int, int, int], ...],
) -> bool:
    if pixel[3] < TRANSPARENT_ALPHA_THRESHOLD:
        return True
    if not _is_light_opaque(pixel):
        return False
    if not seed_colors:
        return True
    return any(_color_distance(pixel[:3], color) <= 18 for color in seed_colors)


def _is_light_opaque(pixel: tuple[int, int, int, int]) -> bool:
    red, green, blue, alpha = pixel
    if alpha < TRANSPARENT_ALPHA_THRESHOLD:
        return False
    brightness = (red + green + blue) / 3
    spread = max(red, green, blue) - min(red, green, blue)
    return brightness >= 205 and spread <= 38


def _color_distance(
    first: tuple[int, int, int],
    second: tuple[int, int, int],
) -> float:
    return sum((a - b) ** 2 for a, b in zip(first, second, strict=True)) ** 0.5
