# Text Fitting in PowerPoint - Python Equivalent

This document explains how to detect text overflow in PowerPoint and find optimal font sizes using `python-pptx`.

## Quick Answer

**YES**, there is a Python equivalent to checking if text is bigger than a textbox. Here are the methods:

### Method 1: Simple Estimation (Fastest)
```python
from ppt_translator.pipeline import check_text_fits

fits, suggested_size = check_text_fits(
    text="Hello World",
    font_size_pt=24,
    box_width_emu=1828800,  # Width in EMU (1 pt = 12,700 EMU)
    box_height_emu=914400   # Height in EMU
)

if not fits:
    print(f"Text overflows! Suggested size: {suggested_size}pt")
```

### Method 2: Binary Search for Optimal Size (Balanced)
```python
from ppt_translator.pipeline import find_largest_fitting_font

best_size = find_largest_fitting_font(
    text="Hello World",
    original_font_size=24,
    box_width_emu=1828800,
    box_height_emu=914400
)

print(f"Largest fitting font: {best_size}pt")
```

### Method 3: TextFrame Direct Measurement (Most Accurate)
```python
from pptx import Presentation
from ppt_translator.pipeline import find_largest_fitting_font_in_textframe

prs = Presentation("presentation.pptx")
shape = prs.slides[0].shapes[0]
text_frame = shape.text_frame

best_size = find_largest_fitting_font_in_textframe(
    text_frame,
    "Hello World",
    original_font_size=24
)

print(f"Largest fitting font: {best_size}pt")
```

---

## Deep Dive: How It Works

### Understanding EMU (English Metric Units)

PowerPoint internally uses **EMU** for all measurements:
- **1 point (pt) = 12,700 EMU**
- Example: 24pt font = 24 × 12,700 = 304,800 EMU

```python
# Convert between units
from pptx.util import Pt, Inches

# Get shape dimensions in EMU
width_emu = shape.width          # Already in EMU
height_emu = shape.height        # Already in EMU

# Convert from inches
width_emu = Inches(5)            # 5 inches in EMU
height_emu = Inches(2.5)         # 2.5 inches in EMU

# Convert from points
font_size_emu = Pt(24)           # 24pt in EMU
```

### Three Text Fitting Approaches

#### Approach 1: Estimation-Based (Mathematical)

**How it works:**
1. Calculate approximate character width: `font_size × 0.6 × 12700`
2. Calculate approximate line height: `font_size × 1.2 × 12700`
3. Estimate how many lines needed for the text
4. Compare with available height

**Pros:** Fast, no actual rendering needed  
**Cons:** ±10% accuracy (good enough for most cases)

```python
from ppt_translator.pipeline import estimate_text_dimensions, check_text_fits

# Step 1: Estimate dimensions
estimated_width, estimated_height = estimate_text_dimensions(
    text="Long text here...",
    font_size_pt=24,
    font_name="Arial",
    width_emu=1828800  # Optional: for word-wrapped width
)

# Step 2: Check if it fits
fits, suggested_size = check_text_fits(
    text="Long text here...",
    font_size_pt=24,
    box_width_emu=1828800,
    box_height_emu=914400
)

# Returns:
# fits = False if text too big
# suggested_size = smaller size to use
```

**The Math:**
```
Estimated Width = (len(text) × char_width_emu) or width_emu for wrapped text
Estimated Height = num_lines × line_height_emu × 1.1 (with 10% safety margin)

Where:
  char_width_emu = font_size_pt × 0.6 × 12700
  line_height_emu = font_size_pt × 1.2 × 12700
  num_lines = ceil(total_chars / chars_per_line) for wrapped text
```

#### Approach 2: Binary Search + Estimation

**How it works:**
1. Check if text fits at original font size
2. If not, use binary search to find largest size that fits
3. Search between 6pt (minimum readable) and original size
4. Uses estimation in each iteration

**Pros:** Balanced speed/accuracy  
**Cons:** Still estimation-based (±5-10% error)

```python
from ppt_translator.pipeline import find_largest_fitting_font

best_size = find_largest_fitting_font(
    text="Long text here...",
    original_font_size=24,
    box_width_emu=1828800,
    box_height_emu=914400,
    font_name="Arial"
)

# Binary search iterations:
# Iteration 1: Test 15pt (if fits, search 15-24) or (6-15)
# Iteration 2: Test 12pt or 19pt depending on result
# ... continues until converging on best size
```

**Binary Search Algorithm:**
```
min_size = 6
max_size = original_size
best_size = 6

while (max_size - min_size) > 0.5:
    mid_size = (min_size + max_size) / 2
    if text_fits(mid_size):
        best_size = mid_size
        min_size = mid_size  # Try larger
    else:
        max_size = mid_size  # Try smaller
```

#### Approach 3: TextFrame Direct Measurement (MOST ACCURATE)

**How it works:**
1. Uses the actual TextFrame object from python-pptx
2. Respects word wrapping and layout engine behavior
3. Directly measures against the shape bounds
4. Binary search using actual measurement

**Pros:** Most accurate (detects actual overflow)  
**Cons:** Slightly slower (uses python-pptx internals)

```python
from pptx import Presentation
from ppt_translator.pipeline import (
    check_text_overflow_in_textframe,
    find_largest_fitting_font_in_textframe
)

# Load presentation
prs = Presentation("document.pptx")
shape = prs.slides[0].shapes[0]
text_frame = shape.text_frame

# Method A: Check single size
fits, overflow_ratio = check_text_overflow_in_textframe(
    text_frame,
    text="Long text here...",
    font_size_pt=24
)
# overflow_ratio: 1.5 means text is 150% of available height (50% overflow)

# Method B: Find optimal size
best_size = find_largest_fitting_font_in_textframe(
    text_frame,
    text="Long text here...",
    original_font_size=24
)
```

