"""Image generation cost estimation."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ImageCostEstimate:
    """Estimated image generation cost."""

    provider: str
    number_of_images: int
    cost_per_image: float
    total_cost: float

    def render(self) -> str:
        """Return formatted total cost."""
        return f"${self.total_cost:.2f}"


class ImageCostEstimator:
    """Estimate image generation costs from local configuration."""

    DEFAULT_RATES: dict[str, dict[str, float]] = {
        "mock": {"standard": 0.0, "high": 0.0},
        "openai": {"standard": 0.04, "high": 0.08},
    }

    def __init__(
        self,
        rates: dict[str, dict[str, float]] | None = None,
    ) -> None:
        self._rates = rates or self.DEFAULT_RATES

    def estimate(
        self,
        provider: str,
        quality: str,
        number_of_images: int,
    ) -> ImageCostEstimate:
        """Return a deterministic cost estimate."""
        if number_of_images <= 0:
            raise ValueError("Number of images must be greater than zero.")

        provider_key = provider.casefold()
        quality_key = quality.casefold()
        provider_rates = self._rates.get(provider_key, {})
        cost_per_image = provider_rates.get(
            quality_key,
            provider_rates.get("standard", 0.0),
        )
        total = round(cost_per_image * number_of_images, 4)
        return ImageCostEstimate(
            provider=provider_key,
            number_of_images=number_of_images,
            cost_per_image=cost_per_image,
            total_cost=total,
        )
