"""Market segment classification for Aurora portfolio planning."""

from __future__ import annotations


SEGMENT_KEYWORDS: dict[str, tuple[str, ...]] = {
    "Nursery": ("nursery", "baby", "bunny", "teddy", "newborn"),
    "Holiday": ("holiday", "valentine", "easter", "thanksgiving"),
    "Christmas": ("christmas", "santa", "ornament", "gingerbread"),
    "Halloween": ("halloween", "ghost", "pumpkin", "witch"),
    "Teacher": ("teacher", "classroom", "school"),
    "Wedding": ("wedding", "bridal", "bride"),
    "Birthday": ("birthday", "party", "celebration", "invitation"),
    "Baby Shower": ("baby shower", "shower"),
    "Kitchen": ("kitchen", "recipe", "baking", "coffee"),
    "Farmhouse": ("farmhouse", "farm", "country"),
    "Boho": ("boho", "neutral", "macrame"),
    "Coquette": ("coquette", "bow", "ribbon"),
    "Botanical": ("botanical", "floral", "flower", "garden"),
    "Animals": ("animal", "animals", "woodland", "farm", "pet"),
    "Vintage": ("vintage", "retro", "antique"),
    "Digital Paper": ("digital paper", "paper", "pattern"),
    "Clipart": ("clipart", "graphics", "commercial"),
    "Seamless Patterns": ("seamless", "pattern"),
    "Sublimation": ("sublimation", "t-shirt", "mug"),
    "Wall Art": ("wall art", "print", "poster"),
    "Invitations": ("invitation", "invite"),
    "Planner Stickers": ("planner", "sticker"),
    "Watercolor": ("watercolor",),
    "Commercial Graphics": ("commercial", "graphics", "bundle"),
}


PRODUCT_TYPE_SEGMENTS: dict[str, str] = {
    "clipart": "Clipart",
    "digital paper": "Digital Paper",
    "party printable": "Birthday",
    "sticker sheet": "Planner Stickers",
    "wall art": "Wall Art",
    "junk journal": "Vintage",
}


def classify_market_category(
    product_name: str,
    product_type: str,
    keywords: tuple[str, ...],
) -> str:
    """Classify a product opportunity into a broad market segment."""
    context = " ".join((product_name, product_type, " ".join(keywords))).casefold()
    for segment, terms in SEGMENT_KEYWORDS.items():
        if any(term in context for term in terms):
            return segment
    return PRODUCT_TYPE_SEGMENTS.get(product_type.casefold(), "Wildcard")


def normalize_audience(value: str) -> str:
    """Return a stable audience bucket for balancing."""
    context = value.casefold()
    if "parent" in context:
        return "Parents"
    if "teacher" in context:
        return "Teachers"
    if "crafter" in context:
        return "Crafters"
    if "buyer" in context:
        return "Digital Printable Buyers"
    return value.strip().title() or "General Buyers"
