# PowerPoint Text Fitting - Quick Reference

## Three Ways to Check Text Overflow

### 1️⃣ Estimation (Fastest)
```python
from ppt_translator.pipeline import check_text_fits

fits, suggested_size = check_text_fits(
    text="Hello World",
    font_size_pt=24,
    box_width_emu=1828800,
    box_height_emu=914400
)
```
✅ Fast  
❌ ±10% accuracy  
👉 Use for: Quick checks, performance-critical code

---

### 2️⃣ Binary Search + Estimation (Balanced)
```python
from ppt_translator.pipeline import find_largest_fitting_font

best_size = find_largest_fitting_font(
    text="Hello World",
    original_font_size=24,
    box_width_emu=1828800,
    box_height_emu=914400
)
```
✅ Medium speed  
✅ Medium accuracy (±5%)  
👉 Use for: Most common use cases

---

### 3️⃣ TextFrame Measurement (Most Accurate)
```python
from ppt_translator.pipeline import find_largest_fitting_font_in_textframe

best_size = find_largest_fitting_font_in_textframe(
    text_frame=shape.text_frame,
    text="Hello World",
    original_font_size=24
)
```
✅ Very accurate (actual measurement)  
❌ Slower  
👉 Use for: Critical accuracy needed, when time is not an issue

---

## Unit Conversion Cheatsheet

```python
from pptx.util import Pt, Inches, Cm, Mm

# Convert TO EMU (internal PowerPoint unit)
width_emu = Inches(5)           # 5 inches
height_emu = Cm(10)             # 10 centimeters
size_emu = Pt(24)               # 24 points (font)

# Convert FROM EMU (shape properties are always in EMU)
width_in_inches = shape.width / 914400
font_size_in_pt = run.font.size.pt  # Automatically converted

# Quick conversion formulas
# 1 point = 12,700 EMU
# 1 inch = 914,400 EMU (72pt)
# 1 cm = 360,000 EMU
```

---

## Real Code Example

```python
from pptx import Presentation
from pptx.util import Pt
from ppt_translator.pipeline import find_largest_fitting_font_in_textframe

# Open presentation
prs = Presentation("slide.pptx")
slide = prs.slides[0]
shape = slide.shapes[0]  # First shape with text

# Get current text and size
original_text = shape.text
original_size = shape.text_frame.paragraphs[0].runs[0].font.size.pt

# Translate (your translation code here)
translated_text = "Translated text here..."

# Find optimal font size for translated text
best_size = find_largest_fitting_font_in_textframe(
    shape.text_frame,
    translated_text,
    original_size
)

# Apply translation with optimal size
shape.text = translated_text
for paragraph in shape.text_frame.paragraphs:
    for run in paragraph.runs:
        run.font.size = Pt(best_size)

# Save
prs.save("slide_translated.pptx")
```

---

## Common Issues & Solutions

### Issue: Text Still Overflows
**Solution:** Use TextFrame-based method (Method 3) instead of estimation
```python
# ❌ Was using:
best_size = find_largest_fitting_font(...)

# ✅ Use instead:
best_size = find_largest_fitting_font_in_textframe(...)
```

### Issue: Font Too Small
**Solution:** Adjust the safety margin
```python
# In pipeline.py, find check_text_fits() function
# Change these lines:
fits = estimated_width <= box_width_emu * 0.98 and estimated_height <= box_height_emu * 1.0
# To more aggressive:
fits = estimated_width <= box_width_emu * 0.99 and estimated_height <= box_height_emu * 1.05
```

### Issue: Performance Issues
**Solution:** Use estimation method for batch processing
```python
# ❌ Slow for many shapes:
for shape in all_shapes:
    size = find_largest_fitting_font_in_textframe(...)  # Slow

# ✅ Fast for many shapes:
for shape in all_shapes:
    size = find_largest_fitting_font(...)  # Much faster
```

