"""Interactive review file generation and regeneration from edits."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict
from datetime import datetime

try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False


@dataclass
class SlideTranslation:
    """Translation data for a single slide."""
    slide_number: int
    original_texts: List[Dict[str, any]]  # List of text elements with shape_index
    translated_texts: List[Dict[str, any]]  # List of translated texts (editable)
    quality_score: Optional[float] = None
    issues: List[str] = None
    suggestions: Dict[str, any] = None
    
    def __post_init__(self):
        if self.issues is None:
            self.issues = []
        if self.suggestions is None:
            self.suggestions = {}


@dataclass
class FileReview:
    """Review data for a single PPT file."""
    file_path: str
    slides: List[SlideTranslation]
    total_slides: int
    average_quality_score: Optional[float] = None
    total_issues: int = 0
    
    def calculate_stats(self):
        """Calculate statistics for this file."""
        if not self.slides:
            return
        
        scores = [s.quality_score for s in self.slides if s.quality_score is not None]
        if scores:
            self.average_quality_score = sum(scores) / len(scores)
        
        self.total_issues = sum(len(s.issues) for s in self.slides)


@dataclass
class ReviewData:
    """Complete review data structure."""
    version: str = "1.0"
    created_at: str = None
    source_lang: str = ""
    target_lang: str = ""
    files: List[FileReview] = None
    total_files: int = 0
    total_slides: int = 0
    overall_average_quality: Optional[float] = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now().isoformat()
        if self.files is None:
            self.files = []
    
    def calculate_stats(self):
        """Calculate overall statistics."""
        self.total_files = len(self.files)
        self.total_slides = sum(f.total_slides for f in self.files)
        
        all_scores = []
        for file_review in self.files:
            file_review.calculate_stats()
            if file_review.average_quality_score is not None:
                all_scores.append(file_review.average_quality_score)
        
        if all_scores:
            self.overall_average_quality = sum(all_scores) / len(all_scores)


class ReviewFileGenerator:
    """Generate interactive review files."""
    
    def __init__(self, source_lang: str, target_lang: str):
        """Initialize review file generator."""
        self.source_lang = source_lang
        self.target_lang = target_lang
        self.review_data = ReviewData(
            source_lang=source_lang,
            target_lang=target_lang
        )
    
    def add_file_review(
        self,
        file_path: str,
        slides: List[SlideTranslation],
        quality_scores: Optional[List[float]] = None,
        issues: Optional[List[List[str]]] = None,
    ):
        """Add review data for a file."""
        file_review = FileReview(
            file_path=file_path,
            slides=slides,
            total_slides=len(slides)
        )
        
        # Attach quality scores and issues if provided
        if quality_scores:
            for slide, score in zip(file_review.slides, quality_scores):
                slide.quality_score = score
        
        if issues:
            for slide, slide_issues in zip(file_review.slides, issues):
                slide.issues = slide_issues
        
        self.review_data.files.append(file_review)
    
    def save(self, output_path: Path, format: str = "json") -> None:
        """Save review file in specified format."""
        self.review_data.calculate_stats()
        
        # Convert to dict for serialization
        data_dict = self._to_dict(self.review_data)
        
        if format.lower() == "yaml" or format.lower() == "yml":
            if not YAML_AVAILABLE:
                raise ValueError("YAML format requires PyYAML. Install with: pip install pyyaml")
            with open(output_path, "w", encoding="utf-8") as f:
                yaml.dump(data_dict, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
        else:
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(data_dict, f, ensure_ascii=False, indent=2)
    
    def _to_dict(self, obj):
        """Convert dataclass to dict recursively."""
        if hasattr(obj, '__dataclass_fields__'):
            return {k: self._to_dict(v) for k, v in asdict(obj).items()}
        elif isinstance(obj, list):
            return [self._to_dict(item) for item in obj]
        elif isinstance(obj, dict):
            return {k: self._to_dict(v) for k, v in obj.items()}
        else:
            return obj


class ReviewFileLoader:
    """Load and validate edited review files."""
    
    @staticmethod
    def load(review_file_path: Path) -> ReviewData:
        """Load review file and return ReviewData object."""
        if not review_file_path.exists():
            raise FileNotFoundError(f"Review file not found: {review_file_path}")
        
        with open(review_file_path, "r", encoding="utf-8") as f:
            if review_file_path.suffix.lower() in {".yaml", ".yml"}:
                if not YAML_AVAILABLE:
                    raise ValueError("YAML format requires PyYAML. Install with: pip install pyyaml")
                data = yaml.safe_load(f)
            else:
                data = json.load(f)
        
        return ReviewFileLoader._from_dict(data)
    
    @staticmethod
    def _from_dict(data: dict) -> ReviewData:
        """Convert dict to ReviewData object."""
        review_data = ReviewData(
            version=data.get("version", "1.0"),
            created_at=data.get("created_at"),
            source_lang=data.get("source_lang", ""),
            target_lang=data.get("target_lang", ""),
        )
        
        for file_data in data.get("files", []):
            file_review = FileReview(
                file_path=file_data["file_path"],
                slides=[],
                total_slides=file_data.get("total_slides", 0),
                average_quality_score=file_data.get("average_quality_score"),
                total_issues=file_data.get("total_issues", 0),
            )
            
            for slide_data in file_data.get("slides", []):
                slide = SlideTranslation(
                    slide_number=slide_data["slide_number"],
                    original_texts=slide_data.get("original_texts", []),
                    translated_texts=slide_data.get("translated_texts", []),
                    quality_score=slide_data.get("quality_score"),
                    issues=slide_data.get("issues", []),
                    suggestions=slide_data.get("suggestions", {}),
                )
                file_review.slides.append(slide)
            
            review_data.files.append(file_review)
        
        review_data.calculate_stats()
        return review_data
    
    @staticmethod
    def validate(review_data: ReviewData) -> tuple[bool, List[str]]:
        """Validate review file structure and completeness.
        
        Returns:
            (is_valid, list_of_errors)
        """
        errors = []
        
        if not review_data.files:
            errors.append("No files found in review data")
        
        for file_idx, file_review in enumerate(review_data.files):
            if not file_review.file_path:
                errors.append(f"File {file_idx + 1}: Missing file_path")
            
            if file_review.total_slides != len(file_review.slides):
                errors.append(
                    f"File {file_idx + 1}: Slide count mismatch "
                    f"(expected {file_review.total_slides}, found {len(file_review.slides)})"
                )
            
            for slide_idx, slide in enumerate(file_review.slides):
                if slide.slide_number < 1:
                    errors.append(
                        f"File {file_idx + 1}, Slide {slide_idx + 1}: Invalid slide_number"
                    )
                
                if len(slide.original_texts) != len(slide.translated_texts):
                    errors.append(
                        f"File {file_idx + 1}, Slide {slide.slide_number}: "
                        f"Translation count mismatch "
                        f"(original: {len(slide.original_texts)}, "
                        f"translated: {len(slide.translated_texts)})"
                    )
                
                # Check that each translation has required fields
                for trans_idx, (orig, trans) in enumerate(zip(slide.original_texts, slide.translated_texts)):
                    if "text" not in orig:
                        errors.append(
                            f"File {file_idx + 1}, Slide {slide.slide_number}, "
                            f"Translation {trans_idx + 1}: Missing original text"
                        )
                    if "text" not in trans:
                        errors.append(
                            f"File {file_idx + 1}, Slide {slide.slide_number}, "
                            f"Translation {trans_idx + 1}: Missing translated text"
                        )
        
        return len(errors) == 0, errors

