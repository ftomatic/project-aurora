"""Thumbnail pattern analyzer placeholder."""

from __future__ import annotations

from project_aurora.etsy_intelligence.intelligence_models import EvidenceRecord


class ThumbnailPatternAnalyzer:
    """Analyze only approved/published thumbnail patterns when available."""

    def analyze(self) -> EvidenceRecord:
        return EvidenceRecord(
            source="AURORA_APPROVED_THUMBNAILS",
            observed_at="",
            summary="No approved thumbnail performance threshold configured yet.",
            sample_size=0,
            confidence=0,
        )
