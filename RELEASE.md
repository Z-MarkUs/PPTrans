# Release Guide

## Version 1.0.0

### Building Release Packages

#### 1. Python Package (pip installable)

```bash
# Install build tools
pip install --upgrade pip setuptools wheel build

# Build source distribution and wheel
python -m build

# Outputs:
# - dist/ppt_translator-1.0.0.tar.gz (source distribution)
# - dist/ppt_translator-1.0.0-py3-none-any.whl (wheel)
```

#### 2. macOS Applications

**Apple Silicon (arm64):**
```bash
arch -arm64 python3 build_app.py macos arm64
# Output: dist/PPT-Translator-arm64.app
```

**Intel (x86_64):**
```bash
arch -x86_64 python3 build_app.py macos x86_64
# Output: dist/PPT-Translator-x86_64.app
```

**Universal Binary:**
```bash
python3 build_app.py macos universal
# Output: dist/PPT-Translator.app (runs on both architectures)
```

**Using build script:**
```bash
./build.sh
# Automatically builds for both architectures on macOS
```

#### 3. Windows Executable

```bash
# On Windows
python build_app.py windows
# Output: dist/PPT-Translator.exe

# Or use batch script
build.bat
```

#### 4. Linux Executable

```bash
python3 build_app.py linux
# Output: dist/ppt-translator
```

### Release Checklist

- [ ] Update version in `pyproject.toml` and `setup.py`
- [ ] Update `CHANGELOG.md` (if exists)
- [ ] Run tests: `pytest`
- [ ] Build Python package: `python -m build`
- [ ] Build macOS apps (arm64 and x86_64)
- [ ] Build Windows executable
- [ ] Test installations on each platform
- [ ] Create GitHub release with assets
- [ ] Upload to PyPI: `twine upload dist/*`

### Publishing to PyPI

#### Automated (via GitHub Actions)

The GitHub Actions workflow will automatically publish to PyPI when you create a release, **if** you've set up the `PYPI_API_TOKEN` secret.

**Setup (one-time):**
1. Create PyPI account: https://pypi.org/account/register/
2. Create API token: https://pypi.org/manage/account/
3. Add token to GitHub Secrets:
   - Go to: Settings → Secrets and variables → Actions
   - Add secret: `PYPI_API_TOKEN` = `pypi-xxxxx...`

**Then:**
- Create a GitHub release (via `./release.sh` or manually)
- The workflow will automatically build and publish to PyPI

See `PYPI_SETUP.md` for detailed setup instructions.

#### Manual Upload

```bash
# Install twine
pip install twine

# Upload to PyPI
twine upload dist/ppt_translator-*.whl dist/ppt_translator-*.tar.gz

# Or upload to TestPyPI first (recommended for testing)
twine upload --repository testpypi dist/ppt_translator-*.whl dist/ppt_translator-*.tar.gz
```

### Creating GitHub Release

#### Option 1: Automated Script (Recommended)

```bash
# Make script executable (first time only)
chmod +x release.sh

# Run release script
./release.sh
```

This script will:
- Build Python packages
- Create and push git tag
- Create GitHub release with all assets
- Upload files automatically

#### Option 2: Manual Process

1. **Tag the release:**
   ```bash
   git tag -a v1.0.0 -m "Release version 1.0.0"
   git push origin v1.0.0
   ```

2. **Create release on GitHub:**
   - Go to: https://github.com/Z-MarkUs/PPTrans/releases/new
   - Select tag: `v1.0.0`
   - Add title and description
   - Upload files from `dist/` directory:
     - Python packages (.whl, .tar.gz)
     - macOS apps (.app bundles)
     - Windows executable (.exe)
     - Linux executable (if applicable)
   - Click "Publish release"

#### Option 3: GitHub CLI

```bash
# Install GitHub CLI first: brew install gh (macOS)
gh release create v1.0.0 \
  --title "PPT Translator v1.0.0" \
  --notes-file RELEASE_NOTES.md \
  dist/*
```

See `GITHUB_RELEASE.md` for detailed instructions.

### Distribution Files

After building, the `dist/` directory will contain:

**Python Packages:**
- `ppt_translator-1.0.0-py3-none-any.whl`
- `ppt_translator-1.0.0.tar.gz`

**macOS:**
- `PPT-Translator-arm64.app` (Apple Silicon)
- `PPT-Translator-x86_64.app` (Intel)
- `PPT-Translator.app` (Universal, if built)

**Windows:**
- `PPT-Translator.exe`

**Linux:**
- `ppt-translator`

### Notes

- PyInstaller creates large executables (~100-200MB) due to bundled Python and dependencies
- macOS apps may need code signing for distribution outside App Store
- Windows executables may trigger antivirus warnings (false positives)
- Test all builds on their respective platforms before release

