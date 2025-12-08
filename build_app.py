#!/usr/bin/env python3
"""Build standalone applications for PPT Translator."""
import subprocess
import sys
import platform
from pathlib import Path

try:
    import PyInstaller.__main__
except ImportError:
    print("PyInstaller is required for building apps. Install with: pip install pyinstaller")
    sys.exit(1)


def build_macos_app(arch: str = "universal"):
    """Build macOS app bundle.
    
    Args:
        arch: Architecture - "arm64", "x86_64", or "universal"
    """
    print(f"Building macOS app for {arch}...")
    
    # PyInstaller options for macOS app
    args = [
        "main.py",
        "--name=PPT-Translator",
        "--onefile",
        "--windowed",  # No console window
        "--icon=NONE",  # Add icon file if available
        f"--add-data=README.md:.",  # Include README
        "--hidden-import=pptx",
        "--hidden-import=openai",
        "--hidden-import=anthropic",
        "--hidden-import=yaml",
        "--hidden-import=PIL",
        "--collect-all=pptx",
        "--collect-all=openai",
        "--collect-all=anthropic",
    ]
    
    if arch == "arm64":
        args.extend(["--target-arch=arm64"])
    elif arch == "x86_64":
        args.extend(["--target-arch=x86_64"])
    # universal builds both architectures
    
    # macOS-specific options
    args.extend([
        "--osx-bundle-identifier=com.ppttranslator.app",
        "--osx-entitlements-file=NONE",
    ])
    
    PyInstaller.__main__.run(args)
    
    # Create .app bundle structure
    dist_dir = Path("dist")
    app_name = "PPT-Translator.app"
    app_path = dist_dir / app_name
    
    if app_path.exists():
        print(f"✅ macOS app created: {app_path}")
    else:
        print("⚠️  App bundle may need manual creation")


def build_windows_app():
    """Build Windows executable."""
    print("Building Windows executable...")
    
    args = [
        "main.py",
        "--name=PPT-Translator",
        "--onefile",
        "--console",  # Show console for Windows
        "--icon=NONE",  # Add .ico file if available
        f"--add-data=README.md;.",  # Windows uses semicolon
        "--hidden-import=pptx",
        "--hidden-import=openai",
        "--hidden-import=anthropic",
        "--hidden-import=yaml",
        "--hidden-import=PIL",
        "--collect-all=pptx",
        "--collect-all=openai",
        "--collect-all=anthropic",
    ]
    
    PyInstaller.__main__.run(args)
    
    dist_dir = Path("dist")
    exe_path = dist_dir / "PPT-Translator.exe"
    
    if exe_path.exists():
        print(f"✅ Windows executable created: {exe_path}")
    else:
        print("⚠️  Executable not found")


def build_linux_app():
    """Build Linux executable."""
    print("Building Linux executable...")
    
    args = [
        "main.py",
        "--name=ppt-translator",
        "--onefile",
        "--console",
        f"--add-data=README.md:.",  # Linux uses colon
        "--hidden-import=pptx",
        "--hidden-import=openai",
        "--hidden-import=anthropic",
        "--hidden-import=yaml",
        "--hidden-import=PIL",
        "--collect-all=pptx",
        "--collect-all=openai",
        "--collect-all=anthropic",
    ]
    
    PyInstaller.__main__.run(args)
    
    dist_dir = Path("dist")
    exe_path = dist_dir / "ppt-translator"
    
    if exe_path.exists():
        print(f"✅ Linux executable created: {exe_path}")
    else:
        print("⚠️  Executable not found")


def main():
    """Main build function."""
    if len(sys.argv) < 2:
        print("Usage: python build_app.py <platform> [arch]")
        print("Platforms: macos, windows, linux")
        print("macOS arch options: arm64, x86_64, universal")
        sys.exit(1)
    
    platform_name = sys.argv[1].lower()
    arch = sys.argv[2].lower() if len(sys.argv) > 2 else None
    
    if platform_name == "macos":
        if arch:
            build_macos_app(arch)
        else:
            # Build for current architecture
            current_arch = platform.machine()
            if current_arch == "arm64":
                build_macos_app("arm64")
            else:
                build_macos_app("x86_64")
    elif platform_name == "windows":
        build_windows_app()
    elif platform_name == "linux":
        build_linux_app()
    else:
        print(f"Unknown platform: {platform_name}")
        sys.exit(1)


if __name__ == "__main__":
    main()

