"""Merchant product specifications and QA for Etsy-ready assets."""

from __future__ import annotations

import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from PIL import Image


SPEC_VERSION = "2026-07-sprint-32"


@dataclass(frozen=True, slots=True)
class MerchantSpecification:
    """Commercial production blueprint for one product category."""

    category: str
    physical_dimensions: str
    pixel_dimensions: tuple[int, int] | None
    dpi: int
    file_formats: tuple[str, ...]
    bundle_size: int
    preview_requirements: tuple[str, ...]
    packaging: str
    thumbnail_rules: tuple[str, ...]
    etsy_expectations: tuple[str, ...]
    qa_requirements: tuple[str, ...]
    transparent: bool = False
    minimum_longest_edge: int | None = None
    required_ratios: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "physical_dimensions": self.physical_dimensions,
            "pixel_dimensions": list(self.pixel_dimensions) if self.pixel_dimensions else None,
            "dpi": self.dpi,
            "file_formats": list(self.file_formats),
            "bundle_size": self.bundle_size,
            "preview_requirements": list(self.preview_requirements),
            "packaging": self.packaging,
            "thumbnail_rules": list(self.thumbnail_rules),
            "etsy_expectations": list(self.etsy_expectations),
            "qa_requirements": list(self.qa_requirements),
            "transparent": self.transparent,
            "minimum_longest_edge": self.minimum_longest_edge,
            "required_ratios": list(self.required_ratios),
            "specification_version": SPEC_VERSION,
        }


@dataclass(frozen=True, slots=True)
class ProductManifest:
    """Stored commercial manifest for a generated product."""

    category: str
    specification_version: str
    width: int | None
    height: int | None
    pixels: str
    dpi: int
    formats: tuple[str, ...]
    bundle_size: int
    packaging: str
    qa_result: str
    files: tuple[str, ...]
    previews: tuple[str, ...]
    package_files: tuple[str, ...]
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "specification_version": self.specification_version,
            "width": self.width,
            "height": self.height,
            "pixels": self.pixels,
            "dpi": self.dpi,
            "formats": list(self.formats),
            "bundle_size": self.bundle_size,
            "packaging": self.packaging,
            "qa_result": self.qa_result,
            "files": list(self.files),
            "previews": list(self.previews),
            "package_files": list(self.package_files),
            "created_at": self.created_at.isoformat(),
        }


@dataclass(frozen=True, slots=True)
class MerchantQAResult:
    """QA result for a product against a merchant specification."""

    status: str
    specification: MerchantSpecification
    manifest: ProductManifest
    errors: tuple[str, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "specification": self.specification.to_dict(),
            "manifest": self.manifest.to_dict(),
            "errors": list(self.errors),
            "warnings": list(self.warnings),
        }


class MerchantSpecificationLibrary:
    """Resolve production blueprints by merchant category."""

    def resolve(self, category: str, product_name: str = "") -> MerchantSpecification:
        key = _category_key(f"{product_name} {category}")
        try:
            return _SPECIFICATIONS[key]
        except KeyError as error:
            raise RuntimeError(f"No merchant specification for category: {category}.") from error


class MerchantSpecificationQA:
    """Validate local product assets against Etsy-ready merchant specs."""

    def validate(self, category: str, product_dir: Path, product_name: str = "") -> MerchantQAResult:
        spec = MerchantSpecificationLibrary().resolve(category, product_name)
        files = _asset_files(product_dir, spec)
        previews = _preview_files(product_dir)
        packages = _package_files(product_dir)
        errors: list[str] = []
        if len(files) < spec.bundle_size:
            errors.append(
                f"{spec.category} requires at least {spec.bundle_size} "
                f"{'/'.join(spec.file_formats)} files, found {len(files)}."
            )
        if not previews:
            errors.append(f"{spec.category} requires {', '.join(spec.preview_requirements)}.")
        if spec.packaging == "ZIP" and not packages:
            errors.append(f"{spec.category} requires a ZIP package.")
        for path in files:
            errors.extend(f"{path.name}: {error}" for error in _validate_file(path, spec))
        if spec.required_ratios:
            present = {_ratio_label(path).casefold() for path in files}
            filename_text = " ".join(path.name.casefold() for path in files)
            missing = [
                ratio
                for ratio in spec.required_ratios
                if ratio.casefold() not in present and ratio.casefold() not in filename_text
            ]
            if missing:
                errors.append("Missing required print ratios: " + ", ".join(missing) + ".")
        if packages:
            errors.extend(_validate_zip(product_dir, packages[0], files))
        status = "PASS" if not errors else "FAIL"
        first_dimensions = _first_dimensions(files)
        manifest = ProductManifest(
            category=spec.category,
            specification_version=SPEC_VERSION,
            width=first_dimensions[0],
            height=first_dimensions[1],
            pixels=(
                f"{first_dimensions[0]} x {first_dimensions[1]}"
                if first_dimensions[0] and first_dimensions[1]
                else ""
            ),
            dpi=spec.dpi,
            formats=spec.file_formats,
            bundle_size=spec.bundle_size,
            packaging=spec.packaging,
            qa_result=status,
            files=tuple(str(path) for path in files),
            previews=tuple(str(path) for path in previews),
            package_files=tuple(str(path) for path in packages),
        )
        return MerchantQAResult(status=status, specification=spec, manifest=manifest, errors=tuple(errors))


