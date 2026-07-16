"""Review technically valid images that lack reliable visual style QA."""

from __future__ import annotations

import argparse
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_PATH))

from project_aurora.image_generation.image_inspector import inspect_png  # noqa: E402
from project_aurora.production.product_factory import REPORT_COLLECTION  # noqa: E402
from project_aurora.storage.csv_storage import CSVStorage  # noqa: E402
from project_aurora.storage.memory_manager import MemoryManager  # noqa: E402


@dataclass(frozen=True, slots=True)
class StyleImageReview:
    """Review details for one image."""

    product: str
    path: str
    technical_qa: str
    dominant_colors: tuple[str, ...]
    background_estimate: str
    composition_metrics: dict[str, float]
    semantic_evaluation_status: str
    blocking_reasons: tuple[str, ...]
    preview_path: str


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Review failed style-QA images.")
    parser.add_argument("--job-id")
    parser.add_argument("--approve-job")
    parser.add_argument("--reject-job")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    memory = MemoryManager(CSVStorage(base_path=PROJECT_ROOT / "data" / "aurora"))
    if args.approve_job:
        approve_job(memory, args.approve_job)
        print(f"Approved existing images for job {args.approve_job}.")
        return
    if args.reject_job:
        reject_job(memory, args.reject_job)
        print(f"Rejected existing images for job {args.reject_job}.")
        return

    job_ids = (args.job_id,) if args.job_id else _failed_image_qa_job_ids(memory)
    for job_id in job_ids:
        reviews = review_job_images(memory, job_id)
        print_review(job_id, reviews)


def review_job_images(memory: MemoryManager, job_id: str) -> tuple[StyleImageReview, ...]:
    report = memory.load_record(REPORT_COLLECTION, job_id)
    product = str(report.get("product", ""))
    generated_dir = _generated_images_dir(report)
    active_files = tuple(sorted(generated_dir.glob("*.png"), key=lambda item: item.name))
    if not active_files:
        active_files = _latest_rejected_attempt_files(generated_dir)
    contact_sheet = _contact_sheet_path(generated_dir, job_id)
    if active_files:
        build_contact_sheet(active_files, contact_sheet)
    reviews = []
    for path in active_files:
        inspection = inspect_png(path)
        technical = "PASS" if inspection.is_valid else f"FAIL: {inspection.classification}"
        reviews.append(
            StyleImageReview(
                product=product,
                path=str(path),
                technical_qa=technical,
                dominant_colors=_dominant_colors(path),
                background_estimate=_background_estimate(path),
                composition_metrics=_composition_metrics(path),
                semantic_evaluation_status="NOT_EVALUATED",
                blocking_reasons=() if inspection.is_valid else (inspection.classification,),
                preview_path=str(contact_sheet),
            )
        )
    memory.save_record(
        "style_image_reviews",
        job_id,
        {
            "job_id": job_id,
            "product": product,
            "reviews": [_review_to_dict(review) for review in reviews],
            "contact_sheet": str(contact_sheet),
            "created_at": datetime.now().isoformat(),
        },
    )
    return tuple(reviews)


def approve_job(memory: MemoryManager, job_id: str) -> None:
    report = memory.load_record(REPORT_COLLECTION, job_id)
    generated_dir = _generated_images_dir(report)
    if not tuple(generated_dir.glob("*.png")):
        for source in _latest_rejected_attempt_files(generated_dir):
            shutil.move(str(source), str(generated_dir / source.name))
    memory.save_record(
        "style_image_reviews",
        f"{job_id}_approval",
        {
            "job_id": job_id,
            "decision": "APPROVED",
            "resume_from_stage": "image_qa",
            "reuse_existing_images": True,
            "created_at": datetime.now().isoformat(),
        },
    )


def reject_job(memory: MemoryManager, job_id: str) -> None:
    memory.save_record(
        "style_image_reviews",
        f"{job_id}_rejection",
        {
            "job_id": job_id,
            "decision": "REJECTED",
            "regeneration_permitted": True,
            "created_at": datetime.now().isoformat(),
        },
    )


def print_review(job_id: str, reviews: tuple[StyleImageReview, ...]) -> None:
    print("STYLE IMAGE REVIEW")
    print("")
    print("Job ID")
    print(job_id)
    for review in reviews:
        print("")
        print("Product")
        print(review.product)
        print("Path")
        print(review.path)
        print("Technical QA")
        print(review.technical_qa)
        print("Dominant Colors")
        for color in review.dominant_colors:
            print(color)
        print("Background Estimate")
        print(review.background_estimate)
        print("Composition Metrics Available")
        print(review.composition_metrics)
        print("Semantic Evaluation Status")
        print(review.semantic_evaluation_status)
        print("Blocking Reasons")
        print(", ".join(review.blocking_reasons) or "None")
        print("Preview Path")
        print(review.preview_path)


