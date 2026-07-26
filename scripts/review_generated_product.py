"""Create a local contact sheet for reviewing generated Aurora product assets."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image, ImageDraw

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_PATH))

from project_aurora.planning.production_queue_manager import ProductionQueueManager  # noqa: E402


QUEUE_PATH = PROJECT_ROOT / "data" / "aurora" / "production_queue" / "queue.json"
JOBS_DIR = PROJECT_ROOT / "data" / "aurora" / "jobs"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Review generated Aurora product assets.")
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--approve", action="store_true")
    parser.add_argument("--reject", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    queue = ProductionQueueManager(queue_path=QUEUE_PATH)
    job = next((item for item in queue.list_jobs() if item.id == args.job_id), None)
    if job is None:
        raise SystemExit(f"Job not found: {args.job_id}")
    job_root = next(JOBS_DIR.glob(f"{job.id.replace('-', '_')[:12]}*"), None)
    if job_root is None:
        raise SystemExit(f"Job workspace not found for {args.job_id}")
    final_dir = job_root / "final_product_images"
    files = tuple(
        path for path in sorted(final_dir.glob("*")) if path.suffix.casefold() in {".png", ".jpg", ".jpeg"}
    )
    contact_sheet = job_root / "review" / "contact_sheet.jpg"
    contact_sheet.parent.mkdir(parents=True, exist_ok=True)
    _write_contact_sheet(contact_sheet, job.product_name, job.category, job.id, files)
    if args.approve:
        (job_root / "review" / "APPROVED").write_text("APPROVED\n", encoding="utf-8")
    if args.reject:
        (job_root / "review" / "REJECTED").write_text("REJECTED\n", encoding="utf-8")
    print("PRODUCT VISUAL REVIEW")
    print("Job ID")
    print(job.id)
    print("Product")
    print(job.product_name)
    print("Contact Sheet")
    print(contact_sheet)
    print("Approval Status")
    print("APPROVED" if (job_root / "review" / "APPROVED").exists() else "REVIEW_REQUIRED")


def _write_contact_sheet(
    output_path: Path,
    product_name: str,
    category: str,
    job_id: str,
    files: tuple[Path, ...],
) -> None:
    thumb_size = (320, 320)
    columns = 2
    rows = max(1, (len(files) + columns - 1) // columns)
    header_height = 120
    canvas = Image.new("RGB", (columns * thumb_size[0], header_height + rows * thumb_size[1]), "white")
    draw = ImageDraw.Draw(canvas)
    draw.text((16, 16), f"{product_name}\n{category}\n{job_id}", fill="black")
    for index, path in enumerate(files):
        with Image.open(path) as image:
            preview = image.convert("RGB")
            preview.thumbnail((300, 300), Image.Resampling.LANCZOS)
        x = (index % columns) * thumb_size[0] + 10
        y = header_height + (index // columns) * thumb_size[1] + 10
        canvas.paste(preview, (x, y))
        draw.text((x, y + 304), path.name[:42], fill="black")
    canvas.save(output_path, format="JPEG", quality=92)


if __name__ == "__main__":
    main()