def merchant_prompt_requirements(category: str, product_name: str = "") -> str:
    """Return prompt-ready merchant specification requirements."""
    spec = MerchantSpecificationLibrary().resolve(category, product_name)
    parts = [
        f"Merchant Category: {spec.category}",
        f"Physical dimensions: {spec.physical_dimensions}",
        f"DPI: {spec.dpi}",
        f"File format: {', '.join(spec.file_formats)}",
        f"Bundle size: {spec.bundle_size}",
        f"Packaging: {spec.packaging}",
        "Commercial quality Etsy-ready product.",
    ]
    if spec.pixel_dimensions:
        parts.append(f"Pixel dimensions: {spec.pixel_dimensions[0]}x{spec.pixel_dimensions[1]} px")
    if "seamless" in spec.qa_requirements:
        parts.append("Must be seamless and tileable.")
    if spec.transparent:
        parts.append("Transparent background required.")
    if spec.minimum_longest_edge:
        parts.append(f"Minimum longest edge: {spec.minimum_longest_edge} px.")
    return " ".join(parts)


def _category_key(value: str) -> str:
    lowered = value.casefold()
    if "digital paper" in lowered or "pattern" in lowered:
        return "digital paper"
    if "clipart" in lowered or "clip art" in lowered:
        return "clipart"
    if "sticker" in lowered:
        return "stickers"
    if "party" in lowered or "invitation" in lowered or "printable" in lowered:
        return "party printables"
    if "wall art" in lowered or "poster" in lowered or " art print" in lowered or lowered.endswith(" print"):
        return "printable wall art"
    return lowered.strip()


def _asset_files(product_dir: Path, spec: MerchantSpecification) -> tuple[Path, ...]:
    suffixes = {f".{fmt.casefold()}" for fmt in spec.file_formats}
    return tuple(
        path
        for path in sorted(product_dir.glob("*"), key=lambda item: item.name)
        if path.is_file()
        and path.suffix.casefold() in suffixes
        and "preview" not in path.stem.casefold()
    )


def _preview_files(product_dir: Path) -> tuple[Path, ...]:
    return tuple(
        path
        for path in sorted(product_dir.glob("*preview*"), key=lambda item: item.name)
        if path.is_file() and path.suffix.casefold() in {".jpg", ".jpeg", ".png"}
    )


def _package_files(product_dir: Path) -> tuple[Path, ...]:
    return tuple(sorted(product_dir.glob("*.zip"), key=lambda item: item.name))


def _validate_file(path: Path, spec: MerchantSpecification) -> tuple[str, ...]:
    errors: list[str] = []
    try:
        with Image.open(path) as image:
            size = image.size
            mode = image.mode
            dpi = image.info.get("dpi")
            fmt = (image.format or "").casefold()
    except OSError:
        return ("File is not a readable image.",)
    if path.suffix.casefold().lstrip(".") not in {fmt.casefold() for fmt in spec.file_formats}:
        errors.append("Wrong file format.")
    if spec.pixel_dimensions and size != spec.pixel_dimensions:
        errors.append(
            f"Incorrect dimensions: expected {spec.pixel_dimensions[0]}x{spec.pixel_dimensions[1]}, got {size[0]}x{size[1]}."
        )
    if spec.minimum_longest_edge and max(size) < spec.minimum_longest_edge:
        errors.append(f"Longest edge must be at least {spec.minimum_longest_edge}px.")
    if not _dpi_ok(dpi, spec.dpi):
        errors.append(f"Incorrect DPI: expected {spec.dpi}.")
    if "JPG" in spec.file_formats and mode != "RGB":
        errors.append("JPG files must be RGB.")
    if spec.transparent:
        if mode not in {"RGBA", "LA"}:
            errors.append("Transparent PNG must include an alpha channel.")
        else:
            try:
                with Image.open(path) as image:
                    alpha = image.convert("RGBA").getchannel("A")
                    if alpha.getextrema()[0] >= 255:
                        errors.append("Transparent PNG has no transparent pixels.")
            except OSError:
                errors.append("Could not inspect transparency.")
    return tuple(errors)


