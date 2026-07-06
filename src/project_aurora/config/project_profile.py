"""Project profile model for Aurora brand context."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ProjectProfile:
    """Business and brand settings for an Aurora project."""

    project_id: str
    brand_name: str
    marketplace: str
    shop_url: str
    language: str
    currency: str
    target_customer: str
    brand_style: str
    default_ai_provider: str
    default_image_size: str
    default_price: float
    allowed_product_types: tuple[str, ...]
    allowed_platforms: tuple[str, ...]
    retention_policy: dict[str, str]

    def __post_init__(self) -> None:
        required_values = {
            "project_id": self.project_id,
            "brand_name": self.brand_name,
            "marketplace": self.marketplace,
            "shop_url": self.shop_url,
            "language": self.language,
            "currency": self.currency,
            "target_customer": self.target_customer,
            "brand_style": self.brand_style,
            "default_ai_provider": self.default_ai_provider,
            "default_image_size": self.default_image_size,
        }
        for field_name, value in required_values.items():
            if not value.strip():
                raise ValueError(f"{field_name} cannot be empty.")
        if self.default_price <= 0:
            raise ValueError("default_price must be greater than zero.")
        if not self.allowed_product_types:
            raise ValueError("allowed_product_types cannot be empty.")
        if not self.allowed_platforms:
            raise ValueError("allowed_platforms cannot be empty.")
        if not self.retention_policy:
            raise ValueError("retention_policy cannot be empty.")

        object.__setattr__(
            self,
            "allowed_product_types",
            tuple(self.allowed_product_types),
        )
        object.__setattr__(
            self,
            "allowed_platforms",
            tuple(self.allowed_platforms),
        )
        object.__setattr__(
            self,
            "retention_policy",
            dict(self.retention_policy),
        )

    def retention_summary(self) -> tuple[str, ...]:
        """Return human-readable retention policy lines."""
        labels = {
            "generated_images": "Generated images",
            "mockups": "Mockups",
            "prompt_packages": "Prompt packages",
            "seo_packages": "SEO packages",
            "listing_packages": "Listing packages",
            "workflow_logs": "Workflow logs",
        }
        actions = {
            "delete_after_publish": "delete after publish",
            "keep": "keep",
        }
        return tuple(
            f"{labels.get(key, key.replace('_', ' ').title())} "
            f"{actions.get(value, value.replace('_', ' '))}"
            for key, value in self.retention_policy.items()
        )
