"""Collection Intelligence engine."""

from __future__ import annotations

from pathlib import Path

from project_aurora.collections.collection_memory import CollectionMemory
from project_aurora.collections.collection_models import (
    CollectionArtDirection,
    CollectionBlueprint,
    CollectionOpportunity,
    CollectionPlan,
    CollectionProduct,
    CollectionRoadmap,
    CollectionScore,
    CrossSellPlan,
    ShopHealth,
)
from project_aurora.collections.collection_settings import CollectionSettings
from project_aurora.muse.muse_engine import MuseEngine
from project_aurora.storage.memory_manager import MemoryManager


PROJECT_ROOT = Path(__file__).resolve().parents[3]


class CollectionDiscovery:
    """Athena-style deterministic collection discovery."""

    def discover(self) -> tuple[CollectionOpportunity, ...]:
        """Return local collection opportunities."""
        return (
            _opportunity(
                "French Cottage Kitchen",
                "French herb kitchen decor",
                "home decor buyers",
                "Evergreen",
                ("Vintage Botanical", "Farmhouse", "French Vintage"),
                "Buyers want coordinated kitchen prints and botanical herb art.",
                ("Sage", "Rosemary", "Lavender", "Basil", "Thyme"),
            ),
            _opportunity(
                "Woodland Nursery",
                "soft baby animal nursery",
                "parents",
                "Spring",
                ("Soft Pastel Nursery", "Storybook Watercolor"),
                "Parents want gentle nursery art and matching baby animal clipart.",
                ("Bunny", "Fox", "Deer", "Bear", "Hedgehog"),
            ),
            _opportunity(
                "Boho Teacher",
                "warm classroom decor and teacher printables",
                "teachers",
                "Back To School",
                ("Flat Vector", "Boho", "Editorial Minimal"),
                "Teachers want coordinated classroom visuals that feel warm and modern.",
                ("Rainbow", "Alphabet", "Welcome Sign", "Name Tags", "Schedule Cards"),
            ),
            _opportunity(
                "Strawberry Birthday",
                "summer berry party printables",
                "parents",
                "Summer",
                ("Storybook Watercolor", "Soft Cottagecore"),
                "Parents want matching birthday invitations, decor, and thank-you pieces.",
                ("Invitation", "Cupcake Toppers", "Favor Tags", "Thank You Cards", "Party Banner"),
            ),
            _opportunity(
                "Cottagecore Mushrooms",
                "woodland mushroom commercial graphics",
                "crafters",
                "Autumn",
                ("Cottagecore Watercolor", "Vintage Botanical"),
                "Crafters want coordinated mushroom clipart, papers, and stickers.",
                ("Clipart", "Digital Paper", "Sticker Sheet", "Wall Art", "Gift Tags"),
            ),
            _opportunity(
                "Neutral Baby",
                "soft neutral nursery and baby shower set",
                "parents",
                "Evergreen",
                ("Soft Pastel Nursery", "Scandinavian Minimal"),
                "Parents buy gender-neutral nursery decor and matching baby shower pieces.",
                ("Wall Art", "Milestone Cards", "Baby Shower Invitation", "Thank You Cards", "Digital Paper"),
            ),
            _opportunity(
                "Celestial Nursery",
                "moon and star nursery collection",
                "parents",
                "Evergreen",
                ("Soft Pastel Nursery", "Minimal Line Art"),
                "Parents search for cohesive moon, star, and nursery room decor.",
                ("Wall Art", "Digital Paper", "Alphabet Posters", "Milestone Cards", "Clipart"),
            ),
            _opportunity(
                "Wildflower Wedding",
                "romantic floral wedding stationery",
                "brides",
                "Wedding Season",
                ("Pressed Flowers", "Luxury Wedding", "Fine Line Floral"),
                "Brides want matching invitations, menus, signage, and thank-you cards.",
                ("Invitation", "Details Card", "Menu", "Welcome Sign", "Thank You Cards"),
            ),
            _opportunity(
                "Vintage Christmas",
                "nostalgic holiday printables",
                "holiday crafters",
                "Christmas",
                ("Vintage Christmas", "Folk Art"),
                "Crafters search for coordinated vintage holiday graphics.",
                ("Santa", "Holly", "Wreath", "Candle", "Stocking"),
            ),
            _opportunity(
                "Pastel Halloween",
                "cute pastel spooky printable set",
                "parents and teachers",
                "Halloween",
                ("Kawaii", "Paper Cut", "Cute Halloween"),
                "Teachers and parents want friendly Halloween classroom and party art.",
                ("Ghost", "Pumpkin", "Bat", "Candy", "Witch Hat"),
            ),
            _opportunity(
                "Coastal Summer",
                "beach scrapbook and decor collection",
                "scrapbookers",
                "Summer",
                ("Coastal", "Loose Watercolor"),
                "Summer buyers want beach-themed papers and printable wall decor.",
                ("Shell", "Starfish", "Sailboat", "Sea Grass", "Lighthouse"),
            ),
            _opportunity(
                "Dark Academia Library",
                "moody literary wall art collection",
                "students and readers",
                "Autumn",
                ("Dark Academia", "Victorian Engraving", "Oil Painting"),
                "Readers search for moody bookish prints and library decor.",
                ("Books", "Candle", "Raven", "Ink Bottle", "Library Key"),
            ),
            _opportunity(
                "Farmhouse Botanicals",
                "rustic botanical home decor",
                "home decor buyers",
                "Evergreen",
                ("Farmhouse", "Botanical Sketch", "Vintage Botanical"),
                "Kitchen and home decor buyers want coordinated botanical signs.",
                ("Eucalyptus", "Olive Branch", "Cotton", "Fern", "Wildflower"),
            ),
        )


