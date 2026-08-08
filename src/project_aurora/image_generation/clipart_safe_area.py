"""Safe-area validation for transparent clipart source images."""

from __future__ import annotations

from pathlib import Path

from PIL import Image


DEFAULT_MINIMUM_MARGIN_RATIO = 0.05
VISIBLE_ALPHA_THRESHOLD = 32
NORMALIZED_ARTWORK_RATIO = 0.85


def validate_clipart_safe_area(
    path: Path,
    *,
    minimum_margin_ratio: float = DEFAULT_MINIMUM_MARGIN_RATIO,
) -> tuple[str, ...]:
    """Require visible artwork to stay clear of every canvas edge."""
    if not 0 <= minimum_margin_ratio < 0.5:
        raise ValueError("minimum_margin_ratio must be between 0 and 0.5.")
    try:
        with Image.open(path) as image:
            rgba = image.convert("RGBA")
    except OSError as error:
        return (f"{path.name}: invalid PNG ({error}).",)

    alpha = rgba.getchannel("A")
    visible = alpha.point(
        lambda value: 255 if value >= VISIBLE_ALPHA_THRESHOLD else 0
    )
    bounds = visible.getbbox()
    if bounds is None:
        return (f"{path.name}: no visible artwork.",)

    left, top, right, bottom = bounds
    width, height = rgba.size
    margins = {
        "left": left / max(1, width),
        "top": top / max(1, height),
        "right": (width - right) / max(1, width),
        "bottom": (height - bottom) / max(1, height),
    }
    unsafe = tuple(
        side for side, ratio in margins.items() if ratio < minimum_margin_ratio
    )
    if not unsafe:
        return ()
    rendered = ", ".join(
        f"{side} {margins[side]:.1%}" for side in unsafe
    )
    return (
        f"{path.name}: artwork violates the {minimum_margin_ratio:.0%} transparent "
        f"safe area ({rendered}); subject may be cropped.",
    )


def normalize_complete_clipart_safe_area(
    path: Path,
    *,
    artwork_ratio: float = NORMALIZED_ARTWORK_RATIO,
) -> None:
    """Center known-complete artwork inside a deterministic transparent border."""
    if not 0 < artwork_ratio < 1:
        raise ValueError("artwork_ratio must be between 0 and 1.")
    with Image.open(path) as image:
        rgba = image.convert("RGBA")
    visible = rgba.getchannel("A").point(
        lambda value: 255 if value >= VISIBLE_ALPHA_THRESHOLD else 0
    )
    bounds = visible.getbbox()
    if bounds is None:
        raise ValueError(f"{path.name} has no visible artwork to normalize.")

    artwork = rgba.crop(bounds)
    max_width = max(1, int(round(rgba.width * artwork_ratio)))
    max_height = max(1, int(round(rgba.height * artwork_ratio)))
    scale = min(max_width / artwork.width, max_height / artwork.height, 1.0)
    resized = artwork.resize(
        (
            max(1, int(round(artwork.width * scale))),
            max(1, int(round(artwork.height * scale))),
        ),
        Image.Resampling.LANCZOS,
    )
    canvas = Image.new("RGBA", rgba.size, (255, 255, 255, 0))
    left = (rgba.width - resized.width) // 2
    top = (rgba.height - resized.height) // 2
    canvas.alpha_composite(resized, dest=(left, top))
    canvas.save(path, format="PNG")
