# PPT Translator v1.0.0

## 🎉 First Release!

PPT Translator is now available on PyPI! Translate PowerPoint presentations using modern LLM providers with advanced features like vision-based quality review, layout-aware translation, and interactive editing.

---

## ✨ Key Features

### 🚀 Core Translation
- **Multi-Provider Support**: DeepSeek, OpenAI, Anthropic, and Grok
- **Batch Processing**: Translate entire directories of presentations
- **Format Preservation**: Maintains fonts, colors, spacing, tables, and alignment
- **Smart Caching**: Avoids duplicate API calls for repeated strings

### 🔍 Vision-Based Quality Review
- **Pre-Translation Analysis**: LLM analyzes original slides to plan translation strategy
- **Post-Translation Review**: Quality scoring (0-10) with user's chosen vision-capable model
- **Iterative Refinement**: Automatically refines translations until quality threshold is met
- **Visual Quality Assessment**: Compares original and translated slides for layout and accuracy

### 🎨 Layout-Aware Translation
- **Auto Font Adjustment**: Automatically scales font sizes when translated text overflows
- **Layout Preservation**: Ensures text fits within original text box boundaries
- **Smart Text Fitting**: Calculates optimal font size and line breaks

### 💾 Translation Memory
- **Consistency Across Slides**: Stores translations in temporary JSON file
- **Shared Memory**: Reuses translations across multiple files in a batch
- **Automatic Cleanup**: Removes memory file after translation completes

### 📝 Interactive Review Mode
- **Review File Generation**: Creates editable JSON/YAML files with all translations
- **Manual Editing**: Edit translations and regenerate PPTs
- **Quality Scores**: Includes quality scores and issues per slide
- **Memory Updates**: User edits automatically update translation memory

### 📚 User-Defined Glossary
- **Preset Translations**: Define preferred translations for specific terms
- **LLM Integration**: Glossary included in translation prompts for better consistency
- **Multiple Formats**: Supports JSON and YAML glossary files

---

## 📦 Installation

### Via pip (Recommended)
```bash
pip install pptrans
```

### Standalone Applications
Download pre-built applications:
- **macOS Apple Silicon** (arm64): `PPT-Translator-arm64.app`
- **macOS Intel** (x86_64): `PPT-Translator-x86_64.app`
- **Windows** (x86): `PPT-Translator.exe`

---

## 🚀 Quick Start

### Basic Translation
```bash
pptrans presentation.pptx --provider openai --source-lang zh --target-lang en
```

### With Vision Review
```bash
pptrans presentation.pptx \
  --provider openai \
  --vision-review \
  --vision-model YOUR_VISION_MODEL_NAME \
  --vision-quality-threshold 8.0
```

### Generate Review File
```bash
pptrans presentation.pptx \
  --provider openai \
  --generate-review \
  --review-format json
```

### Regenerate from Edited Review
```bash
pptrans ./presentations/ \
  --regenerate-from-review translation_review.json
```

---

## 📋 Requirements

- Python 3.10+ (for pip installation)
- API keys for your chosen provider(s):
  - OpenAI: `OPENAI_API_KEY`
  - Anthropic: `ANTHROPIC_API_KEY`
  - DeepSeek: `DEEPSEEK_API_KEY`
  - Grok: `GROK_API_KEY`

---

## 🎯 Use Cases

- **Business Presentations**: Translate corporate decks while preserving branding
- **Educational Materials**: Convert course materials to multiple languages
- **Marketing Content**: Localize marketing presentations for global audiences
- **Technical Documentation**: Translate technical presentations with consistent terminology

---

## 🔧 Configuration

### Environment Variables
Create a `.env` file or export environment variables:

```bash
export OPENAI_API_KEY="sk-..."
export ANTHROPIC_API_KEY="sk-ant-..."
```

### Glossary File
Create a JSON or YAML file with preferred translations:

```json
{
  "tomato": "番茄",
  "potato": "土豆"
}
```

Use with:
```bash
pptrans presentation.pptx --glossary glossary.json
```

---

## 📊 What's Included

- ✅ Multi-provider LLM support
- ✅ Vision-based quality review with AI-guided autofallback
- ✅ Layout-aware translation with auto font adjustment
- ✅ Translation memory for consistency
- ✅ Interactive review mode with editable files
- ✅ User-defined glossary support
- ✅ Batch processing
- ✅ Format preservation (fonts, colors, tables, alignment)
- ✅ Progress tracking and cost estimation (coming soon)

---

## 🐛 Known Limitations

- Slide rendering requires LibreOffice or Pillow (fallback)
- Large presentations may take longer to process
- Vision review requires vision-capable models (users enter their own model name from their provider)
- Some complex PowerPoint features may not be fully preserved

---

## 🙏 Credits

Built with ❤️ using:
- [python-pptx](https://github.com/scanny/python-pptx) for PowerPoint manipulation
- OpenAI, Anthropic, DeepSeek, and Grok for translation
- Modern Python packaging standards

---

## 📖 Documentation

- **Full Documentation**: See [README.md](README.md)
- **Language Support**: See [LANGUAGE_SUPPORT.md](LANGUAGE_SUPPORT.md)

---

## 🔗 Links

- **GitHub Repository**: https://github.com/Z-MarkUs/PPTrans
- **PyPI Package**: https://pypi.org/project/pptrans/
- **Issues**: https://github.com/Z-MarkUs/PPTrans/issues

---

## 📝 Changelog

### v1.1.1 (2026-02-03)

**Maintenance Release**

- 🧹 Removed untested Gradio web interface (CLI-only focus)
- 🧹 Cleaned up test files and temporary artifacts
- 📝 Improved documentation consistency
- 🔒 Enhanced security checks (no exposed credentials)
- 📦 Removed Gradio dependency from requirements

### v1.1.0

**Previous release with multi-provider support and vision review**

### v1.0.0 (2025-12-08)

**Initial Release**

- ✨ Multi-provider LLM translation support
- ✨ Vision-based quality review system
- ✨ Layout-aware translation with auto font adjustment
- ✨ Translation memory for consistency
- ✨ Interactive review mode
- ✨ User-defined glossary support
- ✨ Batch processing capabilities
- ✨ Format preservation (fonts, colors, tables, alignment)
- 📦 PyPI package distribution
- 🖥️ Standalone application builds (macOS, Windows, Linux)

---

## 🎓 Getting Help

- **Documentation**: Check the [README.md](README.md) for detailed usage
- **Issues**: Report bugs or request features on [GitHub Issues](https://github.com/Z-MarkUs/PPTrans/issues)
- **Examples**: See `example_glossary.json` for glossary format examples

---

**Thank you for using PPT Translator! 🚀**

