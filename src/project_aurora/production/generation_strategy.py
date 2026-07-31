"""Config-driven generation-family strategy for Aurora production jobs."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


GENERATION_MODE_AUTO = "AUTO"
GENERATION_MODE_STORYBOOK = "STORYBOOK"
GENERATION_MODE_CLIPART = "CLIPART"
GENERATION_MODE_CHARACTERS = "CHARACTERS"
GENERATION_MODE_BOTANICAL = "BOTANICAL"
GENERATION_MODE_DIGITAL_PAPER = "DIGITAL_PAPER"
GENERATION_MODE_WEDDING = "WEDDING"

SUPPORTED_GENERATION_STRATEGIES = {
    GENERATION_MODE_AUTO,
    GENERATION_MODE_STORYBOOK,
    GENERATION_MODE_CLIPART,
    GENERATION_MODE_CHARACTERS,
    GENERATION_MODE_BOTANICAL,
    GENERATION_MODE_DIGITAL_PAPER,
    GENERATION_MODE_WEDDING,
}

DEFAULT_GENERATION_MIX = {
    GENERATION_MODE_STORYBOOK: 50,
    GENERATION_MODE_CLIPART: 25,
    GENERATION_MODE_CHARACTERS: 10,
    GENERATION_MODE_BOTANICAL: 10,
    GENERATION_MODE_DIGITAL_PAPER: 5,
    GENERATION_MODE_WEDDING: 0,
}

STORYBOOK_HINTS = (
    "woodland",
    "storybook",
    "nursery",
    "tea party",
    "picnic",
    "garden",
    "gardening",
    "bakery",
    "baking",
    "cottage",
    "forest",
    "rabbit",
    "bunny",
    "fox",
    "mouse",
    "bear",
    "hedgehog",
    "animal family",
    "whimsical",
)
CLIPART_HINTS = (
    "clipart",
    "bundle",
    "elements",
    "icons",
    "objects",
    "mushroom",
    "teapot",
    "tea cups",
    "commercial graphics",
)
CHARACTER_HINTS = (
    "character",
    "characters",
    "girl",
    "boy",
    "people",
    "person",
    "family",
)
BOTANICAL_HINTS = (
    "botanical",
    "floral",
    "flower",
    "flowers",
    "wildflower",
    "lavender",
    "rose",
    "leaf",
    "leaves",
    "greenery",
)
DIGITAL_PAPER_HINTS = (
    "digital paper",
    "scrapbook paper",
    "paper pack",
    "pattern",
    "seamless",
)
WEDDING_HINTS = (
    "wedding",
    "bridal",
    "bride",
    "invitation",
    "menu",
    "save the date",
    "stationery",
)


@dataclass(frozen=True, slots=True)
class GenerationStrategyConfig:
    """Production mix targets for automatic generation-family selection."""

    mix: dict[str, int] = field(default_factory=lambda: dict(DEFAULT_GENERATION_MIX))
    source: str = "DEFAULT"

    @classmethod
    def from_file(cls, path: Path) -> "GenerationStrategyConfig":
        """Load generation mix weights from a tiny YAML subset."""
        if not path.exists():
            return cls()
        values: dict[str, int] = {}
        in_mix = False
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            stripped = raw_line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if not raw_line.startswith((" ", "\t")):
                in_mix = stripped.rstrip(":") == "generation_mix"
                continue
            if not in_mix or ":" not in stripped:
                continue
            key, value = stripped.split(":", maxsplit=1)
            mode = normalize_generation_mode(key)
            try:
                values[mode] = int(value.strip().strip("\"'"))
            except ValueError as exc:
                raise ValueError(f"Invalid generation mix weight for {key}.") from exc
        if not values:
            values = dict(DEFAULT_GENERATION_MIX)
        return cls(mix=values, source=str(path))


@dataclass(frozen=True, slots=True)
class GenerationStrategyDecision:
    """Resolved strategy for one queued product."""

    generation_mode: str
    listing_family: str
    reason: str
    config_source: str
    matched_terms: tuple[str, ...] = ()

    def source_evidence(self) -> tuple[str, ...]:
        """Return queue-safe evidence fields consumed by ProductFactory."""
        terms = ",".join(self.matched_terms)
        return (
            f"generation_mode={self.generation_mode}",
            f"listing_family={self.listing_family}",
            f"generation_strategy_reason={self.reason}",
            f"generation_mix_source={self.config_source}",
            f"generation_strategy_terms={terms}",
        )


class GenerationStrategyResolver:
    """Resolve Aurora product-family strategy from config and product context."""

    def __init__(self, config: GenerationStrategyConfig | None = None) -> None:
        self._config = config or GenerationStrategyConfig()

    @classmethod
    def from_file(cls, path: Path) -> "GenerationStrategyResolver":
        """Create a resolver from generation_mix.yaml."""
        return cls(GenerationStrategyConfig.from_file(path))

    def resolve(
        self,
        *,
        product_name: str,
        product_category: str = "",
        keywords: tuple[str, ...] = (),
        requested_mode: str = GENERATION_MODE_AUTO,
    ) -> GenerationStrategyDecision:
        """Resolve one generation-family decision."""
        requested = normalize_generation_mode(requested_mode)
        if requested != GENERATION_MODE_AUTO:
            return GenerationStrategyDecision(
                generation_mode=requested,
                listing_family=listing_family_for_generation_mode(requested),
                reason="Explicit generation mode override.",
                config_source=self._config.source,
            )

        context = _context_text(product_name, product_category, " ".join(keywords))
        for mode, hints in (
            (GENERATION_MODE_DIGITAL_PAPER, DIGITAL_PAPER_HINTS),
            (GENERATION_MODE_WEDDING, WEDDING_HINTS),
            (GENERATION_MODE_BOTANICAL, BOTANICAL_HINTS),
            (GENERATION_MODE_CHARACTERS, CHARACTER_HINTS),
            (GENERATION_MODE_STORYBOOK, STORYBOOK_HINTS),
            (GENERATION_MODE_CLIPART, CLIPART_HINTS),
        ):
            matches = _matched_terms(context, hints)
            if matches:
                return GenerationStrategyDecision(
                    generation_mode=mode,
                    listing_family=listing_family_for_generation_mode(mode),
                    reason=f"AUTO selected {mode} from product/category terms.",
                    config_source=self._config.source,
                    matched_terms=matches,
                )

        mode = _weighted_mode(context, self._config.mix)
        return GenerationStrategyDecision(
            generation_mode=mode,
            listing_family=listing_family_for_generation_mode(mode),
            reason="AUTO selected from configured generation mix.",
            config_source=self._config.source,
        )


def normalize_generation_mode(value: str) -> str:
    """Normalize CLI/config spelling into Aurora generation mode constants."""
    normalized = (value or GENERATION_MODE_AUTO).strip().upper()
    normalized = normalized.replace("-", "_").replace(" ", "_")
    aliases = {
        "DIGITALPAPER": GENERATION_MODE_DIGITAL_PAPER,
        "DIGITAL_PAPERS": GENERATION_MODE_DIGITAL_PAPER,
        "DIGITAL_PAPER": GENERATION_MODE_DIGITAL_PAPER,
        "STORYBOOK_SCENE": GENERATION_MODE_STORYBOOK,
        "CHARACTER": GENERATION_MODE_CHARACTERS,
        "CHARACTERS": GENERATION_MODE_CHARACTERS,
        "BOTANICALS": GENERATION_MODE_BOTANICAL,
        "WEDDINGS": GENERATION_MODE_WEDDING,
        "WEDDING_PRINTABLE": GENERATION_MODE_WEDDING,
        "WEDDING_STATIONERY": GENERATION_MODE_WEDDING,
    }
    mode = aliases.get(normalized, normalized)
    if mode not in SUPPORTED_GENERATION_STRATEGIES:
        raise ValueError(f"Unsupported generation mode: {value}.")
    return mode


def listing_family_for_generation_mode(generation_mode: str) -> str:
    """Map production strategy into the renderer's listing-family vocabulary."""
    mode = normalize_generation_mode(generation_mode)
    if mode == GENERATION_MODE_STORYBOOK:
        return GENERATION_MODE_STORYBOOK
    if mode == GENERATION_MODE_AUTO:
        return GENERATION_MODE_AUTO
    return GENERATION_MODE_CLIPART


def _weighted_mode(context: str, mix: dict[str, int]) -> str:
    configured = [
        (normalize_generation_mode(mode), max(0, int(weight)))
        for mode, weight in mix.items()
        if normalize_generation_mode(mode) != GENERATION_MODE_AUTO
    ]
    total = sum(weight for _mode, weight in configured)
    if total <= 0:
        return GENERATION_MODE_STORYBOOK
    bucket = sum(ord(character) for character in context) % total
    running = 0
    for mode, weight in configured:
        running += weight
        if bucket < running:
            return mode
    return configured[-1][0]


def _context_text(*values: str) -> str:
    return " ".join(
        value.casefold().replace("_", " ").replace("-", " ")
        for value in values
        if value
    )


def _matched_terms(context: str, terms: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(term for term in terms if term.casefold() in context)