### Issue: Different Languages (CJK)
**Solution:** Adjust character width for wider characters
```python
# For Chinese/Japanese/Korean, modify:
char_width_emu = font_size_pt * 0.6 * 12700  # Default
# To:
char_width_emu = font_size_pt * 1.0 * 12700  # For CJK
```

---

## Parameter Reference

### check_text_fits()
```python
check_text_fits(
    text: str,              # Text to check
    font_size_pt: float,    # Font size in points
    box_width_emu: int,     # Box width in EMU
    box_height_emu: int,    # Box height in EMU
    font_name: str = "Arial"  # Font family (affects width calc)
) -> tuple[bool, float]    # (fits, suggested_size)
```

### find_largest_fitting_font()
```python
find_largest_fitting_font(
    text: str,
    original_font_size: float,
    box_width_emu: int,
    box_height_emu: int,
    font_name: str = "Arial"
) -> float                 # Best font size
```

### find_largest_fitting_font_in_textframe()
```python
find_largest_fitting_font_in_textframe(
    text_frame,            # From shape.text_frame
    text: str,
    original_font_size: float,
    max_iterations: int = 10  # Binary search iterations
) -> float                 # Best font size
```

### check_text_overflow_in_textframe()
```python
check_text_overflow_in_textframe(
    text_frame,
    text: str,
    font_size_pt: float
) -> tuple[bool, float]    # (fits, overflow_ratio)
                          # ratio > 1.0 = overflow
```

---

## Performance Comparison

```
Checking 100 shapes:

Method 1 (estimation):          ~10ms
Method 2 (binary search est):   ~50ms (10 iterations)
Method 3 (textframe check):     ~100ms
Method 4 (binary search tf):    ~500ms (10 iterations × textframe)

Use Method 1 or 2 for interactive performance.
Use Method 3 or 4 for one-time processing with high accuracy.
```

---

## What Happens in apply_shape_properties()

The new implementation automatically:

1. **Tries TextFrame measurement first** (most accurate)
   - If successful, uses TextFrame-based binary search
   
2. **Falls back to estimation** (if TextFrame access fails)
   - Uses estimation-based binary search
   
3. **Always checks original font size**
   - Doesn't assume original was correct
   - Finds largest size that actually fits

```
apply_shape_properties()
    ↓
Does shape have text?
    ├─ YES → Check if needs sizing
    │   ├─ Try TextFrame method
    │   │   ├─ Success → Use result ✅
    │   │   └─ Fail → Fallback to estimation
    │   └─ Use estimation method ✅
    └─ NO → Skip font sizing
```

---

## When to Use Each Method

| Situation | Recommended Method |
|-----------|-------------------|
| Single shape, need accuracy | Method 4 (TextFrame binary search) |
| Multiple shapes, balance speed/accuracy | Method 2 (Estimation binary search) |
| Batch processing many shapes | Method 1 (Quick estimation) |
| Check one specific size | Method 3 (TextFrame check) |
| Real-time translation | Method 2 (Fast binary search) |
| Publication-quality output | Method 4 (Most accurate) |

---

## Tips & Tricks

### Preserve Original Font While Sizing
```python
# Don't change font, only size
for paragraph in shape.text_frame.paragraphs:
    for run in paragraph.runs:
        run.font.size = Pt(best_size)
        # run.font.name stays unchanged!
```

### Account for Multiple Paragraphs
```python
# Text with paragraphs needs extra height
text_with_paragraphs = "Line 1\nLine 2\nLine 3"

best_size = find_largest_fitting_font_in_textframe(
    shape.text_frame,
    text_with_paragraphs,  # Includes \n characters
    original_size
)
```

### Work with Word Wrapping
```python
# Always enable word wrapping
shape.text_frame.word_wrap = True

# Then measure - handles line wrapping automatically
best_size = find_largest_fitting_font_in_textframe(
    shape.text_frame,
    "Long text that will wrap...",
    24
)
```

### Minimum Font Size
```python
# Current minimum is 6pt
# To change, modify find_largest_fitting_font():
min_size = 8.0  # Instead of 6.0
```
