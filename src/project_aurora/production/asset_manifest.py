"""Job-scoped asset manifest utilities for Product Factory outputs."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class AssetManifestEntry:
    """Ownership record for one generated or final product asset."""

    job_id: str
    product_slug: str
    source_stage: str
    path: str
    filename: str
    checksum: str
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe manifest entry."""
        return {
            "job_id": self.job_id,
            "product_slug": self.product_slug,
            "source_stage": self.source_stage,
            "path": self.path,
            "filename": self.filename,
            "checksum": self.checksum,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AssetManifestEntry":
        """Build an entry from stored JSON."""
        created_at = data.get("created_at")
        return cls(
            job_id=str(data.get("job_id", "")),
            product_slug=str(data.get("product_slug", "")),
            source_stage=str(data.get("source_stage", "")),
            path=str(data.get("path", "")),
            filename=str(data.get("filename", "")),
            checksum=str(data.get("checksum", "")),
            created_at=(
                datetime.fromisoformat(str(created_at))
                if created_at
                else datetime.now()
            ),
        )


@dataclass(frozen=True, slots=True)
class AssetOwnershipDiagnostic:
    """One manifest ownership validation line."""

    active_job_id: str
    active_product_slug: str
    workspace: str
    asset_owner_job_id: str
    asset_owner_product_slug: str
    filename: str
    validation_result: str

    def to_dict(self) -> dict[str, str]:
        """Return a JSON-safe diagnostic."""
        return {
            "active_job_id": self.active_job_id,
            "active_product_slug": self.active_product_slug,
            "workspace": self.workspace,
            "asset_owner_job_id": self.asset_owner_job_id,
            "asset_owner_product_slug": self.asset_owner_product_slug,
            "filename": self.filename,
            "validation_result": self.validation_result,
        }


@dataclass(frozen=True, slots=True)
class AssetOwnershipResult:
    """Result of checking files against a job manifest."""

    passed: bool
    diagnostics: tuple[AssetOwnershipDiagnostic, ...]
    errors: tuple[str, ...] = field(default_factory=tuple)


def product_slug(value: str) -> str:
    """Return Aurora's normalized product slug."""
    slug = re.sub(r"[^a-z0-9]+", "_", value.casefold()).strip("_")
    return slug[:80]


def job_slug(value: str) -> str:
    """Return a short filesystem-safe job slug."""
    slug = re.sub(r"[^a-z0-9]+", "_", value.casefold()).strip("_")
    return slug[:80]


def manifest_path_for(job_root: Path) -> Path:
    """Return the manifest path for a job workspace."""
    return job_root / "asset_manifest.json"


def checksum_file(path: Path) -> str:
    """Return a SHA-256 checksum for a file."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_asset_manifest(path: Path) -> tuple[AssetManifestEntry, ...]:
    """Load a manifest if present."""
    if not path.exists():
        return ()
    data = json.loads(path.read_text(encoding="utf-8"))
    entries = data.get("assets", data)
    if not isinstance(entries, list):
        return ()
    return tuple(
        AssetManifestEntry.from_dict(item)
        for item in entries
        if isinstance(item, dict)
    )


def write_asset_manifest(
    *,
    manifest_path: Path,
    job_id: str,
    product_name: str,
    files: tuple[Path, ...],
    source_stage: str,
    append: bool = True,
) -> tuple[AssetManifestEntry, ...]:
    """Write or append ownership records for asset files."""
    existing = list(load_asset_manifest(manifest_path)) if append else []
    product = product_slug(product_name)
    replacement_keys = {(source_stage, file_path.name) for file_path in files}
    retained = [
        entry
        for entry in existing
        if (entry.source_stage, entry.filename) not in replacement_keys
    ]
    new_entries = [
        AssetManifestEntry(
            job_id=job_id,
            product_slug=product,
            source_stage=source_stage,
            path=str(file_path),
            filename=file_path.name,
            checksum=checksum_file(file_path),
        )
        for file_path in files
    ]
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    records = (*retained, *new_entries)
    manifest_path.write_text(
        json.dumps({"assets": [entry.to_dict() for entry in records]}, indent=2),
        encoding="utf-8",
    )
    return tuple(new_entries)


def validate_asset_ownership(
    *,
    manifest_path: Path,
    job_id: str,
    product_name: str,
    workspace: Path,
    files: tuple[Path, ...],
    source_stage: str | None = None,
) -> AssetOwnershipResult:
    """Validate that files belong to the active job manifest."""
    entries = load_asset_manifest(manifest_path)
    by_name = {entry.filename: entry for entry in entries}
    active_slug = product_slug(product_name)
    diagnostics: list[AssetOwnershipDiagnostic] = []
    errors: list[str] = []
    for file_path in files:
        entry = by_name.get(file_path.name)
        owner_job = entry.job_id if entry else "UNKNOWN"
        owner_slug = entry.product_slug if entry else "UNKNOWN"
        result = "PASS"
        if entry is None:
            result = "FAIL"
            errors.append(f"STALE_OR_MISMATCHED_ASSET: {file_path.name} is missing manifest ownership")
        elif entry.job_id != job_id or entry.product_slug != active_slug:
            result = "FAIL"
            errors.append(
                "STALE_OR_MISMATCHED_ASSET: "
                f"{file_path.name} belongs to job {entry.job_id} / {entry.product_slug}"
            )
        elif source_stage and entry.source_stage != source_stage:
            result = "FAIL"
            errors.append(
                "STALE_OR_MISMATCHED_ASSET: "
                f"{file_path.name} is from {entry.source_stage}, expected {source_stage}"
            )
        elif checksum_file(file_path) != entry.checksum:
            result = "FAIL"
            errors.append(f"STALE_OR_MISMATCHED_ASSET: {file_path.name} checksum changed")
        diagnostics.append(
            AssetOwnershipDiagnostic(
                active_job_id=job_id,
                active_product_slug=active_slug,
                workspace=str(workspace),
                asset_owner_job_id=owner_job,
                asset_owner_product_slug=owner_slug,
                filename=file_path.name,
                validation_result=result,
            )
        )
    return AssetOwnershipResult(
        passed=not errors,
        diagnostics=tuple(diagnostics),
        errors=tuple(errors),
    )