def build_contact_sheet(paths: tuple[Path, ...], output_path: Path) -> Path:
    thumbs: list[Image.Image] = []
    for path in paths:
        with Image.open(path) as image:
            thumb = image.convert("RGBA")
            thumb.thumbnail((240, 240))
            canvas = Image.new("RGBA", (260, 290), (255, 255, 255, 255))
            canvas.alpha_composite(thumb, ((260 - thumb.width) // 2, 10))
            draw = ImageDraw.Draw(canvas)
            draw.text((10, 260), path.name[:32], fill=(0, 0, 0, 255))
            thumbs.append(canvas)
    if not thumbs:
        return output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)
    sheet = Image.new("RGBA", (260 * len(thumbs), 290), (255, 255, 255, 255))
    for index, thumb in enumerate(thumbs):
        sheet.alpha_composite(thumb, (260 * index, 0))
    sheet.convert("RGB").save(output_path, format="JPEG", quality=90)
    return output_path


def _failed_image_qa_job_ids(memory: MemoryManager) -> tuple[str, ...]:
    ids = []
    for record_id in memory.list_records(REPORT_COLLECTION):
        if record_id == "latest":
            continue
        report = memory.load_record(REPORT_COLLECTION, record_id)
        if report.get("failed_stage") == "image_qa":
            ids.append(record_id)
    return tuple(ids)


def _generated_images_dir(report: dict[str, Any]) -> Path:
    job_paths = report.get("job_paths")
    if not isinstance(job_paths, dict):
        raise RuntimeError("Production report does not include job_paths.")
    value = job_paths.get("generated_images_dir")
    if not isinstance(value, str) or not value:
        raise RuntimeError("Production report does not include generated_images_dir.")
    return Path(value)


def _latest_rejected_attempt_files(generated_dir: Path) -> tuple[Path, ...]:
    rejected = generated_dir / "rejected"
    attempts = tuple(
        sorted(
            (path for path in rejected.glob("attempt_*") if path.is_dir()),
            key=lambda item: item.name,
        )
    )
    if not attempts:
        return ()
    return tuple(sorted(attempts[-1].glob("*.png"), key=lambda item: item.name))


def _contact_sheet_path(generated_dir: Path, job_id: str) -> Path:
    return generated_dir.parent / "style_review" / f"{job_id}_contact_sheet.jpg"


def _dominant_colors(path: Path) -> tuple[str, ...]:
    with Image.open(path) as image:
        rgb = image.convert("RGB").resize((64, 64))
        colors = rgb.getcolors(maxcolors=4096) or []
    top = sorted(colors, key=lambda item: item[0], reverse=True)[:5]
    return tuple(f"#{r:02x}{g:02x}{b:02x}" for _, (r, g, b) in top)


def _background_estimate(path: Path) -> str:
    with Image.open(path) as image:
        rgba = image.convert("RGBA")
        width, height = rgba.size
        pixels = [
            rgba.getpixel((0, 0)),
            rgba.getpixel((width - 1, 0)),
            rgba.getpixel((0, height - 1)),
            rgba.getpixel((width - 1, height - 1)),
        ]
    avg_alpha = sum(pixel[3] for pixel in pixels) / len(pixels)
    avg_light = sum(sum(pixel[:3]) / 3 for pixel in pixels) / len(pixels)
    if avg_alpha < 25:
        return "transparent"
    if avg_light > 230:
        return "light"
    if avg_light < 60:
        return "dark"
    return "mixed"


def _composition_metrics(path: Path) -> dict[str, float]:
    with Image.open(path) as image:
        rgba = image.convert("RGBA").resize((128, 128))
        alpha = rgba.getchannel("A")
        histogram = alpha.histogram()
        visible = sum(count for value, count in enumerate(histogram) if value > 0)
    total = 128 * 128
    visible_ratio = round(visible / total, 3)
    return {
        "visible_ratio": visible_ratio,
        "whitespace_ratio": round(1 - visible_ratio, 3),
    }


def _review_to_dict(review: StyleImageReview) -> dict[str, Any]:
    return {
        "product": review.product,
        "path": review.path,
        "technical_qa": review.technical_qa,
        "dominant_colors": list(review.dominant_colors),
        "background_estimate": review.background_estimate,
        "composition_metrics": review.composition_metrics,
        "semantic_evaluation_status": review.semantic_evaluation_status,
        "blocking_reasons": list(review.blocking_reasons),
        "preview_path": review.preview_path,
    }


if __name__ == "__main__":
    main()
