@echo off
REM Build script for PPT Translator (Windows)

echo 🚀 Building PPT Translator...

REM Check Python version
python --version

REM Install build dependencies
echo 📦 Installing build dependencies...
pip install --upgrade pip setuptools wheel build pyinstaller

REM Build source distribution and wheel
echo 📦 Building Python package...
python -m build

REM Build Windows executable
echo 🪟 Building Windows executable...
python build_app.py windows

echo.
echo ✨ Build complete! Check the 'dist' directory for outputs.
echo 📦 Python packages: dist\*.whl, dist\*.tar.gz
echo 🖥️  Executable: dist\PPT-Translator.exe

pause

