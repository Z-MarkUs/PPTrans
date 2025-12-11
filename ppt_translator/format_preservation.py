"""Format preservation utilities for maintaining PPT structure during translation."""
from __future__ import annotations

from typing import List, Dict, Tuple
from pptx.enum.text import PP_ALIGN


class ParagraphFormatPreserver:
    """Preserve and restore paragraph formatting across translation."""
    
    @staticmethod
    def extract_paragraph_metadata(paragraph) -> Dict:
        """Extract metadata from a paragraph including bullet level and spacing."""
        return {
            "level": paragraph.level,
            "alignment": f"PP_ALIGN.{paragraph.alignment}" if paragraph.alignment else None,
            "line_spacing": paragraph.line_spacing,
            "space_before": paragraph.space_before,
            "space_after": paragraph.space_after,
        }
    
    @staticmethod
    def extract_run_metadata(run) -> Dict:
        """Extract formatting from a text run (bold, italic, color, font)."""
        return {
            "font_size": run.font.size.pt if getattr(run.font, "size", None) is not None else None,
            "font_name": getattr(run.font, "name", None),
            "bold": run.font.bold,
            "italic": run.font.italic,
            "font_color": str(run.font.color.rgb) if (
                getattr(run.font, "color", None) is not None
                and getattr(run.font.color, "rgb", None) is not None
            ) else None,
        }
    
    @staticmethod
    def detect_bullet_level(paragraph) -> int:
        """Return the indentation level for bullet points."""
        return paragraph.level


class TextStructureAnalyzer:
    """Analyze text structure to identify bullet points and lists."""
    
    @staticmethod
    def is_bulleted_text(shape) -> bool:
        """Check if a shape contains bullet points."""
        if not hasattr(shape, "text_frame"):
            return False
        
        for paragraph in shape.text_frame.paragraphs:
            if paragraph.level > 0 or hasattr(paragraph, "_element"):
                # Check for bullet formatting
                pPr = paragraph._element.pPr
                if pPr is not None:
                    buFont = pPr.find(".//{http://schemas.openxmlformats.org/drawingml/2006/main}buFont")
                    if buFont is not None:
                        return True
        return False
    
    @staticmethod
    def split_into_logical_units(text: str) -> List[str]:
        """Split text into logical units (paragraphs, bullet points)."""
        units = []
        current_unit = []
        
        for line in text.split('\n'):
            if line.strip():
                current_unit.append(line)
            else:
                if current_unit:
                    units.append('\n'.join(current_unit))
                    current_unit = []
        
        if current_unit:
            units.append('\n'.join(current_unit))
        
        return units


class FontSizeOptimizer:
    """Smart font size handling to prevent aggressive scaling."""
    
    # Standard font size presets for different contexts
    PRESET_SIZES = {
        "title": 44.0,
        "subtitle": 32.0,
        "heading": 28.0,
        "body": 14.0,
        "small": 11.0,
        "caption": 8.0,
    }
    
    @staticmethod
    def detect_context(shape, shape_index: int) -> str:
        """Detect the context (title, body, caption, etc.) based on position and size."""
        # Shape index 0 and 1 are typically title/subtitle
        if shape_index == 0:
            return "title"
        elif shape_index == 1:
            return "subtitle"
        
        # Check font size to infer context
        if hasattr(shape, "text_frame"):
            for paragraph in shape.text_frame.paragraphs:
                if paragraph.runs:
                    font_size = paragraph.runs[0].font.size
                    if font_size:
                        pt_size = font_size.pt
                        if pt_size > 32:
                            return "heading"
                        elif pt_size < 12:
                            return "caption"
        
        return "body"
    
    @staticmethod
    def preserve_font_scale(original_font_size: float, context: str) -> float:
        """Preserve original font size with minimal scaling for translation context.
        
        Returns the recommended font size after translation.
        """
        # For most cases, preserve original size
        # Only apply small adjustment if clearly needed
        if context == "body":
            # Body text: preserve exactly
            return original_font_size
        elif context in ["title", "heading"]:
            # Headers: preserve exactly to maintain visual hierarchy
            return original_font_size
        else:
            # Small text: may need slight increase for readability
            # but preserve overall intent
            return original_font_size
    
    @staticmethod
    def calculate_optimal_size(text: str, original_size: float, available_width: float, available_height: float) -> float:
        """Calculate optimal font size that fits in available space without aggressive downsizing.
        
        Args:
            text: The text to fit
            original_size: Original font size in points
            available_width: Available width in EMU
            available_height: Available height in EMU
        
        Returns:
            Recommended font size, preferring original size when possible
        """
        # Convert available space to approximate characters
        # Rough estimate: 1pt ≈ 12700 EMU, char width ≈ 0.6 * font_size
        
        char_width_emu = original_size * 0.6 * 12700
        line_height_emu = original_size * 1.2 * 12700
        
        chars_per_line = max(1, int(available_width / char_width_emu))
        max_lines = max(1, int(available_height / line_height_emu))
        
        # Calculate required lines for text
        required_lines = max(1, (len(text) + chars_per_line - 1) // chars_per_line)
        
        if required_lines <= max_lines:
            # Text fits - preserve original size
            return original_size
        else:
            # Calculate scaling needed
            scale = max_lines / required_lines
            new_size = original_size * scale * 0.95  # 5% margin
            
            # Don't go below minimum readable size
            return max(8.0, new_size)


class ListFormatPreserver:
    """Utilities for preserving list and bullet formatting."""
    
    @staticmethod
    def preserve_list_structure(paragraphs: List) -> List[Dict]:
        """Extract and preserve list structure from paragraphs."""
        list_structure = []
        
        for para in paragraphs:
            item = {
                "level": para.level,
                "text": para.text,
                "has_bullets": False,
            }
            
            # Check for bullet formatting
            pPr = para._element.pPr
            if pPr is not None:
                buNone = pPr.find(".//{http://schemas.openxmlformats.org/drawingml/2006/main}buNone")
                if buNone is None:
                    # Has bullets/numbering
                    item["has_bullets"] = True
            
            list_structure.append(item)
        
        return list_structure
    
    @staticmethod
    def restore_list_structure(shape, structure: List[Dict]) -> None:
        """Restore list structure to a shape's text frame."""
        text_frame = shape.text_frame
        
        # Clear existing paragraphs except first
        while len(text_frame.paragraphs) > 1:
            p = text_frame.paragraphs[-1]._element
            p.getparent().remove(p)
        
        # Restore paragraphs
        for idx, item in enumerate(structure):
            if idx == 0:
                para = text_frame.paragraphs[0]
            else:
                para = text_frame.add_paragraph()
            
            para.text = item["text"]
            para.level = item["level"]
