"""Vision-based review system (stub for compatibility)."""
from __future__ import annotations

from typing import Optional
from pathlib import Path

from .providers.base import TranslationProvider


class VisionReviewResult:
    """Result from vision-based review."""
    
    def __init__(
        self,
        quality_score: float,
        issues: list[str],
        suggestions: dict,
        needs_refinement: bool = False,
    ):
        self.quality_score = quality_score
        self.issues = issues
        self.suggestions = suggestions
        self.needs_refinement = needs_refinement


class VisionReviewer:
    """Vision-based review system (minimal implementation)."""
    
    def __init__(
        self,
        provider: TranslationProvider,
        quality_threshold: float = 7.0,
        vision_model: Optional[str] = None,
    ):
        self.provider = provider
        self.quality_threshold = quality_threshold
        self.vision_model = vision_model or getattr(provider, 'model', None)
    
    def analyze_original_slide(
        self, image_path: Path, source_lang: str, target_lang: str, glossary: Optional[dict] = None
    ) -> dict:
        """Analyze original slide (stub)."""
        return {}
    
    def review_translated_slide(
        self,
        original_image_path: Path,
        translated_image_path: Path,
        source_lang: str,
        target_lang: str,
    ) -> VisionReviewResult:
        """Review translated slide (stub - returns default result)."""
        # This is a stub - in full implementation, would call vision API
        return VisionReviewResult(
            quality_score=7.0,
            issues=[],
            suggestions={},
            needs_refinement=False,
        )
