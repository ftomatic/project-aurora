"""Preview Aurora seasonal review, creative brief, blueprints, and prompts."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from types import SimpleNamespace

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(SRC_PATH))

from project_aurora.creative.product_creative_director import ProductionCreativeDirector  # noqa: E402
from project_aurora.image_generation.image_prompt_builder import StructuredImagePromptBuilder  # noqa: E402
from project_aurora.planning.production_queue_manager import ProductionJob  # noqa: E402
from project_aurora.research.seasonal_intelligence import SeasonalIntelligence  # noqa: E402


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Preview one Aurora creative brief.")
    parser.add_argument("--product", required=True)
    parser.add_argument("--product-type", default="digital illustration collection")
    parser.add_argument("--style", default="Whimsical Storybook Watercolor")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    job = ProductionJob(
        id="preview-job",
        priority="High",
        product_name=args.product,
        category=args.product_type,
        style=args.style,
        seasonal_theme="Evergreen",
        keywords=tuple(args.product.casefold().split()),
        confidence_score=0.95,
        estimated_competition="Low",
        estimated_demand="High",
        estimated_revenue=100,
        target_customer="Etsy digital printable buyers",
        required_image_count=4,
    )
    art_direction = SimpleNamespace(
        recommended_style=args.style,
        palette="cream, sage, blush, warm gold",
        rendering_family=args.style,
        rendering_method=args.style,
        composition="cohesive four-image product collection",
        background_treatment="clean commercial background",
        lighting="soft natural lighting",
        texture="high-quality printable detail",
        mood="cohesive commercial",
    )
    seasonal = SeasonalIntelligence().evaluate(job.product_name, job.seasonal_theme, job.category)
    brief = ProductionCreativeDirector().create_brief(job, art_direction)
    prompts = StructuredImagePromptBuilder().build_prompts(brief, seasonal)
    print("CREATIVE PREVIEW")
    print("")
    print("Seasonal Decision")
    print(seasonal.production_decision)
    print("Reason")
    print(seasonal.reason)
    print("")
    print("Creative Brief")
    print(brief.visual_story)
    print("Palette")
    print(", ".join(brief.palette))
    print("Text Policy")
    print(brief.text_policy)
    print("")
    print("Image Blueprint")
    for blueprint in brief.image_blueprint:
        print(f"{blueprint.image_number}. {blueprint.role} - {blueprint.purpose}")
    print("")
    print("Prompts")
    for prompt in prompts:
        print(f"{prompt.image_number}. {prompt.blueprint_role}")
        print(prompt.prompt)
        print("")
    print("QA Rules")
    print("No text, no years, coherent roles, matching filenames, no stale assets.")


if __name__ == "__main__":
    main()