def _validate_zip(product_dir: Path, package: Path, files: tuple[Path, ...]) -> tuple[str, ...]:
    if package.stat().st_size <= 0:
        return (f"{package.name}: ZIP file is empty.",)
    with zipfile.ZipFile(package) as archive:
        names = {Path(name).name for name in archive.namelist() if not name.endswith("/")}
    expected = {path.name for path in files}
    if not expected.issubset(names):
        return (f"{package.name}: ZIP is missing product files.",)
    if any(name.startswith(".") or name.endswith(".json") for name in names):
        return (f"{package.name}: ZIP contains metadata or temporary files.",)
    return ()


def _dpi_ok(dpi: object, expected: int, tolerance: float = 1.0) -> bool:
    if not isinstance(dpi, tuple) or len(dpi) < 2:
        return False
    try:
        return abs(float(dpi[0]) - expected) <= tolerance and abs(float(dpi[1]) - expected) <= tolerance
    except (TypeError, ValueError):
        return False


def _first_dimensions(files: tuple[Path, ...]) -> tuple[int | None, int | None]:
    if not files:
        return (None, None)
    try:
        with Image.open(files[0]) as image:
            return image.size
    except OSError:
        return (None, None)


def _ratio_label(path: Path) -> str:
    stem = path.stem.casefold().replace("_", "x").replace("-", "x")
    for ratio in ("2:3", "3:4", "4:5", "11x14", "iso"):
        if ratio.replace(":", "x") in stem or ratio in stem:
            return ratio
    return ""


_SPECIFICATIONS: dict[str, MerchantSpecification] = {
    "digital paper": MerchantSpecification(
        category="Digital Paper",
        physical_dimensions="12 x 12 inches",
        pixel_dimensions=(3600, 3600),
        dpi=300,
        file_formats=("JPG",),
        bundle_size=12,
        preview_requirements=("1 collage preview",),
        packaging="ZIP",
        thumbnail_rules=("show palette and pattern variety",),
        etsy_expectations=("scrapbook printable", "commercial quality", "RGB"),
        qa_requirements=("seamless", "no compression artifacts", "consistent palette"),
    ),
    "clipart": MerchantSpecification(
        category="Clipart",
        physical_dimensions="variable transparent PNG assets",
        pixel_dimensions=None,
        dpi=300,
        file_formats=("PNG",),
        bundle_size=20,
        preview_requirements=("grid preview",),
        packaging="ZIP",
        thumbnail_rules=("show all individual elements on grid",),
        etsy_expectations=("transparent PNG", "commercial-use friendly"),
        qa_requirements=("transparent", "individual assets", "commercial quality"),
        transparent=True,
        minimum_longest_edge=4000,
    ),
    "printable wall art": MerchantSpecification(
        category="Printable Wall Art",
        physical_dimensions="multiple print ratios",
        pixel_dimensions=None,
        dpi=300,
        file_formats=("JPG",),
        bundle_size=5,
        preview_requirements=("lifestyle mockup",),
        packaging="ZIP",
        thumbnail_rules=("show finished wall art mockup",),
        etsy_expectations=("multiple ratios", "print-ready JPG"),
        qa_requirements=("correct ratios", "300 DPI", "JPG"),
        required_ratios=("2:3", "3:4", "4:5", "11x14", "ISO"),
    ),
    "stickers": MerchantSpecification(
        category="Stickers",
        physical_dimensions="individual transparent sticker PNGs",
        pixel_dimensions=None,
        dpi=300,
        file_formats=("PNG",),
        bundle_size=8,
        preview_requirements=("sticker sheet preview",),
        packaging="ZIP",
        thumbnail_rules=("show sticker sheet and individual stickers",),
        etsy_expectations=("transparent PNG", "optional Cricut compatibility"),
        qa_requirements=("transparent", "individual stickers", "sheet preview"),
        transparent=True,
    ),
    "party printables": MerchantSpecification(
        category="Party Printables",
        physical_dimensions="8.5 x 11 inches letter size",
        pixel_dimensions=(2550, 3300),
        dpi=300,
        file_formats=("JPG",),
        bundle_size=4,
        preview_requirements=("bundle preview",),
        packaging="ZIP",
        thumbnail_rules=("show printable pages clearly",),
        etsy_expectations=("letter size", "safe zones", "print margins"),
        qa_requirements=("letter size", "300 DPI", "print margins respected"),
    ),
}
