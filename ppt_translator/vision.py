"""Vision-based slide review and quality assessment."""
from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Dict, List, Optional

from .providers.base import TranslationProvider
from .render import render_slide_to_image


def encode_image_to_base64(image_path: Path) -> Optional[str]:
    """Encode image file to base64 string for API."""
    try:
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')
    except Exception:
        return None


class VisionReviewResult:
    """Result from vision-based review."""
    
    def __init__(
        self,
        quality_score: float,
        issues: List[str],
        suggestions: Dict[str, any],
        needs_refinement: bool = False,
    ):
        self.quality_score = quality_score  # 0-10
        self.issues = issues
        self.suggestions = suggestions
        self.needs_refinement = needs_refinement


class VisionReviewer:
    """Review slides using vision-capable LLM."""
    
    def __init__(
        self,
        provider: TranslationProvider,
        quality_threshold: float = 7.0,
        vision_model: Optional[str] = None,
    ):
        """Initialize vision reviewer.
        
        Args:
            provider: Vision-capable translation provider (must support vision)
            quality_threshold: Minimum quality score (0-10) to accept translation
            vision_model: Optional vision model name (default: gpt-5.1)
        """
        self.provider = provider
        self.quality_threshold = quality_threshold
        if not vision_model:
            raise ValueError("vision_model is required for VisionReviewer. Please specify a vision-capable model.")
        self.vision_model = vision_model
    
    def analyze_original_slide(
        self, image_path: Path, source_lang: str, target_lang: str, glossary: Optional[Dict[str, str]] = None
    ) -> Dict[str, any]:
        """Analyze original slide before translation to plan translation strategy.
        
        Uses vision LLM to understand:
        - Text regions and hierarchy (title, body, captions)
        - Layout constraints and spacing
        - Visual context (charts, diagrams, images)
        - Translation priorities
        
        Returns planning information dict.
        """
        if not image_path.exists():
            return {}
        
        image_base64 = encode_image_to_base64(image_path)
        if not image_base64:
            return {}
        
        # Build prompt for pre-translation analysis
        prompt = (
            f"Analyze this PowerPoint slide in {source_lang}. "
            f"I need to translate it to {target_lang}. "
            "Please identify:\n"
            "1. Text hierarchy (titles, subtitles, body text, captions)\n"
            "2. Layout constraints (text box sizes, spacing)\n"
            "3. Visual context (charts, diagrams, images with text)\n"
            "4. Translation priorities (what should be translated first)\n"
            "5. Potential layout issues after translation\n\n"
            "Respond in JSON format with keys: hierarchy, constraints, context, priorities, warnings"
        )
        
        # Call vision API
        try:
            if hasattr(self.provider, 'vision_call'):
                response = self.provider.vision_call(
                    prompt,
                    [str(image_path)],
                    model=self.vision_model
                )
                try:
                    return json.loads(response)
                except json.JSONDecodeError:
                    # If not JSON, return raw response
                    return {"analysis": response}
            else:
                print("Warning: Provider does not support vision calls")
                return {}
        except Exception as e:
            print(f"Warning: Vision analysis failed: {e}")
            return {}
    
    def review_translated_slide(
        self,
        original_image_path: Path,
        translated_image_path: Path,
        source_lang: str,
        target_lang: str,
    ) -> VisionReviewResult:
        """Review translated slide and provide quality assessment.
        
        Compares original and translated slides visually to assess:
        - Translation quality and accuracy
        - Layout preservation
        - Text overflow issues
        - Readability
        
        Returns:
            VisionReviewResult with quality score, issues, and suggestions
        """
        if not original_image_path.exists() or not translated_image_path.exists():
            return VisionReviewResult(
                quality_score=5.0,
                issues=["Could not load slide images for review"],
                suggestions={},
                needs_refinement=True,
            )
        
        original_base64 = encode_image_to_base64(original_image_path)
        translated_base64 = encode_image_to_base64(translated_image_path)
        
        if not original_base64 or not translated_base64:
            return VisionReviewResult(
                quality_score=5.0,
                issues=["Could not encode images for review"],
                suggestions={},
                needs_refinement=True,
            )
        
        # Build prompt for quality review
        prompt = (
            f"Review this translation from {source_lang} to {target_lang}. "
            "Compare the original slide (first image) with the translated slide (second image).\n\n"
            "Assess:\n"
            "1. Translation quality (accuracy, naturalness) - score 0-10\n"
            "2. Layout preservation (text fits, no overflow)\n"
            "3. Visual consistency (formatting, spacing)\n"
            "4. Issues found (list specific problems)\n"
            "5. Suggestions for improvement\n\n"
            "Respond in JSON format:\n"
            '{"quality_score": 0-10, "issues": ["issue1", "issue2"], '
            '"suggestions": {"font_size": 10.5, "line_spacing": 1.2}, "needs_refinement": true/false}'
        )
        
        # Call vision API
        try:
            if hasattr(self.provider, 'vision_call'):
                response = self.provider.vision_call(
                    prompt,
                    [str(original_image_path), str(translated_image_path)],
                    model=self.vision_model
                )
                try:
                    result_data = json.loads(response)
                    return VisionReviewResult(
                        quality_score=result_data.get("quality_score", 5.0),
                        issues=result_data.get("issues", []),
                        suggestions=result_data.get("suggestions", {}),
                        needs_refinement=result_data.get("needs_refinement", True),
                    )
                except json.JSONDecodeError:
                    # If not JSON, try to extract score from text
                    quality_score = 8.0
                    if "quality_score" in response.lower():
                        # Try to extract number
                        import re
                        match = re.search(r'quality[_\s]*score[:\s]*(\d+\.?\d*)', response.lower())
                        if match:
                            quality_score = float(match.group(1))
                    return VisionReviewResult(
                        quality_score=quality_score,
                        issues=["Could not parse review response"],
                        suggestions={},
                        needs_refinement=quality_score < self.quality_threshold,
                    )
            else:
                print("Warning: Provider does not support vision calls")
                return VisionReviewResult(
                    quality_score=5.0,
                    issues=["Provider does not support vision"],
                    suggestions={},
                    needs_refinement=True,
                )
        except Exception as e:
            print(f"Warning: Vision review failed: {e}")
            return VisionReviewResult(
                quality_score=5.0,
                issues=[f"Review error: {str(e)}"],
                suggestions={},
                needs_refinement=True,
            )