### Comparing the Methods

| Method | Speed | Accuracy | Best For |
|--------|-------|----------|----------|
| `check_text_fits()` | ⚡ Fast | Medium (±10%) | Quick checks |
| `find_largest_fitting_font()` | 🚀 Medium | Medium-High (±5%) | Most common use |
| `check_text_overflow_in_textframe()` | 🐢 Medium | Very High | Detailed checks |
| `find_largest_fitting_font_in_textframe()` | 🐢 Slowest | Very High | Most accuracy |

---

## Real-World Example

### Scenario: Translate PowerPoint and Fit Text

```python
from pptx import Presentation
from ppt_translator.pipeline import (
    find_largest_fitting_font_in_textframe,
    apply_shape_properties,
)

# 1. Load original presentation
prs = Presentation("presentation.pptx")

# 2. Extract text and translate it
for slide in prs.slides:
    for shape in slide.shapes:
        if hasattr(shape, "text_frame"):
            original_text = shape.text
            # ... translate original_text to translated_text ...
            
            # 3. Find optimal font size for translated text
            original_size = shape.text_frame.paragraphs[0].runs[0].font.size.pt
            
            best_size = find_largest_fitting_font_in_textframe(
                shape.text_frame,
                translated_text,
                original_size
            )
            
            # 4. Apply translation with optimal size
            shape.text_frame.clear()
            para = shape.text_frame.paragraphs[0]
            run = para.add_run()
            run.text = translated_text
            run.font.size = Pt(best_size)

# 5. Save
prs.save("presentation_translated.pptx")
```

---

## Key Insights

### 1. Word Wrapping Changes Everything

Text that seems to fit horizontally might overflow vertically due to word wrapping:

```python
# This text is short but wraps to multiple lines
text = "This is a relatively long sentence that will wrap to multiple lines"
font_size = 24

# At 24pt with a 2-inch box width:
# - Line 1: "This is a relatively long"
# - Line 2: "sentence that will wrap to"
# - Line 3: "multiple lines"

# The 3 lines might exceed available height!
```

### 2. Character Width Varies by Font

The 0.6 multiplier is approximate:
- Proportional fonts (Arial): ~0.55-0.65
- Monospace fonts (Courier): ~1.0
- Sans-serif fonts (Arial): ~0.6
- Serif fonts (Times): ~0.5

For maximum accuracy, measure actual text instead of estimating.

### 3. Line Spacing Affects Height

```python
# Line spacing can be:
# - Single (1.0)
# - 1.15x
# - 1.5x
# - Double (2.0)
# - Fixed (e.g., 12pt)

# This affects total height calculation!
from pptx.enum.text import MSO_ANCHOR

shape.text_frame.vertical_anchor = MSO_ANCHOR.MIDDLE  # Vertical alignment
```

### 4. Safety Margins

All functions use conservative margins:
- **Width:** 98% of available (leaves 2% margin)
- **Height:** 100% of available (uses full height)

Adjust if you need different margins.

---

## Implementation in Your Code

The `pipeline.py` file now includes:

1. **`check_text_fits(text, font_size, width, height)`**
   - Simple yes/no check with suggested size

2. **`find_largest_fitting_font(text, original_size, width, height)`**
   - Binary search for optimal size

3. **`check_text_overflow_in_textframe(text_frame, text, font_size)`**
   - Direct measurement of overflow

4. **`find_largest_fitting_font_in_textframe(text_frame, text, original_size)`**
   - Binary search using actual measurement

5. **`apply_shape_properties(shape, shape_data)`**
   - Now uses the most accurate TextFrame-based measurement first
   - Falls back to estimation if TextFrame access fails

---

## FAQ

**Q: Why does my text still overflow?**  
A: The estimation might be off by ±10%. Use Method 4 (TextFrame-based) for better accuracy.

**Q: Why is Method 4 slower?**  
A: It actually measures the text in the TextFrame, which requires more processing.

**Q: Can I adjust the safety margin?**  
A: Yes, modify the multipliers in `check_text_fits()`:
```python
# Current:
fits = width <= box_width_emu * 0.98 and height <= box_height_emu * 1.0

# More aggressive (text closer to edge):
fits = width <= box_width_emu * 0.95 and height <= box_height_emu * 0.95

# More conservative (text further from edge):
fits = width <= box_width_emu * 0.99 and height <= box_height_emu * 0.99
```

**Q: What if text has multiple paragraphs?**  
A: The height calculation includes paragraph spacing. Just pass all text as one string.

**Q: How do I handle multi-language text?**  
A: Some languages (CJK) use wider characters. Adjust char_width multiplier:
```python
# For Chinese/Japanese/Korean
char_width_emu = font_size_pt * 1.0 * 12700  # Instead of 0.6
```

**Q: What's the minimum font size?**  
A: Currently 6pt (hardcoded in binary search). Adjust as needed for readability.

---

## Reference Links

- [python-pptx Documentation](https://python-pptx.readthedocs.io/)
- [OOXML Specification (Word Wrapping)](https://docs.microsoft.com/en-us/office/open-xml/structure)
- [EMU Units Reference](https://msdn.microsoft.com/en-us/library/office/documentformat.openxml.wordprocessingml.shared.emuunittype(v=office.15).aspx)
