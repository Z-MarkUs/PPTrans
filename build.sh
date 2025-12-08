#!/bin/bash
# Build script for PPT Translator

set -e

echo "🚀 Building PPT Translator..."

# Check Python version
python3 --version

# Install build dependencies
echo "📦 Installing build dependencies..."
pip install --upgrade pip setuptools wheel build pyinstaller

# Build source distribution and wheel
echo "📦 Building Python package..."
python3 -m build

# Build apps based on platform
PLATFORM=$(uname -s)
ARCH=$(uname -m)

echo "🖥️  Platform: $PLATFORM, Architecture: $ARCH"

if [[ "$PLATFORM" == "Darwin" ]]; then
    echo "🍎 Building macOS apps..."
    
    # Build for Apple Silicon
    if [[ "$ARCH" == "arm64" ]] || command -v arch &> /dev/null; then
        echo "  Building for Apple Silicon (arm64)..."
        arch -arm64 python3 build_app.py macos arm64 || python3 build_app.py macos arm64
    fi
    
    # Build for Intel
    if [[ "$ARCH" == "x86_64" ]] || command -v arch &> /dev/null; then
        echo "  Building for Intel (x86_64)..."
        arch -x86_64 python3 build_app.py macos x86_64 || python3 build_app.py macos x86_64
    fi
    
    echo "✅ macOS builds complete"
elif [[ "$PLATFORM" == "Linux" ]]; then
    echo "🐧 Building Linux executable..."
    python3 build_app.py linux
    echo "✅ Linux build complete"
elif [[ "$PLATFORM" == MINGW* ]] || [[ "$PLATFORM" == MSYS* ]] || [[ "$PLATFORM" == CYGWIN* ]]; then
    echo "🪟 Building Windows executable..."
    python3 build_app.py windows
    echo "✅ Windows build complete"
else
    echo "⚠️  Unknown platform: $PLATFORM"
fi

echo ""
echo "✨ Build complete! Check the 'dist' directory for outputs."
echo "📦 Python packages: dist/*.whl, dist/*.tar.gz"
echo "🖥️  Executables: dist/PPT-Translator*"

