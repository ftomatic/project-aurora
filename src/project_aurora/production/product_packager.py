"""Build merchant-required customer packages for final product assets."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from project_aurora.production.merchant_specification import (
    MerchantSpecificationLibrary,
)


ETSY_MAX_DIGITAL_PACKAGE_SIZE_BYTES = 20 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class ProductPackageResult:
    """Result of creating a customer product package."""

    status: str
    package_files: tuple[str, ...] = field(default_factory=tuple)
    errors: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(self, "status", self.status.strip().upper())
        object.__setattr__(self, "package_files", tuple(self.package_files))
        object.__setattr__(self, "errors", tuple(self.errors))


class ProductPackager:
    """Create package files required by the merchant specification."""

    def package(
        self,
        *,
        product_name: str,
        category: str,
        product_dir: Path,
    ) -> ProductPackageResult:
        """Create required package files for a product directory."""
        spec = MerchantSpecificationLibrary().resolve(category, product_name)
        if spec.packaging != "ZIP":
            return ProductPackageResult(status="SKIPPED")
        files = _asset_files(product_dir, spec.file_formats)
        errors: list[str] = []
        if len(files) < spec.bundle_size:
            errors.append(
                f"{spec.category} requires at least {spec.bundle_size} "
                f"{'/'.join(spec.file_formats)} files before ZIP packaging, "
                f"found {len(files)}."
            )
        if errors:
            return ProductPackageResult(status="FAILED", errors=tuple(errors))
        zip_path = product_dir / f"{_slug(product_name)}.zip"
        with ZipFile(zip_path, "w", compression=ZIP_DEFLATED) as archive:
            for file_path in files:
                archive.write(file_path, arcname=file_path.name)
        validation_errors = _validate_zip(zip_path, files)
        return ProductPackageResult(
            status="FAILED" if validation_errors else "SUCCESS",
            package_files=(str(zip_path),) if zip_path.exists() else (),
            errors=validation_errors,
        )


def _asset_files(product_dir: Path, formats: tuple[str, ...]) -> tuple[Path, ...]:
    suffixes = {f".{fmt.casefold()}" for fmt in formats}
    return tuple(
        path
        for path in sorted(product_dir.glob("*"), key=lambda item: item.name)
        if path.is_file()
        and path.suffix.casefold() in suffixes
        and "preview" not in path.stem.casefold()
    )


def _validate_zip(zip_path: Path, files: tuple[Path, ...]) -> tuple[str, ...]:
    errors: list[str] = []
    if not zip_path.exists():
        return (f"ZIP does not exist: {zip_path}",)
    if zip_path.stat().st_size <= 0:
        errors.append("ZIP file is empty.")
    if zip_path.stat().st_size >= ETSY_MAX_DIGITAL_PACKAGE_SIZE_BYTES:
        errors.append(
            f"{zip_path.name}: ZIP package exceeds Etsy's 20 MB digital file limit."
        )
    try:
        with ZipFile(zip_path, "r") as archive:
            names = [Path(name).name for name in archive.namelist() if not name.endswith("/")]
    except OSError as error:
        return (f"ZIP is invalid: {error}",)
    expected = {path.name for path in files}
    if set(names) != expected:
        errors.append("ZIP must contain exactly the final customer asset files.")
    if any(name.startswith(".") or name.endswith(".json") for name in names):
        errors.append("ZIP must not contain metadata or hidden files.")
    return tuple(errors)


def _slug(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "_", value.strip()).strip("_")
    return cleaned or "aurora_product"