class CollectionScorer:
    """Score collection opportunities."""

    def __init__(self, memory: CollectionMemory, cross_sell_weight: int = 15) -> None:
        self._memory = memory
        self._cross_sell_weight = cross_sell_weight

    def score(self, opportunity: CollectionOpportunity) -> CollectionScore:
        """Return score dimensions for a collection."""
        trend = _trend_score(opportunity)
        commercial = _commercial_score(opportunity)
        seasonality = _seasonality_score(opportunity)
        competition = _competition_score(opportunity)
        duplicate = self._memory.duplicate_score(opportunity.name)
        portfolio_fit = max(0, 92 - duplicate)
        cross_sell = min(100, 70 + len(opportunity.complementary_products) * self._cross_sell_weight // 5)
        evergreen = 90 if opportunity.season == "Evergreen" else 72
        expansion = _expansion_score(opportunity)
        brand = _brand_consistency_score(opportunity)
        revenue = _revenue_score(opportunity)
        confidence = round((trend + commercial + seasonality + portfolio_fit + cross_sell) / 5)
        return CollectionScore(
            trend_score=trend,
            commercial_score=commercial,
            seasonality=seasonality,
            competition=competition,
            portfolio_fit=portfolio_fit,
            cross_sell_potential=cross_sell,
            evergreen_score=evergreen,
            average_confidence=confidence,
            expansion_potential=expansion,
            brand_consistency=brand,
            revenue_potential=revenue,
        )


class CollectionDesigner:
    """Muse collection art director."""

    def __init__(self, muse: MuseEngine) -> None:
        self._muse = muse

    def design(self, opportunity: CollectionOpportunity) -> CollectionArtDirection:
        """Return collection-wide art direction."""
        if opportunity.aesthetics:
            try:
                profile = self._muse.style_profile(opportunity.aesthetics[0])
                return CollectionArtDirection(
                    master_style=profile.name,
                    palette=profile.typical_color_palette[:4],
                    rendering=profile.rendering_method,
                    mood=tuple(_mood_for_collection(opportunity)),
                    typography="Future: collection typography system",
                    composition_rules=(
                        "Use coordinated product compositions.",
                        "Keep each listing visibly part of the same collection.",
                    ),
                    consistency_rules=(
                        f"Use {profile.name} across all products.",
                        "Reuse palette, lighting, line quality, and rendering method.",
                    ),
                    variation_rules=(
                        "Change subject per product.",
                        "Keep composition rhythm consistent while varying focal details.",
                    ),
                )
            except ValueError:
                pass
        direction = self._muse.select_style(
            product=opportunity.name,
            audience=opportunity.audience,
            season=opportunity.season,
            competition="Medium",
            product_type="collection",
        )
        palette = tuple(part.strip() for part in direction.palette.split(",") if part.strip())[:4]
        return CollectionArtDirection(
            master_style=direction.recommended_style,
            palette=palette,
            rendering=direction.rendering_method,
            mood=tuple(part.strip() for part in direction.mood.split() if part.strip()) or (direction.mood,),
            typography="Future: collection typography system",
            composition_rules=(
                direction.composition,
                "Keep each listing visibly part of the same collection.",
            ),
            consistency_rules=(
                f"Use {direction.recommended_style} across all products.",
                "Reuse palette, lighting, line quality, and rendering method.",
            ),
            variation_rules=(
                "Change subject per product.",
                "Keep composition rhythm consistent while varying focal details.",
            ),
        )

    def blueprint(self, opportunity: CollectionOpportunity, art_direction: CollectionArtDirection) -> CollectionBlueprint:
        """Return the merchant-facing collection blueprint."""
        primary = art_direction.palette[:3] or ("Cream", "Sage", "Blush")
        secondary = art_direction.palette[3:6] or tuple(_secondary_colors_for_collection(opportunity))
        return CollectionBlueprint(
            theme_name=opportunity.name,
            target_audience=opportunity.audience,
            visual_identity=f"{opportunity.name} coordinated {art_direction.master_style} collection",
            primary_colors=primary,
            secondary_colors=secondary,
            typography_style=_typography_for_collection(opportunity),
            illustration_style=art_direction.master_style,
            mood=art_direction.mood,
            season=opportunity.season,
            commercial_positioning=(
                f"Cohesive Etsy collection for {opportunity.audience}: "
                f"{opportunity.customer_intent}"
            ),
        )


class CollectionProductPlanner:
    """Atlas-style product planner inside one collection."""

    def __init__(self, collection_size: int) -> None:
        self._collection_size = collection_size

    def plan(self, opportunity: CollectionOpportunity) -> tuple[CollectionProduct, ...]:
        """Create coordinated products inside the collection."""
        return self.plan_all(opportunity)[: self._collection_size]

    def plan_all(self, opportunity: CollectionOpportunity) -> tuple[CollectionProduct, ...]:
        """Create the full collection roadmap expansion."""
        product_specs = _product_expansion_for_collection(opportunity)
        products = tuple(
            CollectionProduct(
                product_name=f"{opportunity.name} {subject}",
                subject=subject,
                product_type=product_type,
                keywords=(
                    opportunity.name.casefold(),
                    subject.casefold(),
                    product_type,
                    opportunity.theme.casefold(),
                ),
            )
            for subject, product_type in product_specs
        )
        return tuple(dict.fromkeys(products))


class MerchantBrain:
    """Generate cross-sell strategy for a collection."""

    def generate(self, opportunity: CollectionOpportunity, products: tuple[CollectionProduct, ...]) -> CrossSellPlan:
        """Return related products and bundle ideas."""
        product_names = tuple(product.product_name for product in products)
        return CrossSellPlan(
            related_products=product_names,
            collection_links=tuple(f"Part of Collection: {opportunity.name}" for _ in products),
            bundle_suggestions=(
                f"{opportunity.name} Complete Bundle",
                f"{opportunity.name} Mini Set",
                f"{opportunity.name} Commercial Graphics Pack",
            ),
            future_collection_ideas=(
                f"{opportunity.name} Digital Paper",
                f"{opportunity.name} Wall Art",
                f"{opportunity.name} Sticker Sheet",
            ),
            matching_products=tuple(f"Matching {product.subject}" for product in products),
            matching_collections=_matching_collections(opportunity),
        )


class CollectionIntelligenceEngine:
    """Coordinate discovery, scoring, design, product planning, and memory."""

    def __init__(
        self,
        memory: MemoryManager | None = None,
        settings: CollectionSettings | None = None,
        collection_memory: CollectionMemory | None = None,
        muse: MuseEngine | None = None,
    ) -> None:
        self._memory = memory
        self._settings = settings or CollectionSettings.from_file(PROJECT_ROOT / "config" / "collections.yaml")
        self._collection_memory = collection_memory or CollectionMemory(memory=memory)
        self._muse = muse or MuseEngine(memory=memory)
        self._discovery = CollectionDiscovery()
        self._scorer = CollectionScorer(self._collection_memory, self._settings.cross_sell_weight)
        self._designer = CollectionDesigner(self._muse)
        self._planner = CollectionProductPlanner(self._settings.collection_size)
        self._merchant = MerchantBrain()

    def run(self) -> CollectionPlan:
        """Return the best collection plan."""
        opportunities = self._discovery.discover()
        scored = tuple((opportunity, self._scorer.score(opportunity)) for opportunity in opportunities)
        eligible = tuple(item for item in scored if item[1].total >= self._settings.minimum_collection_score)
        if not eligible and not self._settings.allow_single_products:
            eligible = scored
        opportunity, score = max(eligible, key=lambda item: (item[1].total, item[1].cross_sell_potential, item[0].name))
        art_direction = self._designer.design(opportunity)
        blueprint = self._designer.blueprint(opportunity, art_direction)
        roadmap_products = self._planner.plan_all(opportunity)
        products = self._planner.plan(opportunity)
        cross_sell = self._merchant.generate(opportunity, products)
        roadmap = _roadmap(opportunity, roadmap_products, completed=products)
        shop_health = _shop_health(self._collection_memory.records, opportunity, roadmap_products)
        plan = CollectionPlan(
            collection=opportunity,
            score=score,
            art_direction=art_direction,
            products=products,
            cross_sell=cross_sell,
            why_chosen=(
                f"{opportunity.name} collection scored {score.total} with strong "
                f"cross-sell potential and {opportunity.customer_intent}"
            ),
            blueprint=blueprint,
            roadmap=roadmap,
            shop_health=shop_health,
        )
        self._collection_memory.remember(opportunity.name, tuple(product.product_name for product in products))
        if self._memory is not None:
            self._memory.save_record("collection_plans", _slug(opportunity.name), _plan_to_record(plan))
        return plan


def _opportunity(
    name: str,
    theme: str,
    audience: str,
    season: str,
    aesthetics: tuple[str, ...],
    customer_intent: str,
    products: tuple[str, ...],
) -> CollectionOpportunity:
    return CollectionOpportunity(
        name=name,
        theme=theme,
        audience=audience,
        season=season,
        aesthetics=aesthetics,
        customer_intent=customer_intent,
        complementary_products=products,
    )


def _trend_score(opportunity: CollectionOpportunity) -> int:
    if "French" in opportunity.name or "Dark Academia" in opportunity.name:
        return 92
    if opportunity.season in {"Christmas", "Halloween", "Summer"}:
        return 88
    return 84


def _commercial_score(opportunity: CollectionOpportunity) -> int:
    return 90 if len(opportunity.complementary_products) >= 5 else 76


def _expansion_score(opportunity: CollectionOpportunity) -> int:
    return min(100, 62 + len(_product_expansion_for_collection(opportunity)) * 4)


def _brand_consistency_score(opportunity: CollectionOpportunity) -> int:
    return 94 if opportunity.aesthetics else 82


def _revenue_score(opportunity: CollectionOpportunity) -> int:
    high_value_types = {
        product_type
        for _subject, product_type in _product_expansion_for_collection(opportunity)
        if product_type in {"clipart", "digital paper", "wall art", "party printable"}
    }
    return min(100, 70 + len(high_value_types) * 6 + len(opportunity.complementary_products))


def _seasonality_score(opportunity: CollectionOpportunity) -> int:
    return 86 if opportunity.season != "Evergreen" else 78


def _competition_score(opportunity: CollectionOpportunity) -> int:
    return 48 if "Vintage Christmas" in opportunity.name else 38


def _product_type_for_collection(opportunity: CollectionOpportunity) -> str:
    lowered = opportunity.name.casefold()
    if "kitchen" in lowered or "library" in lowered or "nursery" in lowered:
        return "wall art"
    if "paper" in lowered or "coastal" in lowered:
        return "digital paper"
    if "halloween" in lowered or "christmas" in lowered:
        return "clipart"
    return "clipart"


def _product_expansion_for_collection(opportunity: CollectionOpportunity) -> tuple[tuple[str, str], ...]:
    lowered = opportunity.name.casefold()
    if "woodland nursery" in lowered:
        return (
            ("Clipart Bundle", "clipart"),
            ("Digital Paper Pack", "digital paper"),
            ("Nursery Wall Art", "wall art"),
            ("Milestone Cards", "party printable"),
            ("Growth Chart", "wall art"),
            ("Alphabet Posters", "wall art"),
            ("Baby Shower Invitation", "party printable"),
            ("Thank You Cards", "party printable"),
            ("Gift Tags", "party printable"),
            ("Stickers", "sticker sheet"),
        )
    if "teacher" in lowered:
        return (
            ("Classroom Decor", "wall art"),
            ("Alphabet Posters", "wall art"),
            ("Name Tags", "party printable"),
            ("Schedule Cards", "party printable"),
            ("Reward Stickers", "sticker sheet"),
            ("Bulletin Board Borders", "digital paper"),
            ("Welcome Sign", "wall art"),
            ("Teacher Planner Stickers", "sticker sheet"),
        )
    if "birthday" in lowered:
        return (
            ("Invitation", "party printable"),
            ("Cupcake Toppers", "party printable"),
            ("Favor Tags", "party printable"),
            ("Thank You Cards", "party printable"),
            ("Party Banner", "party printable"),
            ("Digital Paper Pack", "digital paper"),
            ("Clipart Bundle", "clipart"),
            ("Stickers", "sticker sheet"),
        )
    if "wedding" in lowered:
        return (
            ("Invitation", "party printable"),
            ("Details Card", "party printable"),
            ("Menu", "party printable"),
            ("Welcome Sign", "wall art"),
            ("Thank You Cards", "party printable"),
            ("Table Numbers", "party printable"),
            ("Clipart Bundle", "clipart"),
            ("Digital Paper Pack", "digital paper"),
        )
    if "mushroom" in lowered:
        return (
            ("Clipart Bundle", "clipart"),
            ("Digital Paper Pack", "digital paper"),
            ("Sticker Sheet", "sticker sheet"),
            ("Wall Art", "wall art"),
            ("Gift Tags", "party printable"),
            ("Junk Journal Pages", "digital paper"),
            ("Commercial Graphics Pack", "clipart"),
        )
    if "christmas" in lowered:
        return (
            ("Clipart Bundle", "clipart"),
            ("Digital Paper Pack", "digital paper"),
            ("Gift Tags", "party printable"),
            ("Wall Art", "wall art"),
            ("Stickers", "sticker sheet"),
            ("Greeting Cards", "party printable"),
            ("Commercial Graphics Pack", "clipart"),
        )
    if "kitchen" in lowered or "botanical" in lowered:
        return (
            ("Wall Art Set", "wall art"),
            ("Herb Clipart Bundle", "clipart"),
            ("Digital Paper Pack", "digital paper"),
            ("Recipe Cards", "party printable"),
            ("Kitchen Labels", "sticker sheet"),
            ("Gallery Wall Trio", "wall art"),
            ("Commercial Graphics Pack", "clipart"),
        )
    if "coastal" in lowered:
        return (
            ("Digital Paper Pack", "digital paper"),
            ("Clipart Bundle", "clipart"),
            ("Wall Art Set", "wall art"),
            ("Sticker Sheet", "sticker sheet"),
            ("Scrapbook Cards", "party printable"),
            ("Commercial Graphics Pack", "clipart"),
        )
    if "dark academia" in lowered:
        return (
            ("Wall Art Set", "wall art"),
            ("Clipart Bundle", "clipart"),
            ("Digital Paper Pack", "digital paper"),
            ("Bookmarks", "party printable"),
            ("Sticker Sheet", "sticker sheet"),
            ("Library Quote Prints", "wall art"),
        )
    return tuple((subject, _product_type_for_collection(opportunity)) for subject in opportunity.complementary_products)


def _mood_for_collection(opportunity: CollectionOpportunity) -> tuple[str, ...]:
    lowered = opportunity.name.casefold()
    if "french" in lowered:
        return ("Warm", "French", "Organic")
    if "dark academia" in lowered:
        return ("Moody", "Scholarly", "Antique")
    if "coastal" in lowered:
        return ("Breezy", "Seaside", "Relaxed")
    if "nursery" in lowered:
        return ("Soft", "Gentle", "Sweet")
    return ("Cohesive", "Commercial", "Seasonal")


def _secondary_colors_for_collection(opportunity: CollectionOpportunity) -> tuple[str, ...]:
    lowered = opportunity.name.casefold()
    if "woodland" in lowered:
        return ("Moss", "Taupe", "Soft Brown")
    if "strawberry" in lowered:
        return ("Berry Red", "Blush Pink", "Warm Yellow")
    if "wedding" in lowered:
        return ("Ivory", "Champagne", "Soft Green")
    if "teacher" in lowered:
        return ("Terracotta", "Mustard", "Cream")
    return ("Cream", "Sage", "Warm Gray")


def _typography_for_collection(opportunity: CollectionOpportunity) -> str:
    lowered = opportunity.name.casefold()
    if "wedding" in lowered:
        return "Elegant serif with light script accents"
    if "teacher" in lowered:
        return "Readable friendly classroom sans serif"
    if "birthday" in lowered:
        return "Playful rounded party lettering"
    if "dark academia" in lowered:
        return "Classic literary serif"
    return "Clean Etsy preview typography"


def _matching_collections(opportunity: CollectionOpportunity) -> tuple[str, ...]:
    lowered = opportunity.name.casefold()
    if "woodland" in lowered:
        return ("Neutral Baby", "Cottagecore Mushrooms", "Celestial Nursery")
    if "teacher" in lowered:
        return ("Pastel Halloween", "Valentine Classroom", "Back To School")
    if "wedding" in lowered:
        return ("Pressed Flower Wedding", "Neutral Boho Bridal", "Fine Line Floral")
    if "birthday" in lowered:
        return ("Summer Strawberry", "Cottagecore Party", "Berry Baby Shower")
    return ("Matching Digital Paper", "Matching Clipart", "Matching Wall Art")


def _roadmap(
    opportunity: CollectionOpportunity,
    planned: tuple[CollectionProduct, ...],
    completed: tuple[CollectionProduct, ...],
) -> CollectionRoadmap:
    planned_names = tuple(product.product_name for product in planned)
    completed_names = tuple(product.product_name for product in completed)
    remaining = tuple(name for name in planned_names if name not in set(completed_names))
    estimated_revenue = round(len(planned_names) * 18.0 + len(remaining) * 7.5, 2)
    return CollectionRoadmap(
        collection_name=opportunity.name,
        products_planned=planned_names,
        products_completed=completed_names,
        products_remaining=remaining,
        estimated_collection_revenue=estimated_revenue,
    )


def _shop_health(
    records: tuple[object, ...],
    current: CollectionOpportunity,
    planned: tuple[CollectionProduct, ...],
) -> ShopHealth:
    active = len(records) + 1
    largest_name = current.name
    largest_count = len(planned)
    for record in records:
        products = getattr(record, "products_inside", ())
        if len(products) > largest_count:
            largest_count = len(products)
            largest_name = str(getattr(record, "collection_name", largest_name))
    return ShopHealth(
        collections_active=active,
        collections_growing=sum(1 for record in records if len(getattr(record, "products_inside", ())) < 10) + 1,
        collections_completed=sum(1 for record in records if len(getattr(record, "products_inside", ())) >= 10),
        largest_collection=largest_name,
        revenue_concentration="Balanced" if active >= 3 else "Early collection buildout",
        collection_diversity="Healthy" if active >= 3 else "Growing",
    )


def _plan_to_record(plan: CollectionPlan) -> dict[str, object]:
    return {
        "collection": plan.collection.name,
        "why_chosen": plan.why_chosen,
        "products": [product.product_name for product in plan.products],
        "product_types": [product.product_type for product in plan.products],
        "blueprint": plan.blueprint.to_dict() if plan.blueprint else {},
        "roadmap": plan.roadmap.to_dict() if plan.roadmap else {},
        "shop_health": plan.shop_health.to_dict() if plan.shop_health else {},
        "master_style": plan.art_direction.master_style,
        "palette": list(plan.art_direction.palette),
        "commercial_score": plan.score.commercial_score,
        "collection_score": {
            "commercial_potential": plan.score.commercial_score,
            "portfolio_fit": plan.score.portfolio_fit,
            "expansion_potential": plan.score.expansion_potential,
            "cross_sell_potential": plan.score.cross_sell_potential,
            "brand_consistency": plan.score.brand_consistency,
            "revenue_potential": plan.score.revenue_potential,
            "total": plan.score.total,
        },
        "total_score": plan.score.total,
        "cross_sell": {
            "related_products": list(plan.cross_sell.related_products),
            "collection_links": list(plan.cross_sell.collection_links),
            "bundle_suggestions": list(plan.cross_sell.bundle_suggestions),
            "future_collection_ideas": list(plan.cross_sell.future_collection_ideas),
            "matching_products": list(plan.cross_sell.matching_products),
            "matching_collections": list(plan.cross_sell.matching_collections),
        },
        "created_at": plan.created_at.isoformat(),
    }


def render_collection_merchant_report(plan: CollectionPlan) -> str:
    """Return the Sprint 35 merchant-facing collection report."""
    roadmap = plan.roadmap
    lines = [
        "COLLECTION INTELLIGENCE",
        "",
        "Today's Collection",
        plan.collection.name,
        "",
        "Collection Score",
        str(plan.score.total),
        "",
        "Today's Releases",
    ]
    lines.extend(f"[x] {product.subject}" for product in plan.products)
    lines.extend(["", "Remaining Opportunities"])
    if roadmap:
        lines.extend(Path(name).name.replace(f"{plan.collection.name} ", "") for name in roadmap.products_remaining)
    lines.extend(
        [
            "",
            "Visual Identity",
            plan.blueprint.visual_identity if plan.blueprint else plan.art_direction.master_style,
            "",
            "Commercial Positioning",
            plan.blueprint.commercial_positioning if plan.blueprint else plan.why_chosen,
            "",
            "Estimated Collection Revenue",
            f"${roadmap.estimated_collection_revenue:.2f}" if roadmap else "",
            "",
            "Suggested Related Listings",
        ]
    )
    lines.extend(plan.cross_sell.related_products)
    lines.extend(["", "Matching Collections"])
    lines.extend(plan.cross_sell.matching_collections)
    if plan.shop_health:
        lines.extend(
            [
                "",
                "Shop Health",
                f"Collections Active: {plan.shop_health.collections_active}",
                f"Collections Growing: {plan.shop_health.collections_growing}",
                f"Collections Completed: {plan.shop_health.collections_completed}",
                f"Largest Collection: {plan.shop_health.largest_collection}",
                f"Collection Diversity: {plan.shop_health.collection_diversity}",
            ]
        )
    return "\n".join(lines)


def _slug(value: str) -> str:
    return "_".join(part for part in value.casefold().replace("-", " ").split() if part)
