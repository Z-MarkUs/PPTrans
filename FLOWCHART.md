# PPT Translator - Enhanced Flowchart

## Main Processing Flow

```
┌─────────────────────────────────────────────────────────────┐
│ START: PPT File/Directory Input                            │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│ Initialize:                                                 │
│ - Load Config                                               │
│ - Connect Translation Memory DB                             │
│ - Initialize Progress Tracker                              │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│ Scan for PPT Files (.ppt, .pptx)                          │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
              ┌──────────────┐
              │ Files Found? │
              └──────┬───────┘
                     │
        ┌────────────┴────────────┐
        │                         │
       NO                        YES
        │                         │
        ▼                         ▼
┌──────────────┐    ┌──────────────────────────────────────┐
│ Error: No    │    │ Initialize Progress Tracker:         │
│ Files Found  │    │ - Total Files Count                 │
│              │    │ - Total Slides Count                │
│ [EXIT]       │    │ - Start Timer                       │
└──────────────┘    └────────────┬─────────────────────────┘
                                 │
                                 ▼
                         ┌───────────────┐
                         │ More Files?   │◄──────────────┐
                         └───────┬───────┘               │
                                 │                       │
                    ┌────────────┴────────────┐          │
                   NO                        YES          │
                    │                         │           │
                    ▼                         ▼           │
        ┌──────────────────────┐    ┌──────────────────────┐
        │ Generate Review File │    │ Select Next File     │
        │ (JSON/YAML)          │    │ Update: File X of Y  │
        └──────────┬───────────┘    └──────────┬───────────┘
                   │                            │
                   │                            ▼
                   │                ┌──────────────────────┐
                   │                │ Load PowerPoint File │
                   │                └──────────┬───────────┘
                   │                            │
                   │                            ▼
                   │                ┌──────────────────────┐
                   │                │ Extract All Slides   │
                   │                └──────────┬───────────┘
                   │                            │
                   │                            ▼
                   │                    ┌──────────────┐
                   │                    │ More Slides?  │◄──┐
                   │                    └──────┬───────┘   │
                   │                           │           │
                   │              ┌────────────┴────────┐  │
                   │             NO                    YES   │
                   │              │                      │   │
                   │              ▼                      ▼   │
                   │    ┌──────────────────┐    ┌──────────────────────┐
                   │    │ Save Translated  │    │ Select Next Slide   │
                   │    │ PPT File         │    │ Update: Slide X/Y   │
                   │    └────────┬─────────┘    └──────────┬───────────┘
                   │             │                          │
                   │             ▼                          │
                   │    ┌──────────────────┐               │
                   │    │ Update Progress:  │               │
                   │    │ File Complete     │               │
                   │    └────────┬─────────┘               │
                   │             │                          │
                   └─────────────┴──────────────────────────┘
                                 │
                                 │
                                 ▼
```

## Slide Processing Flow (Per Slide)

