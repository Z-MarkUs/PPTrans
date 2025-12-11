"""PowerPoint translation pipeline utilities."""
from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional, List
from xml.dom import minidom

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE_TYPE
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.util import Inches, Pt

from .translation import TranslationService
from .vision import VisionReviewer
from .render import render_slide_to_image
from .review import ReviewFileGenerator, ReviewFileLoader, SlideTranslation


def _apply_translation_to_paragraphs(paragraphs: list, original_text: str, translated_text: str) -> None:
    """Apply translated full text to paragraph structure without re-translating.
    
    This is a best-effort approach to distribute the full translation across paragraphs/runs.
    """
    try:
        if not paragraphs or not translated_text:
            return
        
        # Simple approach: split translated text by newlines
        # and match with paragraphs
        translated_lines = translated_text.split('\n')
        trans_line_idx = 0
        has_translation = False
        
        for para_idx, para in enumerate(paragraphs):
            # Get the next available translated line(s)
            if trans_line_idx >= len(translated_lines):
                break
            
            # Get translated text for this paragraph
            para_trans_text = translated_lines[trans_line_idx].strip() if trans_line_idx < len(translated_lines) else ""
            
            # Update paragraph text
            if para_trans_text:
                para["text"] = para_trans_text
                has_translation = True
            trans_line_idx += 1
            
            # Apply translation to runs within this paragraph
            runs = para.get("runs", [])
            if runs and para_trans_text:
                # If we have multiple runs, split the translated text across them
                # Simple strategy: give each run a portion of the translated text
                run_count = len(runs)
                
                if run_count == 1:
                    # Single run: give it all the translated text
                    runs[0]["text"] = para_trans_text
                else:
                    # Multiple runs: try to split based on original proportions
                    orig_run_lengths = []
                    total_orig_len = 0
                    
                    for run in runs:
                        run_len = len(run.get("text", ""))
                        orig_run_lengths.append(run_len)
                        total_orig_len += run_len
                    
                    if total_orig_len > 0:
                        # Distribute translated text proportionally
                        trans_pos = 0
                        for run_idx, run in enumerate(runs):
                            # Calculate this run's proportion
                            run_proportion = orig_run_lengths[run_idx] / total_orig_len
                            
                            # Calculate how much translated text this run should get
                            if run_idx == len(runs) - 1:
                                # Last run gets everything remaining
                                run_trans_text = para_trans_text[trans_pos:]
                            else:
                                run_trans_len = max(1, int(len(para_trans_text) * run_proportion))
                                run_trans_text = para_trans_text[trans_pos:trans_pos + run_trans_len]
                                trans_pos += run_trans_len
                            
                            run["text"] = run_trans_text.strip()
                            if run["text"]:
                                has_translation = True
                    else:
                        # No original text in runs, distribute equally
                        chars_per_run = len(para_trans_text) // run_count if run_count > 0 else 0
                        for run_idx, run in enumerate(runs):
                            if run_idx == len(runs) - 1:
                                # Last run gets remainder
                                run["text"] = para_trans_text[run_idx * chars_per_run:]
                            else:
                                run["text"] = para_trans_text[run_idx * chars_per_run:(run_idx + 1) * chars_per_run]
                            if run["text"]:
                                has_translation = True
        
        # Fallback: if translation wasn't distributed, put entire translated text in first paragraph
        if not has_translation and paragraphs:
            paragraphs[0]["text"] = translated_text
            if paragraphs[0].get("runs"):
                paragraphs[0]["runs"][0]["text"] = translated_text
    
    except Exception as e:
        # If mapping fails, fallback: put translation in first paragraph
        if paragraphs:
            paragraphs[0]["text"] = translated_text
            if paragraphs[0].get("runs"):
                paragraphs[0]["runs"][0]["text"] = translated_text
        print(f"Warning: Error distributing translation to paragraphs: {e}")



def get_alignment_value(alignment_str: str | None):
    """Convert alignment string to PP_ALIGN enum value."""
    alignment_map = {
        "PP_ALIGN.CENTER": PP_ALIGN.CENTER,
        "PP_ALIGN.LEFT": PP_ALIGN.LEFT,
        "PP_ALIGN.RIGHT": PP_ALIGN.RIGHT,
        "PP_ALIGN.JUSTIFY": PP_ALIGN.JUSTIFY,
        "None": None,
        None: None,
    }
    return alignment_map.get(alignment_str)


def get_shape_properties(shape):
    """Extract text shape properties, preserving paragraph and bullet formatting."""
    shape_data = {
        "text": "",
        "paragraphs": [],  # NEW: Store per-paragraph data with formatting
        "font_size": None,
        "font_name": None,
        "alignment": None,
        "width": shape.width,  # Track original box width
        "height": shape.height,  # Track original box height
        "left": shape.left,
        "top": shape.top,
        "bold": None,
        "italic": None,
        "line_spacing": None,
        "space_before": None,
        "space_after": None,
        "font_color": None,
        "is_subtitle": False,  # Detect if this is a subtitle (should not have bullets)
    }
    if hasattr(shape, "text"):
        shape_data["text"] = shape.text.strip()
        if hasattr(shape, "text_frame"):
            # NEW: Extract per-paragraph data with bullet information
            for para_idx, paragraph in enumerate(shape.text_frame.paragraphs):
                para_data = {
                    "text": paragraph.text,
                    "level": paragraph.level,  # Indentation level for bullets
                    "alignment": f"PP_ALIGN.{paragraph.alignment}" if paragraph.alignment else None,
                    "line_spacing": paragraph.line_spacing,
                    "space_before": paragraph.space_before,
                    "space_after": paragraph.space_after,
                    "runs": [],  # Store run-level formatting
                }
                
                # Extract run-level formatting (font, bold, italic, color)
                for run in paragraph.runs:
                    run_data = {
                        "text": run.text,
                        "font_size": run.font.size.pt if getattr(run.font, "size", None) is not None else None,
                        "font_name": getattr(run.font, "name", None),
                        "bold": run.font.bold,
                        "italic": run.font.italic,
                        "font_color": str(run.font.color.rgb) if (
                            getattr(run.font, "color", None) is not None
                            and getattr(run.font.color, "rgb", None) is not None
                        ) else None,
                    }
                    para_data["runs"].append(run_data)
                
                # Detect subtitle: typically short, high font size, no bullets
                is_subtitle_candidate = (
                    paragraph.level == 0 and
                    len(paragraph.text) < 100 and
                    shape_data.get("font_size", 0) and shape_data.get("font_size", 0) > 16
                )
                if para_idx == 1 and is_subtitle_candidate:
                    shape_data["is_subtitle"] = True
                
                shape_data["paragraphs"].append(para_data)
                
                # Set default from first paragraph (for backward compatibility)
                if para_idx == 0 and paragraph.runs:
                    run = paragraph.runs[0]
                    if getattr(run.font, "size", None) is not None:
                        shape_data["font_size"] = run.font.size.pt
                    if getattr(run.font, "name", None):
                        shape_data["font_name"] = run.font.name
                    if hasattr(run.font, "bold"):
                        shape_data["bold"] = run.font.bold
                    if hasattr(run.font, "italic"):
                        shape_data["italic"] = run.font.italic
                    if (
                        getattr(run.font, "color", None) is not None
                        and getattr(run.font.color, "rgb", None) is not None
                    ):
                        shape_data["font_color"] = str(run.font.color.rgb)
    return shape_data


