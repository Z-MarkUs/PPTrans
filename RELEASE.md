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

```bash
# Install twine
pip install twine

# Upload to PyPI
twine upload dist/ppt_translator-*.whl dist/ppt_translator-*.tar.gz

# Or upload to TestPyPI first
twine upload --repository testpypi dist/ppt_translator-*.whl dist/ppt_translator-*.tar.gz
```

### Creating GitHub Release

1. Tag the release:
   ```bash
   git tag -a v1.0.0 -m "Release version 1.0.0"
   git push origin v1.0.0
   ```

2. Create release on GitHub with:
   - Release notes
   - Upload Python packages (.whl, .tar.gz)
   - Upload macOS apps (.app bundles or .dmg)
   - Upload Windows executable (.exe)
   - Upload Linux executable (if applicable)

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