```
┌─────────────────────────────────────────────────────────────┐
│ Extract Slide:                                             │
│ - Text Elements                                            │
│ - Tables                                                   │
│ - Formatting Properties                                    │
│ - Layout Constraints (width, height, font size)           │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│ Render Original Slide to Image (PNG)                      │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
              ┌──────────────────┐
              │ Check Translation │
              │ Memory DB        │
              └──────┬───────────┘
                     │
        ┌────────────┴────────────┐
        │                         │
      FOUND                    NOT FOUND
        │                         │
        ▼                         ▼
┌──────────────┐    ┌──────────────────────────────────────┐
│ Use Cached   │    │ Translate Text:                      │
│ Translation  │    │ - Chunk by Structure                 │
└──────┬───────┘    │ - Apply Style Guide                  │
       │            │ - Preserve Context                    │
       └──────┬─────┘                                       │
              │                                             │
              ▼                                             │
┌─────────────────────────────────────────────────────────────┐
│ Layout-Aware Processing                                    │
│ - Calculate text box dimensions                           │
│ - Measure translation length                              │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
              ┌──────────────┐
              │ Translation  │
              │ Fits Layout? │
              └──────┬───────┘
                     │
        ┌────────────┴────────────┐
        │                         │
       NO                        YES
        │                         │
        ▼                         │
┌──────────────────┐              │
│ Auto-Adjust:     │              │
│ - Scale Font     │              │
│ - Line Breaks    │              │
│ - Suggest Reword │              │
└──────┬───────────┘              │
       │                          │
       └──────────────┬───────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│ Rebuild Slide with Translated Text                         │
│ - Apply formatting properties                              │
│ - Set font sizes (adjusted if needed)                      │
│ - Preserve colors, alignment, spacing                      │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│ Render Translated Slide to Image (PNG)                    │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│ Multimodal LLM Review:                                     │
│ - Input: Original Image + Translated Image                │
│ - Analyze: Quality, Layout, Readability                    │
│ - Output: Quality Score (0-10) + Issues List               │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
              ┌──────────────┐
              │ Quality Score│
              │ > Threshold? │
              └──────┬───────┘
                     │
        ┌────────────┴────────────┐
        │                         │
       YES                       NO
        │                         │
        ▼                         ▼
┌──────────────┐         ┌──────────────┐
│ Save to      │         │ Max          │
│ Memory DB    │         │ Iterations   │
└──────┬───────┘         │ Reached?     │
       │                 └──────┬───────┘
       │                        │
       │            ┌───────────┴───────────┐
       │           YES                    NO
       │            │                       │
       │            ▼                       ▼
       │    ┌──────────────┐    ┌──────────────────────┐
       │    │ Flag Low     │    │ Refine Translation:  │
       │    │ Quality for  │    │ - Apply LLM          │
       │    │ Manual Review│    │   Suggestions        │
       │    └──────┬───────┘    │ - Fix Layout Issues  │
       │           │             │ - Improve Quality    │
       │           └──────┬──────┘                      │
       │                  │                             │
       │                  └──────────────┬──────────────┘
       │                                 │
       └─────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│ Collect Slide Results:                                     │
│ - Original Text                                            │
│ - Translated Text                                          │
│ - Quality Score                                            │
│ - Issues Detected                                          │
└────────────────────┬────────────────────────────────────────┘
                     │
                     │ [Loop back to next slide]
                     │
```

## Review & Regeneration Flow

```
┌─────────────────────────────────────────────────────────────┐
│ Calculate & Display:                                       │
│ - API Costs                                                │
│ - Processing Time                                          │
│ - Quality Metrics                                          │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│ Generate Interactive Review File:                         │
│ Format: JSON or YAML                                       │
│ Contents:                                                  │
│ - All translations (original → translated)                 │
│ - Quality scores per slide                                 │
│ - Issues flagged                                           │
│ - Editable fields                                          │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
              ┌──────────────┐
              │ User Reviews │
              │ & Edits File?│
              └──────┬───────┘
                     │
        ┌────────────┴────────────┐
        │                         │
       NO                        YES
        │                         │
        ▼                         ▼
┌──────────────┐    ┌──────────────────────────────────────┐
│ END:         │    │ Load Edited Review File              │
│ Translation  │    └──────────┬───────────────────────────┘
│ Complete     │               │
└──────────────┘               ▼
                       ┌──────────────────┐
                       │ Validate Edits:   │
                       │ - Format Check    │
                       │ - Completeness    │
                       └──────┬───────────┘
                              │
                    ┌─────────┴─────────┐
                    │                   │
                  INVALID             VALID
                    │                   │
                    ▼                   ▼
         ┌──────────────────┐  ┌──────────────────────┐
         │ Show Validation  │  │ Regenerate PPTs from │
         │ Errors           │  │ Edited Translations  │
         └────────┬─────────┘  └──────────┬───────────┘
                  │                       │
                  └───────────┬───────────┘
                              │
                              ▼
                  ┌──────────────────────┐
                  │ Update Translation   │
                  │ Memory with User    │
                  │ Edits               │
                  └──────────┬───────────┘
                             │
                             ▼
                    ┌──────────────────┐
                    │ END: Final       │
                    │ Translation      │
                    │ Complete         │
                    └──────────────────┘
```

## Feature Integration Points

### 1. **Layout-Aware Translation** (Green)
- Extracts layout constraints during slide extraction
- Checks if translation fits before rebuilding
- Auto-adjusts font size and line breaks

### 2. **Translation Memory** (Purple)
- Checks memory before translating
- Saves successful translations
- Updates with user edits

### 3. **Interactive Review Mode** (Teal)
- Generates review file after batch processing
- Allows manual edits
- Regenerates PPTs from edited file

### 4. **Progress Tracking** (Blue)
- Updates at file and slide level
- Shows ETA and completion status
- Displays cost estimates

### 5. **Multimodal Review** (Red)
- Visual quality check with LLM
- Iterative refinement loop
- Quality scoring and flagging

