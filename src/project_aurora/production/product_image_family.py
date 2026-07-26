"""Hard product-family rules for Aurora image generation."""

from __future__ import annotations

from dataclasses import dataclass


STORYBOOK_SCENE = "STORYBOOK_SCENE"
CLIPART = "CLIPART"


@dataclass(frozen=True, slots=True)
class ProductImageFamily:
    """Resolved image family for one product."""

    family: str
    transparent_background: bool
    openai_background: str
    prompt_requirements: tuple[str, ...]
    quality_requirements: tuple[str, ...]


def resolve_product_image_family(
    product_name: str,
    product_type: str,
    category: str = "",
) -> ProductImageFamily:
    """Resolve image behavior from product type, not visual guessing."""
    text = f"{product_name} {product_type} {category}".casefold().replace("_", " ")
    if any(term in text for term in ("clipart", "clip art", "clipart bundle", "png bundle")):
        return ProductImageFamily(
            family=CLIPART,
            transparent_background=True,
            openai_background="transparent",
            prompt_requirements=(
                "isolated illustrations only",
                "transparent PNG with alpha channel",
                "no background",
                "no paper texture",
                "no watercolor paper",
                "no beige background",
                "no grid, border, frame, or shadow",
                "artwork only",
            ),
            quality_requirements=(
                "transparent background",
                "alpha channel verified",
                "isolated artwork",
                "no clipping",
                "no paper texture",
            ),
        )
    if any(term in text for term in ("storybook scene", "scene collection", "complete illustration")):
        return ProductImageFamily(
            family=STORYBOOK_SCENE,
            transparent_background=False,
            openai_background="opaque",
            prompt_requirements=(
                "complete watercolor illustration",
                "rich storybook background",
                "cozy woodland environment",
                "full composition",
                "keep the background",
                "no transparency",
            ),
            quality_requirements=(
                "complete background",
                "rich environment",
                "beautiful composition",
                "no cropped characters",
                "fills canvas",
            ),
        )
    if "signature storybook animal collection" in text:
        return ProductImageFamily(
            family=STORYBOOK_SCENE,
            transparent_background=False,
            openai_background="opaque",
            prompt_requirements=(
                "complete watercolor illustration",
                "rich storybook background",
                "cozy woodland environment",
                "full composition",
                "keep the background",
                "no transparency",
            ),
            quality_requirements=(
                "complete background",
                "rich environment",
                "beautiful composition",
                "no cropped characters",
                "fills canvas",
            ),
        )
    return ProductImageFamily(
        family=CLIPART,
        transparent_background=True,
        openai_background="transparent",
        prompt_requirements=(
            "isolated illustrations only",
            "transparent PNG with alpha channel",
            "no background",
            "artwork only",
        ),
        quality_requirements=(
            "transparent background",
            "alpha channel verified",
            "isolated artwork",
        ),
    )
