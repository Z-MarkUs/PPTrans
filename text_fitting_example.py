"""
Example: How to Check if Text Fits in PowerPoint Textbox

This demonstrates the three methods available in pipeline.py for checking
if text overflows a textbox and finding optimal font sizes.
"""

from pptx import Presentation
from pptx.util import Pt, Inches
from ppt_translator.pipeline import (
    check_text_fits,
    find_largest_fitting_font,
    check_text_overflow_in_textframe,
    find_largest_fitting_font_in_textframe,
)


def example_1_simple_estimation():
    """Method 1: Simple estimation-based approach (fastest, less accurate)
    
    Uses mathematical estimation of text dimensions based on font size
    and character count.
    """
    text = "This is some text that might overflow"
    font_size = 24  # points
    box_width_emu = 1828800  # EMU units
    box_height_emu = 914400
    
    # Check if text fits
    fits, suggested_size = check_text_fits(text, font_size, box_width_emu, box_height_emu)
    
    print(f"Method 1: Estimation")
    print(f"  Text: {text}")
    print(f"  Fits at {font_size}pt: {fits}")
    print(f"  Suggested size: {suggested_size:.1f}pt")
    print()


def example_2_binary_search():
    """Method 2: Binary search for optimal size (medium speed, medium accuracy)
    
    Uses binary search to find the largest font size that fits,
    based on estimation.
    """
    text = "This is some text that might overflow"
    original_font_size = 24
    box_width_emu = 1828800
    box_height_emu = 914400
    
    # Find largest fitting font size
    best_size = find_largest_fitting_font(text, original_font_size, box_width_emu, box_height_emu)
    
    print(f"Method 2: Binary Search (Estimation-based)")
    print(f"  Text: {text}")
    print(f"  Original size: {original_font_size}pt")
    print(f"  Largest fitting size: {best_size:.1f}pt")
    print()


def example_3_textframe_measurement():
    """Method 3: TextFrame-based measurement (slower, most accurate)
    
    Actually uses the TextFrame object to check for overflow.
    This is the most accurate as it respects word wrapping and
    internal layout engine of python-pptx.
    """
    # Create a test presentation
    prs = Presentation()
    blank_slide_layout = prs.slide_layouts[6]  # Blank layout
    slide = prs.slides.add_slide(blank_slide_layout)
    
    # Add a textbox with specific dimensions
    left = Inches(1)
    top = Inches(1)
    width = Inches(5)
    height = Inches(2)
    textbox = slide.shapes.add_textbox(left, top, width, height)
    text_frame = textbox.text_frame
    
    text = "This is some text that might overflow the textbox"
    font_size = 24
    
    # Check if text fits in this specific textbox
    fits, overflow_ratio = check_text_overflow_in_textframe(text_frame, text, font_size)
    
    print(f"Method 3: TextFrame Measurement")
    print(f"  Text: {text}")
    print(f"  Textbox size: 5\" x 2\"")
    print(f"  Fits at {font_size}pt: {fits}")
    print(f"  Overflow ratio: {overflow_ratio:.2f} (>1.0 = overflow)")
    print()


def example_4_find_optimal_size_in_textframe():
    """Method 4: Find optimal size using TextFrame (slowest, most accurate)
    
    Uses binary search with TextFrame measurement to find the largest
    font size that fits in a specific textbox.
    """
    # Create a test presentation
    prs = Presentation()
    blank_slide_layout = prs.slide_layouts[6]  # Blank layout
    slide = prs.slides.add_slide(blank_slide_layout)
    
    # Add a textbox with specific dimensions
    left = Inches(1)
    top = Inches(1)
    width = Inches(4)
    height = Inches(1.5)
    textbox = slide.shapes.add_textbox(left, top, width, height)
    text_frame = textbox.text_frame
    
    text = "This is some text that might overflow the textbox"
    original_font_size = 24
    
    # Find largest fitting font size in this textbox
    best_size = find_largest_fitting_font_in_textframe(
        text_frame, text, original_font_size
    )
    
    print(f"Method 4: Find Optimal Font Size (TextFrame-based)")
    print(f"  Text: {text}")
    print(f"  Textbox size: 4\" x 1.5\"")
    print(f"  Original font size: {original_font_size}pt")
    print(f"  Optimal font size: {best_size:.1f}pt")
    print()


def comparison_table():
    """Compare the four methods"""
    print("=" * 80)
    print("COMPARISON OF TEXT FITTING METHODS")
    print("=" * 80)
    print()
    print(f"{'Method':<40} {'Speed':<15} {'Accuracy':<15}")
    print("-" * 80)
    print(f"{'1. check_text_fits()':<40} {'Fast':<15} {'Medium':<15}")
    print(f"{'   - Estimation-based':<40} {'(calculation)':<15} {'(±10%)':<15}")
    print()
    print(f"{'2. find_largest_fitting_font()':<40} {'Medium':<15} {'Medium-High':<15}")
    print(f"{'   - Binary search + estimation':<40} {'(~10 iterations)':<15} {'(±5%)':<15}")
    print()
    print(f"{'3. check_text_overflow_in_textframe()':<40} {'Medium':<15} {'Very High':<15}")
    print(f"{'   - Direct measurement':<40} {'(layout calc)':<15} {'(actual)':<15}")
    print()
    print(f"{'4. find_largest_fitting_font_in_textframe()':<40} {'Slowest':<15} {'Very High':<15}")
    print(f"{'   - Binary search + TextFrame':<40} {'(~10 iterations)':<15} {'(actual)':<15}")
    print()
    print("=" * 80)
    print()
    print("RECOMMENDATION:")
    print("  - For SPEED: Use Method 1 (check_text_fits)")
    print("  - For BALANCE: Use Method 2 (find_largest_fitting_font)")
    print("  - For ACCURACY: Use Method 4 (find_largest_fitting_font_in_textframe)")
    print("  - Use Method 3 to check a single measurement")
    print()


if __name__ == "__main__":
    print("PowerPoint Text Fitting Methods Examples")
    print("=" * 80)
    print()
    
    try:
        example_1_simple_estimation()
    except Exception as e:
        print(f"Example 1 error: {e}\n")
    
    try:
        example_2_binary_search()
    except Exception as e:
        print(f"Example 2 error: {e}\n")
    
    try:
        example_3_textframe_measurement()
    except Exception as e:
        print(f"Example 3 error: {e}\n")
    
    try:
        example_4_find_optimal_size_in_textframe()
    except Exception as e:
        print(f"Example 4 error: {e}\n")
    
    comparison_table()
    
    print("\nKEY CONCEPTS:")
    print("-" * 80)
    print("""
1. EMU (English Metric Units):
   - PowerPoint internally uses EMU for all measurements
   - 1 point (pt) = 12,700 EMU
   - So 24pt font = 24 * 12,700 = 304,800 EMU

2. TextFrame vs Shape:
   - TextFrame = container for text with word wrapping
   - Shape = the actual shape object with position/size
   - text_frame.word_wrap = True enables automatic line wrapping

3. Text Overflow Detection:
   - Text can overflow if:
     a) Font size too large for box
     b) Text too long for available width
     c) Multiple paragraphs with spacing
   
4. Font Size Adjustment:
   - Find the largest font that fits using binary search
   - Minimum readable size = 6pt
   - Consider word wrapping in calculations

5. Accuracy Trade-offs:
   - Estimation: Fast but ±10% error
   - TextFrame: Slow but accurate (accounts for word wrap)
    """)
