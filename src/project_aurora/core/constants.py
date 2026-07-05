"""Constants for Project Aurora core components."""

from __future__ import annotations

DEFAULT_LOGGER_NAME = "project_aurora"

DEFAULT_PLATFORM_AGENTS: tuple[dict[str, object], ...] = (
    {
        "name": "ChiefArchitect",
        "department": "Architecture",
        "role": "System architecture lead",
        "enabled": True,
        "description": "Defines Aurora OS technical direction and boundaries.",
    },
    {
        "name": "ProductOwner",
        "department": "Product",
        "role": "Product priorities owner",
        "enabled": True,
        "description": "Maintains product intent, scope, and acceptance criteria.",
    },
    {
        "name": "MarketingAgent",
        "department": "Marketing",
        "role": "Marketing campaign coordinator",
        "enabled": True,
        "description": "Plans approved campaign messaging and marketing assets.",
    },
    {
        "name": "TrendResearchAgent",
        "department": "Research",
        "role": "Trend research analyst",
        "enabled": True,
        "description": "Summarizes market and creative trends from approved inputs.",
    },
    {
        "name": "ProductStrategyAgent",
        "department": "Product",
        "role": "Product strategy analyst",
        "enabled": True,
        "description": "Converts product goals into clear strategic options.",
    },
    {
        "name": "PromptFactoryAgent",
        "department": "Creative Systems",
        "role": "Prompt production specialist",
        "enabled": True,
        "description": "Creates reusable prompt patterns for approved workflows.",
    },
    {
        "name": "ImageGenerationAgent",
        "department": "Creative Systems",
        "role": "Image generation coordinator",
        "enabled": True,
        "description": "Coordinates image generation requests without provider logic.",
    },
    {
        "name": "ImageQAAgent",
        "department": "Quality",
        "role": "Image quality reviewer",
        "enabled": True,
        "description": "Reviews generated image outputs against defined criteria.",
    },
    {
        "name": "FileProcessingAgent",
        "department": "Operations",
        "role": "File workflow processor",
        "enabled": True,
        "description": "Organizes approved file intake and processing tasks.",
    },
    {
        "name": "MockupAgent",
        "department": "Creative Systems",
        "role": "Mockup preparation specialist",
        "enabled": True,
        "description": "Prepares product mockup workflows and review artifacts.",
    },
    {
        "name": "SEOAgent",
        "department": "Marketing",
        "role": "Search optimization specialist",
        "enabled": True,
        "description": "Drafts search metadata and keyword guidance from inputs.",
    },
    {
        "name": "EtsyAPIAgent",
        "department": "Integrations",
        "role": "Etsy integration placeholder",
        "enabled": True,
        "description": "Represents future Etsy integration ownership without API logic.",
    },
    {
        "name": "ReviewQueueAgent",
        "department": "Quality",
        "role": "Review queue coordinator",
        "enabled": True,
        "description": "Tracks items that need human or automated quality review.",
    },
    {
        "name": "LoggingAgent",
        "department": "Platform",
        "role": "Logging operations steward",
        "enabled": True,
        "description": "Coordinates registry-visible logging and observability duties.",
    },
    {
        "name": "ConfigurationManager",
        "department": "Platform",
        "role": "Configuration steward",
        "enabled": True,
        "description": "Maintains configuration ownership for platform components.",
    },
)
