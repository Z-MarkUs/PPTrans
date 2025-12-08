# Creating a GitHub Release

## Step-by-Step Guide

### Method 1: Using GitHub Web Interface (Recommended)

#### 1. Build and Test Your Release

```bash
# Build Python package
python -m build

# Build macOS apps (if on macOS)
./build.sh

# Build Windows executable (if on Windows)
build.bat

# Test the installation
pip install dist/ppt_translator-*.whl
ppt-translator --help
```

#### 2. Create and Push Git Tag

```bash
# Create an annotated tag
git tag -a v1.0.0 -m "Release version 1.0.0"

# Push tag to GitHub
git push origin v1.0.0

# Or push all tags
git push --tags
```

#### 3. Create Release on GitHub

1. **Go to your repository on GitHub**
   - Navigate to: `https://github.com/Z-MarkUs/PPTrans`

2. **Click on "Releases"**
   - On the right sidebar, click "Releases"
   - Or go directly to: `https://github.com/Z-MarkUs/PPTrans/releases`

3. **Click "Draft a new release"**
   - Or "Create a new release" button

4. **Fill in Release Details**
   - **Tag version**: Select `v1.0.0` (or create new tag)
   - **Release title**: `v1.0.0` or `PPT Translator v1.0.0`
   - **Description**: Paste release notes (see template below)

5. **Upload Release Assets**
   - Click "Attach binaries" or drag & drop files
   - Upload:
     - `dist/ppt_translator-1.0.0-py3-none-any.whl`
     - `dist/ppt_translator-1.0.0.tar.gz`
     - `dist/PPT-Translator-arm64.app` (if built)
     - `dist/PPT-Translator-x86_64.app` (if built)
     - `dist/PPT-Translator.exe` (if built)
     - `dist/ppt-translator` (if built)

6. **Publish Release**
   - Check "Set as the latest release" (if this is your latest)
   - Click "Publish release"

### Method 2: Using GitHub CLI (gh)

#### 1. Install GitHub CLI

```bash
# macOS
brew install gh

# Windows (via winget)
winget install GitHub.cli

# Linux
# See: https://github.com/cli/cli/blob/trunk/docs/install_linux.md
```

#### 2. Authenticate

```bash
gh auth login
```

#### 3. Create Release

```bash
# Create release with assets
gh release create v1.0.0 \
  --title "PPT Translator v1.0.0" \
  --notes-file RELEASE_NOTES.md \
  dist/ppt_translator-1.0.0-py3-none-any.whl \
  dist/ppt_translator-1.0.0.tar.gz \
  dist/PPT-Translator-arm64.app \
  dist/PPT-Translator-x86_64.app \
  dist/PPT-Translator.exe

# Or create draft release first
gh release create v1.0.0 \
  --title "PPT Translator v1.0.0" \
  --notes-file RELEASE_NOTES.md \
  --draft \
  dist/*
```

### Method 3: Automated Script

Create a script to automate the process:

```bash
#!/bin/bash
# release.sh - Automated GitHub release script

set -e

VERSION="1.0.0"
TAG="v${VERSION}"

echo "🚀 Creating release ${TAG}..."

# Build everything
echo "📦 Building packages..."
python -m build

# Create tag
echo "🏷️  Creating tag..."
git tag -a "${TAG}" -m "Release version ${VERSION}"
git push origin "${TAG}"

# Create release with GitHub CLI
if command -v gh &> /dev/null; then
    echo "📤 Creating GitHub release..."
    gh release create "${TAG}" \
        --title "PPT Translator ${TAG}" \
        --notes-file RELEASE_NOTES.md \
        dist/*
    echo "✅ Release created!"
else
    echo "⚠️  GitHub CLI not found. Please create release manually:"
    echo "   https://github.com/Z-MarkUs/PPTrans/releases/new"
fi
```

## Release Notes Template

Create a `RELEASE_NOTES.md` file:

```markdown
# PPT Translator v1.0.0

## 🎉 First Release!

### ✨ Features

- **Multi-Provider Support**: DeepSeek, OpenAI, Anthropic, and Grok
- **Vision-Based Review**: GPT-5.1 powered quality review with iterative refinement
- **Layout-Aware Translation**: Auto-adjusts font sizes to fit translated text
- **Translation Memory**: Ensures consistency across slides
- **Interactive Review Mode**: Edit translations and regenerate PPTs
- **User-Defined Glossary**: Preset preferred translations
- **Batch Processing**: Translate entire directories

### 📦 Installation

**Via pip:**
```bash
pip install ppt-translator
```

**Standalone Apps:**
- macOS Apple Silicon: Download `PPT-Translator-arm64.app`
- macOS Intel: Download `PPT-Translator-x86_64.app`
- Windows: Download `PPT-Translator.exe`

### 🚀 Quick Start

```bash
ppt-translator presentation.pptx --provider openai --source-lang zh --target-lang en
```

### 📋 Requirements

- Python 3.10+ (for pip installation)
- API keys for your chosen provider(s)

### 🔗 Links

- [Documentation](https://github.com/Z-MarkUs/PPTrans#readme)
- [Issues](https://github.com/Z-MarkUs/PPTrans/issues)

### 🙏 Credits

Built with ❤️ using modern LLM providers.
```

## Quick Reference

### Create Tag
```bash
git tag -a v1.0.0 -m "Release v1.0.0"
git push origin v1.0.0
```

### Create Release (GitHub CLI)
```bash
gh release create v1.0.0 --title "v1.0.0" --notes "Release notes" dist/*
```

### Create Release (Web)
1. Go to: `https://github.com/Z-MarkUs/PPTrans/releases/new`
2. Select tag: `v1.0.0`
3. Add title and description
4. Upload files from `dist/` directory
5. Click "Publish release"

## Best Practices

1. **Version Numbering**: Use [Semantic Versioning](https://semver.org/)
   - `MAJOR.MINOR.PATCH` (e.g., `1.0.0`)
   - Major: Breaking changes
   - Minor: New features (backward compatible)
   - Patch: Bug fixes

2. **Release Notes**: Include:
   - What's new
   - Breaking changes (if any)
   - Installation instructions
   - Known issues

3. **Pre-Release Testing**:
   - Test on target platforms
   - Verify all features work
   - Check file sizes are reasonable

4. **Assets Organization**:
   - Name files clearly: `PPT-Translator-v1.0.0-macos-arm64.app`
   - Include checksums (optional)
   - Provide both wheel and source distribution

5. **Release Frequency**:
   - Major releases: Significant features or breaking changes
   - Minor releases: New features, improvements
   - Patch releases: Bug fixes, security updates