def estimate_text_dimensions(text: str, font_size_pt: float, font_name: str = "Arial", width_emu: int = None) -> tuple[float, float]:
    """Estimate text dimensions in EMU (English Metric Units).
    
    Returns (estimated_width, estimated_height) in EMU.
    This is a rough estimation - actual rendering may vary.
    Accounts for word wrapping and multiple lines.
    Conservative to prevent overflow.
    """
    # Safety check: ensure font_size_pt is valid
    if font_size_pt is None or font_size_pt <= 0:
        font_size_pt = 12.0
    
    # Approximate character width: font_size * 0.6 (for most fonts)
    # Approximate line height: font_size * 1.2
    char_width_emu = font_size_pt * 0.6 * 12700  # Convert pt to EMU (1pt = 12700 EMU)
    line_height_emu = font_size_pt * 1.2 * 12700
    
    if width_emu:
        # Calculate how many characters fit per line
        chars_per_line = max(1, int(width_emu / char_width_emu))
        
        # Split text into lines (account for newlines in original text)
        text_lines = text.split('\n')
        total_lines = 0
        for line in text_lines:
            # Each original line may wrap into multiple display lines
            line_count = max(1, (len(line) + chars_per_line - 1) // chars_per_line)
            total_lines += line_count
        
        # Add extra line for paragraph spacing (conservative estimate)
        if len(text_lines) > 1:
            total_lines += len(text_lines) - 1  # Account for spacing between paragraphs
        
        # Add safety margin (10% extra height for padding/margins)
        estimated_width = width_emu  # Text fills width when wrapped
        estimated_height = int(total_lines * line_height_emu * 1.1)
    else:
        # No width constraint, estimate single line
        estimated_width = len(text) * char_width_emu
        estimated_height = int(line_height_emu * 1.1)
    
    return (estimated_width, estimated_height)


def check_text_fits(text: str, font_size_pt: float, box_width_emu: int, box_height_emu: int, font_name: str = "Arial") -> tuple[bool, float]:
    """Check if text fits in the given box dimensions.
    
    Returns (fits, suggested_font_size).
    If text doesn't fit, suggests a smaller font size.
    Conservative to prevent any overflow.
    """
    # Safety check: ensure font_size_pt is valid
    if font_size_pt is None or font_size_pt <= 0:
        font_size_pt = 12.0
    
    estimated_width, estimated_height = estimate_text_dimensions(text, font_size_pt, font_name, box_width_emu)
    
    # Check with a small safety margin (95% of available space)
    fits = estimated_width <= box_width_emu * 0.98 and estimated_height <= box_height_emu * 0.98
    
    if not fits:
        # Calculate scale factor needed - be conservative
        width_scale = (box_width_emu * 0.98) / estimated_width if estimated_width > 0 else 1.0
        height_scale = (box_height_emu * 0.98) / estimated_height if estimated_height > 0 else 1.0
        scale_factor = min(width_scale, height_scale, 1.0)  # Don't scale up
        
        # Suggest new font size (with extra margin for safety)
        suggested_size = font_size_pt * scale_factor * 0.9  # 10% safety margin
        suggested_size = max(6.0, suggested_size)  # Minimum 6pt
    else:
        suggested_size = font_size_pt
    
    return (fits, suggested_size)


def find_largest_fitting_font(text: str, original_font_size: float, box_width_emu: int, box_height_emu: int, font_name: str = "Arial") -> float:
    """Find the largest font size that fits the text without overflow.
    
    Uses binary search to efficiently find the maximum font size that keeps
    text within bounds while trying to stay as close to original as possible.
    """
    # Safety check: ensure original_font_size is valid
    if original_font_size is None or original_font_size <= 0:
        original_font_size = 12.0
    
    if not text or not text.strip():
        return original_font_size
    
    # Check if original size already fits
    fits, _ = check_text_fits(text, original_font_size, box_width_emu, box_height_emu, font_name)
    if fits:
        return original_font_size
    
    # Binary search for largest fitting size
    min_size = 6.0  # Minimum readable font
    max_size = original_font_size
    best_size = min_size
    
    # Do binary search with small tolerance
    while max_size - min_size > 0.5:
        mid_size = (min_size + max_size) / 2
        fits, _ = check_text_fits(text, mid_size, box_width_emu, box_height_emu, font_name)
        
        if fits:
            best_size = mid_size
            min_size = mid_size
        else:
            max_size = mid_size
    
    return best_size


def apply_shape_properties(shape, shape_data, auto_adjust_font: bool = True):
    """Apply saved properties to a shape with paragraph-level formatting preservation."""
    try:
        shape.width = shape_data["width"]
        shape.height = shape_data["height"]
        shape.left = shape_data["left"]
        shape.top = shape_data["top"]
        
        # Configure text frame to prevent overflow
        shape.text_frame.word_wrap = True
        shape.text_frame.auto_size = 1  # 1 = PP_AUTOSIZE.NONE - disable auto-sizing, keep bounds fixed
        
        # NEW: Restore paragraph-by-paragraph formatting
        if shape_data.get("paragraphs"):
            # Use detailed paragraph data if available
            # Clear all existing paragraphs except the first one
            while len(shape.text_frame.paragraphs) > 1:
                p = shape.text_frame.paragraphs[-1]._element
                p.getparent().remove(p)
            
            # Clear the first paragraph's text
            shape.text_frame.paragraphs[0].text = ""
            
            # Calculate optimal font size to fit within bounding box
            optimal_font_size = None
            if auto_adjust_font:
                shape_text = shape_data.get("text", "")
                if shape_text.strip():
                    original_size = shape_data.get("font_size") or 12.0
                    
                    # ALWAYS calculate if text fits - don't assume original was correct
                    # The original might have been overflowing too
                    fits_at_original, suggested_size = check_text_fits(
                        shape_text,
                        original_size,
                        shape_data["width"],
                        shape_data["height"],
                        shape_data.get("font_name", "Arial")
                    )
                    
                    if not fits_at_original:
                        # Text doesn't fit at original size - find optimal size
                        optimal_font_size = find_largest_fitting_font(
                            shape_text,
                            original_size,
                            shape_data["width"],
                            shape_data["height"],
                            shape_data.get("font_name", "Arial")
                        )
                        print(f"  ⚠️  Text exceeds box - adjusting font: {original_size:.1f}pt → {optimal_font_size:.1f}pt")
                    else:
                        # Text fits - keep original size
                        optimal_font_size = original_size
            
            for para_idx, para_data in enumerate(shape_data["paragraphs"]):
                if para_idx == 0:
                    paragraph = shape.text_frame.paragraphs[0]
                else:
                    paragraph = shape.text_frame.add_paragraph()
                
                # Restore paragraph-level properties
                # For subtitles: force level=0 (no bullets) to prevent unwanted bullets
                if shape_data.get("is_subtitle") and para_idx == 1:
                    paragraph.level = 0  # Force no bullet point for subtitle
                else:
                    paragraph.level = para_data.get("level", 0)
                
                if para_data.get("alignment"):
                    paragraph.alignment = get_alignment_value(para_data["alignment"])
                if para_data.get("line_spacing"):
                    paragraph.line_spacing = para_data["line_spacing"]
                if para_data.get("space_before"):
                    paragraph.space_before = para_data["space_before"]
                if para_data.get("space_after"):
                    paragraph.space_after = para_data["space_after"]
                
                # Restore runs with individual formatting
                runs = para_data.get("runs", [])
                if runs:
                    for run_idx, run_data in enumerate(runs):
                        run = paragraph.add_run()
                        run.text = run_data.get("text", "")
                        
                        # Preserve original font size and name - ONLY set if extracted
                        font_size_to_use = run_data.get("font_size")
                        
                        # Apply optimal size if calculated
                        if optimal_font_size is not None and font_size_to_use is not None:
                            font_size_to_use = optimal_font_size
                        
                        if font_size_to_use is not None:
                            run.font.size = Pt(font_size_to_use)
                        
                        if run_data.get("font_name"):
                            run.font.name = run_data["font_name"]
                        
                        if run_data.get("font_color"):
                            try:
                                run.font.color.rgb = RGBColor.from_string(run_data["font_color"])
                            except Exception:
                                pass
                        if run_data.get("bold") is not None:
                            run.font.bold = run_data["bold"]
                        if run_data.get("italic") is not None:
                            run.font.italic = run_data["italic"]
                else:
                    # Fallback if no runs data - use paragraph text
                    run = paragraph.add_run()
                    run.text = para_data.get("text", "")
                    # Only set properties if they were extracted
                    if shape_data.get("font_size"):
                        font_size = shape_data["font_size"]
                        if optimal_font_size is not None:
                            font_size = optimal_font_size
                        run.font.size = Pt(font_size)
                    if shape_data.get("font_name"):
                        run.font.name = shape_data["font_name"]
        else:
            # Fallback to original single-text approach (backward compatibility)
            # Enable word wrap to prevent text from overflowing
            shape.text_frame.word_wrap = True
            
            paragraph = shape.text_frame.paragraphs[0]
            paragraph.text = ""
            run = paragraph.add_run()
            run.text = shape_data["text"]
            
            original_font_size = shape_data.get("font_size") or 12.0
            font_size = original_font_size
            
            # ALWAYS check if text fits in bounding box
            if auto_adjust_font and shape_data["text"].strip():
                fits_at_original, suggested_size = check_text_fits(
                    shape_data["text"],
                    original_font_size,
                    shape_data["width"],
                    shape_data["height"],
                    shape_data.get("font_name", "Arial")
                )
                
                if not fits_at_original:
                    # Find optimal size that fits
                    font_size = find_largest_fitting_font(
                        shape_data["text"],
                        original_font_size,
                        shape_data["width"],
                        shape_data["height"],
                        shape_data.get("font_name", "Arial")
                    )
                    print(f"  ⚠️  Text exceeds box - adjusted: {original_font_size:.1f}pt → {font_size:.1f}pt")
            
            # Apply font properties (preserve original size when possible)
            run.font.size = Pt(font_size)
            if shape_data.get("font_name"):
                run.font.name = shape_data["font_name"]
            if shape_data.get("font_color"):
                try:
                    run.font.color.rgb = RGBColor.from_string(shape_data["font_color"])
                except Exception:
                    pass
            if shape_data.get("bold") is not None:
                run.font.bold = shape_data["bold"]
            if shape_data.get("italic") is not None:
                run.font.italic = shape_data["italic"]
            if shape_data.get("alignment"):
                paragraph.alignment = get_alignment_value(shape_data["alignment"])
            if shape_data.get("line_spacing"):
                paragraph.line_spacing = shape_data["line_spacing"]
            if shape_data.get("space_before"):
                paragraph.space_before = shape_data["space_before"]
            if shape_data.get("space_after"):
                paragraph.space_after = shape_data["space_after"]
        
        # Post-application: verify text fits and shrink if needed
        _enforce_text_bounds(shape, shape_data)
    except Exception as exc:  # pragma: no cover - best effort logging
        print(f"Error applying shape properties: {exc}")


def _enforce_text_bounds(shape, shape_data, min_font_size: float = 6.0):
    """Verify text fits within shape bounds and shrink if needed.
    
    FINAL SAFETY CHECK: After applying text, checks if any part extends beyond bounds.
    This catches cases where:
    - Original text was already overflowing
    - Translation is longer than original
    - Font sizing calculations were estimates
    
    If text doesn't fit, progressively reduces font size across all runs.
    """
    if not shape.has_text_frame or not shape.text_frame.paragraphs:
        return
    
    try:
        # Get the shape bounding box dimensions
        shape_width_emu = shape.width
        shape_height_emu = shape.height
        
        # Get all runs to check and potentially adjust
        all_runs = []
        for paragraph in shape.text_frame.paragraphs:
            for run in paragraph.runs:
                if run.text.strip():
                    all_runs.append(run)
        
        if not all_runs:
            return
        
        # Estimate current font sizes
        current_sizes = []
        for run in all_runs:
            if run.font.size:
                current_sizes.append(run.font.size.pt)
            else:
                current_sizes.append(shape_data.get("font_size", 12.0))
        
        if not current_sizes:
            current_sizes = [shape_data.get("font_size", 12.0)] * len(all_runs)
        
        # Get the average font size (representative size)
        avg_font_size = sum(current_sizes) / len(current_sizes) if current_sizes else 12.0
        
        # Calculate full text
        full_text = shape_data.get("text", "")
        if not full_text.strip():
            return
        
        # Check if text fits at current size within bounding box
        # Use conservative margins to ensure no overflow
        fits, suggested_size = check_text_fits(
            full_text,
            avg_font_size,
            shape_width_emu,
            shape_height_emu,
            shape_data.get("font_name", "Arial")
        )
        
        if not fits:
            # Text exceeds bounds - shrink all runs proportionally
            scale_factor = suggested_size / avg_font_size if avg_font_size > 0 else 0.8
            
            print(f"  ⚠️  FINAL CHECK: Text exceeds box bounds - shrinking from {avg_font_size:.1f}pt to {suggested_size:.1f}pt")
            
            for i, run in enumerate(all_runs):
                if current_sizes[i] > min_font_size:
                    new_size = max(min_font_size, current_sizes[i] * scale_factor)
                    run.font.size = Pt(new_size)
    except Exception as e:
        # Silent fail - best effort
        pass


def get_table_properties(table):
    """Extract table properties including all paragraphs and runs in each cell."""
    table_data = {
        "rows": len(table.rows),
        "cols": len(table.columns),
        "cells": [],
    }
    for row in table.rows:
        row_data = []
        for cell in row.cells:
            cell_data = {
                "text": cell.text.strip(),  # Full cell text
                "paragraphs": [],  # Store all paragraphs with formatting
                "font_size": None,
                "font_name": None,
                "alignment": None,
                "margin_left": cell.margin_left,
                "margin_right": cell.margin_right,
                "margin_top": cell.margin_top,
                "margin_bottom": cell.margin_bottom,
                "vertical_anchor": str(cell.vertical_anchor) if cell.vertical_anchor else None,
                "font_color": None,
            }
            
            # Extract all paragraphs and runs (not just first)
            if cell.text_frame.paragraphs:
                for para in cell.text_frame.paragraphs:
                    para_data = {
                        "text": para.text,
                        "alignment": f"PP_ALIGN.{para.alignment}" if para.alignment else None,
                        "runs": []
                    }
                    for run in para.runs:
                        run_data = {
                            "text": run.text,
                            "font_size": run.font.size.pt if getattr(run.font, "size", None) is not None else None,
                            "font_name": getattr(run.font, "name", None),
                            "bold": run.font.bold,
                            "italic": run.font.italic,
                            "font_color": str(run.font.color.rgb) if (
                                getattr(run.font, "color", None) is not None
                                and getattr(run.font.color, "rgb", None) is not None
                            ) else None,
                        }
                        para_data["runs"].append(run_data)
                    cell_data["paragraphs"].append(para_data)
                
                # Get defaults from first paragraph/run for backward compatibility
                paragraph = cell.text_frame.paragraphs[0]
                if paragraph.runs:
                    run = paragraph.runs[0]
                    if getattr(run.font, "size", None) is not None:
                        cell_data["font_size"] = run.font.size.pt
                    if getattr(run.font, "name", None):
                        cell_data["font_name"] = run.font.name
                    if hasattr(run.font, "bold"):
                        cell_data["bold"] = run.font.bold
                    if hasattr(run.font, "italic"):
                        cell_data["italic"] = run.font.italic
                    if (
                        getattr(run.font, "color", None) is not None
                        and getattr(run.font.color, "rgb", None) is not None
                    ):
                        cell_data["font_color"] = str(run.font.color.rgb)
                if getattr(paragraph, "alignment", None) is not None:
                    cell_data["alignment"] = f"PP_ALIGN.{paragraph.alignment}" if paragraph.alignment else None
            row_data.append(cell_data)
        table_data["cells"].append(row_data)
    return table_data


def apply_table_properties(table, table_data):
    """Apply saved table properties."""
    for row_idx, row in enumerate(table.rows):
        for col_idx, cell in enumerate(row.cells):
            try:
                cell_data = table_data["cells"][row_idx][col_idx]
                cell.margin_left = cell_data["margin_left"]
                cell.margin_right = cell_data["margin_right"]
                cell.margin_top = cell_data["margin_top"]
                cell.margin_bottom = cell_data["margin_bottom"]
                if cell_data.get("vertical_anchor"):
                    # Parse vertical anchor safely
                    anchor_str = cell_data["vertical_anchor"]
                    if "TOP" in anchor_str:
                        cell.vertical_anchor = MSO_ANCHOR.TOP
                    elif "MIDDLE" in anchor_str:
                        cell.vertical_anchor = MSO_ANCHOR.MIDDLE
                    elif "BOTTOM" in anchor_str:
                        cell.vertical_anchor = MSO_ANCHOR.BOTTOM
                
                # Clear existing content
                cell.text = ""
                
                # Apply paragraph-by-paragraph formatting if available
                if cell_data.get("paragraphs"):
                    # Clear all paragraphs except first
                    while len(cell.text_frame.paragraphs) > 1:
                        p = cell.text_frame.paragraphs[-1]._element
                        p.getparent().remove(p)
                    
                    for para_idx, para_data in enumerate(cell_data["paragraphs"]):
                        if para_idx == 0:
                            paragraph = cell.text_frame.paragraphs[0]
                        else:
                            paragraph = cell.text_frame.add_paragraph()
                        
                        # Apply paragraph alignment
                        if para_data.get("alignment"):
                            paragraph.alignment = get_alignment_value(para_data["alignment"])
                        
                        # Apply runs with formatting
                        if para_data.get("runs"):
                            for run_data in para_data["runs"]:
                                run = paragraph.add_run()
                                run.text = run_data.get("text", "")
                                
                                if run_data.get("font_size"):
                                    run.font.size = Pt(run_data["font_size"] * 0.8)  # Scale for tables
                                if run_data.get("font_name"):
                                    run.font.name = run_data["font_name"]
                                if run_data.get("font_color"):
                                    run.font.color.rgb = RGBColor.from_string(run_data["font_color"])
                                if run_data.get("bold") is not None:
                                    run.font.bold = run_data["bold"]
                                if run_data.get("italic") is not None:
                                    run.font.italic = run_data["italic"]
                else:
                    # Fallback to simple text application
                    paragraph = cell.text_frame.paragraphs[0]
                    run = paragraph.add_run()
                    run.text = cell_data["text"]
                    if cell_data.get("font_size"):
                        adjusted_size = cell_data["font_size"] * 0.8
                        run.font.size = Pt(adjusted_size)
                    run.font.name = cell_data.get("font_name") or "Arial"
                    if cell_data.get("font_color"):
                        run.font.color.rgb = RGBColor.from_string(cell_data["font_color"])
                    if "bold" in cell_data:
                        run.font.bold = cell_data["bold"]
                    if "italic" in cell_data:
                        run.font.italic = cell_data["italic"]
                    if cell_data.get("alignment"):
                        paragraph.alignment = get_alignment_value(cell_data["alignment"])
            except Exception as exc:  # pragma: no cover - best effort logging
                print(f"Error setting cell properties: {exc}")


def _process_shape_recursive(
    shape,
    shape_index: int,
    slide_element: ET.Element,
    slide_number: int,
    translator: TranslationService | None,
    source_lang: str,
    target_lang: str,
    parent_path: str = ""
):
    """Recursively process a shape and its nested shapes (groups).
    
    Handles:
    - Regular text shapes
    - Tables
    - Group shapes (containing nested shapes)
    - Shapes within groups
    """
    current_path = f"{parent_path}.{shape_index}" if parent_path else str(shape_index)
    
    # Check if this is a group shape with nested shapes
    if hasattr(shape, 'shapes'):
        # This is a group shape - recursively process its children
        for nested_index, nested_shape in enumerate(shape.shapes):
            _process_shape_recursive(
                nested_shape,
                nested_index,
                slide_element,
                slide_number,
                translator,
                source_lang,
                target_lang,
                parent_path=current_path
            )
    
    # Process the shape itself - check for table first (most specific)
    if hasattr(shape, 'table'):
        # This shape has a table - process it
        table_element = ET.SubElement(slide_element, "table_element")
        table_element.set("shape_index", current_path)
        table_data = get_table_properties(shape.table)
        if translator:
            # Translate each cell's text
            for row_idx, row in enumerate(table_data["cells"]):
                for col_idx, cell in enumerate(row):
                    if cell.get("text", "").strip():
                        original = cell["text"]
                        translated = translator.translate(cell["text"], source_lang, target_lang)
                        cell["text"] = translated
                        
                        # Also distribute translation to paragraph structure
                        if cell.get("paragraphs"):
                            _apply_translation_to_paragraphs(cell["paragraphs"], original, translated)
                        
                        if original != translated:
                            print(f"    [Slide {slide_number}] Table {current_path}[{row_idx},{col_idx}]: {original[:30]}... → {translated[:30]}...")
        props_element = ET.SubElement(table_element, "properties")
        props_element.text = json.dumps(table_data, indent=2)
    elif hasattr(shape, "text_frame") and hasattr(shape, "text"):
        # Has text frame - extract and translate
        text_element = ET.SubElement(slide_element, "text_element")
        text_element.set("shape_index", current_path)
        shape_data = get_shape_properties(shape)
        
        if translator and shape_data.get("text", "").strip():
            original_text = shape_data["text"]
            translated_text = translator.translate(shape_data["text"], source_lang, target_lang)
            shape_data["text"] = translated_text
            
            if original_text and original_text != translated_text:
                print(f"    [Slide {slide_number}] {current_path}: {original_text[:40]}... → {translated_text[:40]}...")
            
            if shape_data.get("paragraphs"):
                _apply_translation_to_paragraphs(shape_data["paragraphs"], original_text, translated_text)
        
        props_element = ET.SubElement(text_element, "properties")
        props_element.text = json.dumps(shape_data, indent=2)


def extract_text_from_slide(
    slide,
    slide_number: int,
    *,
    translator: TranslationService | None,
    source_lang: str,
    target_lang: str,
):
    """Extract text from a slide and optionally translate it.
    
    Recursively processes all shapes including nested groups.
    """
    slide_element = ET.Element("slide")
    slide_element.set("number", str(slide_number))
    
    # Process all shapes recursively (handles nested groups)
    for shape_index, shape in enumerate(slide.shapes):
        _process_shape_recursive(
            shape,
            shape_index,
            slide_element,
            slide_number,
            translator,
            source_lang,
            target_lang
        )
    
    return slide_element


def ppt_to_xml(
    ppt_path: str,
    *,
    translator: TranslationService | None,
    source_lang: str,
    target_lang: str,
    max_workers: int = 4,
    temp_dir: Path | None = None,
) -> Optional[str]:
    """Convert a PowerPoint presentation to XML with performance timing."""
    import time
    root = ET.Element("presentation")
    base_dir = Path(ppt_path).parent
    if temp_dir is None:
        temp_dir = base_dir
    try:
        prs = Presentation(ppt_path)
        root.set("file_path", Path(ppt_path).name)
        workers = max(1, max_workers)
        
        print(f"\n⏱️  Processing {len(prs.slides)} slides with {workers} workers...")
        start_time = time.time()
        
        with ThreadPoolExecutor(max_workers=workers) as executor:
            future_to_slide = {
                executor.submit(
                    extract_text_from_slide,
                    slide,
                    slide_number,
                    translator=translator,
                    source_lang=source_lang,
                    target_lang=target_lang,
                ): slide_number
                for slide_number, slide in enumerate(prs.slides, start=1)
            }
            for idx, (future, slide_number) in enumerate(future_to_slide.items(), 1):
                slide_start = time.time()
                slide_element = future.result()
                slide_elapsed = time.time() - slide_start
                root.append(slide_element)
                intermediate_path = temp_dir / f"slide_{slide_number}_{'translated' if translator else 'original'}.xml"
                xml_str = minidom.parseString(ET.tostring(root)).toprettyxml(indent="  ")
                with open(intermediate_path, "w", encoding="utf-8") as handle:
                    handle.write(xml_str)
                print(f"  [Slide {slide_number}/{len(prs.slides)}] Completed in {slide_elapsed:.2f}s")
        
        total_time = time.time() - start_time
        print(f"✅ All slides processed in {total_time:.2f}s ({total_time/len(prs.slides):.2f}s per slide)")
        return minidom.parseString(ET.tostring(root)).toprettyxml(indent="  ")
    except Exception as exc:  # pragma: no cover - best effort logging
        print(f"Error processing presentation: {exc}")
        return None


def _apply_shape_recursive(
    shape,
    shape_index: int,
    xml_slide: ET.Element,
    parent_path: str = ""
):
    """Recursively apply translations to a shape and its nested shapes.
    
    Handles groups containing nested shapes.
    """
    current_path = f"{parent_path}.{shape_index}" if parent_path else str(shape_index)
    
    # Check if this is a group shape with nested shapes
    if hasattr(shape, 'shapes'):
        # Recursively process nested shapes
        for nested_index, nested_shape in enumerate(shape.shapes):
            _apply_shape_recursive(
                nested_shape,
                nested_index,
                xml_slide,
                parent_path=current_path
            )
    
    # Apply translation to the shape itself - check for table first
    if hasattr(shape, 'table'):
        # This shape has a table
        table_element = xml_slide.find(f".//table_element[@shape_index='{current_path}']")
        if table_element is not None:
            props_element = table_element.find("properties")
            if props_element is not None and props_element.text:
                try:
                    table_data = json.loads(props_element.text)
                    apply_table_properties(shape.table, table_data)
                except Exception as exc:
                    print(f"Error applying table properties: {exc}")
    elif hasattr(shape, "text_frame") and hasattr(shape, "text"):
        # Has text frame
        text_element = xml_slide.find(f".//text_element[@shape_index='{current_path}']")
        if text_element is not None:
            props_element = text_element.find("properties")
            if props_element is not None and props_element.text:
                try:
                    shape_data = json.loads(props_element.text)
                    apply_shape_properties(shape, shape_data, auto_adjust_font=True)
                except Exception as exc:
                    print(f"Error applying shape properties: {exc}")


def create_translated_ppt(original_ppt_path: str, translated_xml_path: str, output_ppt_path: str) -> None:
    """Create a new PowerPoint presentation using translated content.
    
    Recursively processes all shapes including nested groups.
    """
    try:
        prs = Presentation(original_ppt_path)
        tree = ET.parse(translated_xml_path)
        root = tree.getroot()
        for slide_number, slide in enumerate(prs.slides, start=1):
            xml_slide = root.find(f".//slide[@number='{slide_number}']")
            if xml_slide is None:
                continue
            
            # Process all shapes recursively
            for shape_index, shape in enumerate(slide.shapes):
                _apply_shape_recursive(shape, shape_index, xml_slide)
        
        prs.save(output_ppt_path)
        print(f"Translated PowerPoint saved to: {output_ppt_path}")
    except Exception as exc:  # pragma: no cover - logging only
        print(f"Error creating translated PowerPoint: {exc}")


def _collect_review_data(
    original_xml_path: Optional[Path],
    translated_xml_path: Path,
    vision_reviewer: Optional[VisionReviewer] = None,
) -> List[SlideTranslation]:
    """Collect translation data for review file generation."""
    review_slides = []
    
    try:
        # Parse translated XML
        tree = ET.parse(translated_xml_path)
        root = tree.getroot()
        
        # Parse original XML if available
        original_root = None
        if original_xml_path and original_xml_path.exists():
            original_tree = ET.parse(original_xml_path)
            original_root = original_tree.getroot()
        
        for xml_slide in root.findall(".//slide"):
            slide_number = int(xml_slide.get("number", "0"))
            if slide_number == 0:
                continue
            
            original_texts = []
            translated_texts = []
            quality_score = None
            issues = []
            
            # Collect text elements
            for text_elem in xml_slide.findall(".//text_element"):
                shape_index = int(text_elem.get("shape_index", "-1"))
                props_elem = text_elem.find("properties")
                if props_elem is not None and props_elem.text:
                    try:
                        shape_data = json.loads(props_elem.text)
                        translated_texts.append({
                            "shape_index": shape_index,
                            "text": shape_data.get("text", ""),
                            "properties": shape_data,
                        })
                    except Exception:
                        pass
            
            # Get original texts if available
            if original_root:
                orig_slide = original_root.find(f".//slide[@number='{slide_number}']")
                if orig_slide is not None:
                    for text_elem in orig_slide.findall(".//text_element"):
                        shape_index = int(text_elem.get("shape_index", "-1"))
                        props_elem = text_elem.find("properties")
                        if props_elem is not None and props_elem.text:
                            try:
                                shape_data = json.loads(props_elem.text)
                                original_texts.append({
                                    "shape_index": shape_index,
                                    "text": shape_data.get("text", ""),
                                    "properties": shape_data,
                                })
                            except Exception:
                                pass
            
            # Match original and translated texts by shape_index
            # Create a map for easier matching
            orig_map = {t["shape_index"]: t for t in original_texts}
            trans_map = {t["shape_index"]: t for t in translated_texts}
            
            # Ensure both lists are aligned
            all_indices = sorted(set(orig_map.keys()) | set(trans_map.keys()))
            aligned_original = []
            aligned_translated = []
            
            for idx in all_indices:
                aligned_original.append(orig_map.get(idx, {"shape_index": idx, "text": "", "properties": {}}))
                aligned_translated.append(trans_map.get(idx, {"shape_index": idx, "text": "", "properties": {}}))
            
            slide_translation = SlideTranslation(
                slide_number=slide_number,
                original_texts=aligned_original,
                translated_texts=aligned_translated,
                quality_score=quality_score,
                issues=issues,
            )
            review_slides.append(slide_translation)
    
    except Exception as e:
        print(f"Warning: Could not collect review data: {e}")
    
    return review_slides


def regenerate_ppt_from_review(
    original_ppt_path: Path,
    review_data,
    file_index: int,
    output_path: Path,
    update_memory=None,
) -> None:
    """Regenerate PPT from edited review file data.
    
    Args:
        original_ppt_path: Path to original PPT file
        review_data: ReviewData object with edited translations
        file_index: Index of file in review_data.files list
        output_path: Path for output PPT file
        update_memory: Optional TranslationMemory to update with edits
    """
    if file_index >= len(review_data.files):
        raise ValueError(f"File index {file_index} out of range")
    
    file_review = review_data.files[file_index]
    
    try:
        prs = Presentation(str(original_ppt_path))
        
        # Create a mapping of slide number to translations
        slide_translations = {s.slide_number: s for s in file_review.slides}
        
        for slide_number, slide in enumerate(prs.slides, start=1):
            if slide_number not in slide_translations:
                continue
            
            slide_trans = slide_translations[slide_number]
            
            # Create a mapping of shape_index to translated text
            trans_map = {t["shape_index"]: t for t in slide_trans.translated_texts}
            
            for shape_index, shape in enumerate(slide.shapes):
                if shape_index in trans_map:
                    trans_data = trans_map[shape_index]
                    
                    if shape.shape_type == MSO_SHAPE_TYPE.TABLE:
                        # Handle table updates if needed
                        pass
                    elif hasattr(shape, "text"):
                        # Update text with edited translation
                        edited_text = trans_data.get("text", "")
                        if edited_text:
                            # Get properties from original or use defaults
                            props = trans_data.get("properties", {})
                            
                            # Clear existing text
                            shape.text = ""
                            paragraph = shape.text_frame.paragraphs[0]
                            run = paragraph.add_run()
                            run.text = edited_text
                            
                            # Apply properties if available
                            if props.get("font_size"):
                                run.font.size = Pt(props["font_size"] * 0.7)
                            if props.get("font_name"):
                                run.font.name = props["font_name"]
                            if props.get("font_color"):
                                try:
                                    run.font.color.rgb = RGBColor.from_string(props["font_color"])
                                except Exception:
                                    pass
                            
                            # Update translation memory if provided
                            if update_memory:
                                orig_text = ""
                                for orig in slide_trans.original_texts:
                                    if orig.get("shape_index") == shape_index:
                                        orig_text = orig.get("text", "")
                                        break
                                if orig_text:
                                    update_memory.set(orig_text, edited_text)
        
        prs.save(str(output_path))
        print(f"✅ Regenerated PPT from review: {output_path.name}")
    
    except Exception as e:
        raise RuntimeError(f"Error regenerating PPT: {e}") from e


def cleanup_intermediate_files(temp_dir: Path) -> None:
    """Remove all intermediate files and the temp directory."""
    try:
        # Remove all files in the temp directory
        for file in temp_dir.glob("*"):
            if file.is_file():
                try:
                    file.unlink()
                except Exception:
                    pass  # Continue cleaning up other files even if one fails
        # Remove the temp directory itself (only works if empty)
        if temp_dir.exists():
            try:
                temp_dir.rmdir()
            except OSError:
                # Directory not empty or other error - log but don't fail
                print(f"Warning: Could not remove temp directory {temp_dir.name}/ (may not be empty)")
    except Exception as exc:  # pragma: no cover - logging only
        print(f"Warning: Could not clean up intermediate files: {exc}")


def process_ppt_file(
    ppt_path: Path,
    *,
    translator: TranslationService,
    source_lang: str,
    target_lang: str,
    max_workers: int = 4,
    cleanup: bool = True,
    vision_reviewer: VisionReviewer | None = None,
    max_refinement_iterations: int = 3,
    collect_review_data: bool = False,
):
    """Process a single PowerPoint file from extraction to translated output."""
    if not ppt_path.is_file():
        raise FileNotFoundError(f"'{ppt_path}' is not a valid file.")
    if ppt_path.suffix.lower() not in {".ppt", ".pptx"}:
        raise ValueError(f"'{ppt_path}' is not a PowerPoint file.")

    base_dir = ppt_path.parent
    # Create temp directory for intermediate files
    temp_dir = base_dir / f"{ppt_path.stem}_temp"
    temp_dir.mkdir(exist_ok=True)
    print(f"Using temp directory: {temp_dir.name}/")

    print(f"Generating original XML for {ppt_path.name}...")
    original_xml = ppt_to_xml(
        str(ppt_path),
        translator=None,
        source_lang=source_lang,
        target_lang=target_lang,
        max_workers=max_workers,
        temp_dir=temp_dir,
    )
    if original_xml:
        original_output_path = temp_dir / f"{ppt_path.stem}_original.xml"
        with open(original_output_path, "w", encoding="utf-8") as handle:
            handle.write(original_xml)
        print(f"Original XML saved: {original_output_path}")

    print(
        f"Generating translated XML (from {source_lang} to {target_lang}) for {ppt_path.name}..."
    )
    translated_xml = ppt_to_xml(
        str(ppt_path),
        translator=translator,
        source_lang=source_lang,
        target_lang=target_lang,
        max_workers=max_workers,
        temp_dir=temp_dir,
    )
    if not translated_xml:
        return None, None if collect_review_data else None

    translated_output_path = temp_dir / f"{ppt_path.stem}_translated.xml"
    with open(translated_output_path, "w", encoding="utf-8") as handle:
        handle.write(translated_xml)
    print(f"Translated XML saved: {translated_output_path}")

    print(f"Creating translated PPT for {ppt_path.name}...")
    output_filename = f"{ppt_path.stem}_translated{ppt_path.suffix}"
    output_ppt_path = base_dir / output_filename
    
    # Vision-based iterative refinement
    if vision_reviewer:
        print(f"🔍 Vision review enabled (max {max_refinement_iterations} iterations)")
        
        # Pre-translation: Analyze original slides
        print("  📸 Rendering original slides for analysis...")
        prs_original = Presentation(str(ppt_path))
        for slide_num in range(1, len(prs_original.slides) + 1):
            original_img = temp_dir / f"slide_{slide_num}_original.png"
            if render_slide_to_image(ppt_path, slide_num, original_img):
                analysis = vision_reviewer.analyze_original_slide(
                    original_img, source_lang, target_lang
                )
                if analysis:
                    print(f"    Slide {slide_num}: Analyzed")
        
        # Iterative refinement loop
        best_ppt_path = None
        best_score = 0.0
        
        for iteration in range(1, max_refinement_iterations + 1):
            if iteration > 1:
                print(f"  🔄 Refinement iteration {iteration}/{max_refinement_iterations}")
            
            # Create translated PPTX
            iter_output_path = base_dir / f"{ppt_path.stem}_translated_iter{iteration}{ppt_path.suffix}"
            create_translated_ppt(str(ppt_path), str(translated_output_path), str(iter_output_path))
            
            # Review translated slides
            print(f"  📸 Rendering translated slides for review...")
            all_passed = True
            min_score = 10.0
            
            for slide_num in range(1, len(prs_original.slides) + 1):
                original_img = temp_dir / f"slide_{slide_num}_original.png"
                translated_img = temp_dir / f"slide_{slide_num}_translated_iter{iteration}.png"
                
                if render_slide_to_image(iter_output_path, slide_num, translated_img):
                    review_result = vision_reviewer.review_translated_slide(
                        original_img, translated_img, source_lang, target_lang
                    )
                    
                    print(f"    Slide {slide_num}: Quality score {review_result.quality_score:.1f}/10")
                    if review_result.issues:
                        print(f"      Issues: {', '.join(review_result.issues[:3])}")
                    
                    min_score = min(min_score, review_result.quality_score)
                    if review_result.needs_refinement:
                        all_passed = False
            
            # Check if quality threshold met
            if min_score >= vision_reviewer.quality_threshold or all_passed:
                print(f"  ✅ Quality threshold met (score: {min_score:.1f}/10)")
                best_ppt_path = iter_output_path
                break
            elif iteration < max_refinement_iterations:
                print(f"  ⚠️  Quality below threshold ({min_score:.1f}/10), refining...")
                # TODO: Apply suggestions from review_result to improve translation
                # For now, we'll just retry (could use suggestions to adjust font sizes, etc.)
            else:
                print(f"  ⚠️  Max iterations reached (final score: {min_score:.1f}/10)")
                best_ppt_path = iter_output_path
        
        # Use best result or final iteration
        if best_ppt_path and best_ppt_path != output_ppt_path:
            best_ppt_path.rename(output_ppt_path)
            # Clean up iteration files
            for iter_file in base_dir.glob(f"{ppt_path.stem}_translated_iter*.pptx"):
                if iter_file != output_ppt_path:
                    iter_file.unlink()
    else:
        # No vision review - just create translated PPT
        create_translated_ppt(str(ppt_path), str(translated_output_path), str(output_ppt_path))

    # Collect review data if requested
    review_slides = None
    if collect_review_data:
        review_slides = _collect_review_data(
            original_xml_path=original_output_path if original_xml else None,
            translated_xml_path=translated_output_path,
            vision_reviewer=vision_reviewer,
        )

    if cleanup:
        cleanup_intermediate_files(temp_dir)
        print(f"Intermediate files and temp directory cleaned up.")
    else:
        print(f"Intermediate files kept in {temp_dir.name}/ (you can delete manually)")

    if collect_review_data:
        return output_ppt_path, review_slides
    return output_ppt_path
