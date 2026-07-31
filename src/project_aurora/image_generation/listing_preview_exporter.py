"""Create Etsy listing preview images from transparent customer PNGs."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path

from PIL import Image, ImageDraw

from project_aurora.image_generation.image_inspector import inspect_png
from project_aurora.image_generation.listing_family_decision import (
    LISTING_FAMILY_AUTO,
    LISTING_FAMILY_CLIPART,
    LISTING_FAMILY_STORYBOOK,
    ListingFamilyDecisionEngine,
)


PREVIEW_SIZE = (3000, 3000)
PREVIEW_DPI = 300
ARTWORK_FRAME_RATIO = 0.85
SCENE_FRAME_RATIO = 0.96
CREAM = (248, 243, 232, 255)


@dataclass(frozen=True, slots=True)
class ListingPreviewExportResult:
    """Result of creating Etsy preview listing images."""

    status: str
    preview_files: tuple[str, ...] = field(default_factory=tuple)
    errors: tuple[str, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(self, "status", self.status.strip().upper())
        object.__setattr__(self, "preview_files", tuple(self.preview_files))
        object.__setattr__(self, "errors", tuple(self.errors))
        object.__setattr__(self, "warnings", tuple(self.warnings))


class ListingPreviewExporter:
    """Export warm cream-background Etsy listing previews."""

    def __init__(
        self,
        final_images_dir: Path,
        output_dir: Path,
        output_prefix: str,
        storybook_scenes_dir: Path | None = None,
        required_count: int = 4,
        listing_family: str = LISTING_FAMILY_AUTO,
        product_category: str = "",
        niche_theme: str = "",
        intended_customer: str = "",
        artwork_composition: str = "",
        art_direction_fingerprint: str = "",
        decision_engine: ListingFamilyDecisionEngine | None = None,
    ) -> None:
        self._final_images_dir = final_images_dir
        self._storybook_scenes_dir = storybook_scenes_dir
        self._output_dir = output_dir
        self._output_prefix = output_prefix
        self._required_count = required_count
        self._listing_family = listing_family
        self._product_category = product_category
        self._niche_theme = niche_theme
        self._intended_customer = intended_customer
        self._artwork_composition = artwork_composition
        self._art_direction_fingerprint = art_direction_fingerprint
        self._decision_engine = decision_engine or ListingFamilyDecisionEngine()

    def export(self) -> ListingPreviewExportResult:
        """Create preview images from final transparent customer PNGs."""
        source_files = self._source_files()
        errors = self._validate_sources(source_files)
        if errors:
            return ListingPreviewExportResult(status="FAILED", errors=errors)
        self._output_dir.mkdir(parents=True, exist_ok=True)
        preview_files: list[str] = []
        scene_files = self._storybook_scene_files()
        scene_file = scene_files[0] if scene_files else None
        decision = self._decision_engine.decide(
            listing_family=self._listing_family,
            product_category=self._product_category,
            niche_theme=self._niche_theme,
            intended_customer=self._intended_customer,
            artwork_composition=self._artwork_composition,
            scene_available=scene_file is not None,
        )
        listing_family = decision.selected_family
        start_index = 1
        if listing_family == LISTING_FAMILY_STORYBOOK:
            for index, storybook_scene in enumerate(scene_files, start=1):
                output_path = self._output_dir / f"{self._output_prefix}_preview_{index:02d}.png"
                try:
                    self.render_storybook_primary_preview(storybook_scene, output_path)
                except RuntimeError as error:
                    return ListingPreviewExportResult(status="FAILED", errors=(str(error),))
                preview_files.append(str(output_path))
            self._write_manifest(preview_files, listing_family, scene_file, scene_files)
            return ListingPreviewExportResult(
                status="SUCCESS",
                preview_files=tuple(preview_files),
            )
        for index, source_path in enumerate(source_files, start=start_index):
            output_path = self._output_dir / f"{self._output_prefix}_preview_{index:02d}.png"
            if listing_family == LISTING_FAMILY_STORYBOOK and scene_file is not None:
                self.render_storybook_supporting_preview(
                    source_path,
                    scene_file,
                    output_path,
                    index=index,
                )
            else:
                self._export_one(source_path, output_path)
            preview_files.append(str(output_path))
        self._write_manifest(preview_files, listing_family, scene_file, scene_files)
        return ListingPreviewExportResult(status="SUCCESS", preview_files=tuple(preview_files))

    def _source_files(self) -> tuple[Path, ...]:
        if not self._final_images_dir.exists():
            return ()
        return tuple(sorted(self._final_images_dir.glob("*.png"), key=lambda item: item.name))

    def _storybook_scene_file(self) -> Path | None:
        scene_files = self._storybook_scene_files()
        return scene_files[0] if scene_files else None

    def _storybook_scene_files(self) -> tuple[Path, ...]:
        if self._storybook_scenes_dir is None or not self._storybook_scenes_dir.exists():
            return ()
        return tuple(sorted(self._storybook_scenes_dir.glob("*.png"), key=lambda item: item.name))

    def _validate_sources(self, source_files: tuple[Path, ...]) -> tuple[str, ...]:
        errors: list[str] = []
        if len(source_files) != self._required_count:
            errors.append(
                f"Expected exactly {self._required_count} final PNG files, found {len(source_files)}."
            )
        for path in source_files:
            inspection = inspect_png(path)
            if not inspection.is_valid:
                errors.append(f"{path.name}: invalid source image ({inspection.classification}).")
        return tuple(errors)

    @staticmethod
    def _export_one(source_path: Path, output_path: Path) -> None:
        with Image.open(source_path) as image:
            artwork = image.convert("RGBA")
            artwork = _trim_transparent_bounds(artwork)
            max_art = int(PREVIEW_SIZE[0] * ARTWORK_FRAME_RATIO)
            artwork.thumbnail((max_art, max_art), Image.Resampling.LANCZOS)
            canvas = _paper_texture()
            left = (PREVIEW_SIZE[0] - artwork.width) // 2
            top = (PREVIEW_SIZE[1] - artwork.height) // 2
            canvas.alpha_composite(artwork, (left, top))
            canvas.save(output_path, format="PNG", dpi=(PREVIEW_DPI, PREVIEW_DPI))

    @staticmethod
    def render_storybook_primary_preview(source_path: Path, output_path: Path) -> None:
        """Render a storybook scene as a full-canvas primary Etsy preview."""
        with Image.open(source_path) as image:
            scene = image.convert("RGBA")
            canvas = _cover_image(scene, PREVIEW_SIZE)
            occupancy = _opaque_occupancy(canvas)
            if occupancy[0] < 0.85 or occupancy[1] < 0.85:
                raise RuntimeError(
                    "Storybook primary preview scene occupies less than 85 percent "
                    "of preview width or height."
                )
            canvas.save(output_path, format="PNG", dpi=(PREVIEW_DPI, PREVIEW_DPI))

    @staticmethod
    def render_storybook_supporting_preview(
        source_path: Path,
        scene_path: Path,
        output_path: Path,
        *,
        index: int,
    ) -> None:
        """Render supporting STORYBOOK previews as full-canvas scene imagery."""
        del source_path
        with Image.open(scene_path) as scene_image:
            canvas = _storybook_scene_background(scene_image.convert("RGBA"), index=index)
            canvas.save(output_path, format="PNG", dpi=(PREVIEW_DPI, PREVIEW_DPI))

    def _write_manifest(
        self,
        preview_files: list[str],
        listing_family: str,
        scene_file: Path | None,
        scene_files: tuple[Path, ...] = (),
    ) -> None:
        manifest = {
            "listing_family": listing_family,
            "art_direction_fingerprint": self._art_direction_fingerprint,
            "primary_preview_source": str(scene_file) if scene_file else "",
            "storybook_scene_sources": [str(path) for path in scene_files],
            "preview_renderer": (
                "STORYBOOK_NATURE_FULL_CANVAS"
                if listing_family == LISTING_FAMILY_STORYBOOK
                else "CLIPART_TRANSPARENCY_PREVIEW"
            ),
            "preview_files": [Path(path).name for path in preview_files],
        }
        (self._output_dir / "preview_manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True),
            encoding="utf-8",
        )


def _trim_transparent_bounds(image: Image.Image) -> Image.Image:
    alpha = image.getchannel("A")
    bbox = alpha.getbbox()
    if bbox is None:
        return image
    return image.crop(bbox)


def _paper_texture() -> Image.Image:
    canvas = Image.new("RGBA", PREVIEW_SIZE, CREAM)
    draw = ImageDraw.Draw(canvas, "RGBA")
    for offset in range(0, PREVIEW_SIZE[0], 34):
        draw.line(
            ((offset, 0), (offset - PREVIEW_SIZE[0] // 3, PREVIEW_SIZE[1])),
            fill=(255, 255, 255, 12),
            width=2,
        )
    for offset in range(0, PREVIEW_SIZE[1], 41):
        draw.line(
            ((0, offset), (PREVIEW_SIZE[0], offset + PREVIEW_SIZE[1] // 4)),
            fill=(218, 204, 182, 10),
            width=1,
        )
    return canvas


def _storybook_scene_background(scene: Image.Image, *, index: int) -> Image.Image:
    """Create a full-canvas nature/storybook background for supporting previews."""
    from PIL import ImageEnhance

    background = _cover_image(_scene_variant(scene, index=index), PREVIEW_SIZE)
    background = ImageEnhance.Color(background).enhance(1.03)
    background = ImageEnhance.Brightness(background).enhance(1.01)
    return background


def _scene_variant(scene: Image.Image, *, index: int) -> Image.Image:
    """Return a gentle full-scene crop variant without adding graphic elements."""
    source = scene.convert("RGBA")
    width, height = source.size
    crop_ratio = 0.92 if index % 2 == 0 else 0.96
    crop_width = max(1, int(width * crop_ratio))
    crop_height = max(1, int(height * crop_ratio))
    offsets = {
        2: (0.04, 0.02),
        3: (0.00, 0.04),
        4: (0.08, 0.05),
        5: (0.03, 0.08),
    }
    ox, oy = offsets.get(index, (0.04, 0.04))
    left = min(width - crop_width, max(0, int(width * ox)))
    top = min(height - crop_height, max(0, int(height * oy)))
    return source.crop((left, top, left + crop_width, top + crop_height))


def _cover_image(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    """Resize an image to cover the target canvas, cropping only overflow."""
    source = image.convert("RGBA")
    target_width, target_height = size
    scale = max(target_width / source.width, target_height / source.height)
    resized_size = (
        max(1, round(source.width * scale)),
        max(1, round(source.height * scale)),
    )
    resized = source.resize(resized_size, Image.Resampling.LANCZOS)
    left = max(0, (resized.width - target_width) // 2)
    top = max(0, (resized.height - target_height) // 2)
    return resized.crop((left, top, left + target_width, top + target_height))


def _opaque_occupancy(image: Image.Image) -> tuple[float, float]:
    alpha = image.convert("RGBA").getchannel("A")
    bbox = alpha.getbbox()
    if bbox is None:
        return 0.0, 0.0
    left, top, right, bottom = bbox
    return (right - left) / image.width, (bottom - top) / image.height
