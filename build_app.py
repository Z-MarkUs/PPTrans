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
    
    # Check if we're trying to cross-compile x86_64 on arm64
    # GitHub Actions macOS runners are arm64-only, so we can't build x86_64 binaries
    import os
    
    current_arch = platform.machine()
    platform_str = platform.platform().lower()
    
    # Check multiple ways to detect arm64 (platform.machine() may vary)
    is_arm64 = (
        current_arch == "arm64" or 
        current_arch == "aarch64" or
        "arm64" in str(current_arch).lower() or
        "arm64" in platform_str or
        "aarch64" in platform_str or
        (hasattr(platform, 'processor') and "arm" in str(platform.processor()).lower())
    )
    
    # Also check environment variables that GitHub Actions might set
    runner_arch = os.environ.get("RUNNER_ARCH", "").lower()
    if "arm" in runner_arch or "aarch" in runner_arch:
        is_arm64 = True
    
    # Debug output
    if arch == "x86_64":
        print(f"[DEBUG] Current arch (platform.machine()): {current_arch}")
        print(f"[DEBUG] Platform string: {platform_str}")
        print(f"[DEBUG] Detected as arm64: {is_arm64}")
    
    if arch == "x86_64" and is_arm64:
        print("[WARN] Cannot build x86_64 on arm64 machine.")
        print(f"[WARN] Detected architecture: {current_arch}")
        print("[WARN] Native dependencies (e.g., PIL) are compiled for arm64 only.")
        print("[WARN] x86_64 builds must be done on an Intel Mac or with Rosetta 2.")
        print("[WARN] Skipping x86_64 build.")
        sys.exit(0)  # Exit gracefully, don't fail the build
    
    # PyInstaller options for macOS app
    # Note: Use --onedir instead of --onefile for macOS .app bundles (PyInstaller deprecation)
    args = [
        "main.py",
        "--name=PPTrans",
        "--onedir",  # Use onedir for macOS .app bundles (onefile is deprecated)
        "--windowed",  # No console window
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
        # Don't specify entitlements file if not needed (omit instead of "NONE")
    ])
    
    PyInstaller.__main__.run(args)
    
    # Create .app bundle structure
    dist_dir = Path("dist")
    app_name = "PPTrans.app"
    app_path = dist_dir / app_name
    
    if app_path.exists():
        print(f"[OK] macOS app created: {app_path}")
    else:
        print("[WARN] App bundle may need manual creation")


def build_windows_app():
    """Build Windows executable."""
    print("Building Windows executable...")
    
    args = [
        "main.py",
        "--name=PPTrans",
        "--onefile",
        "--console",  # Show console for Windows
        # Don't specify icon if not available (omit instead of "NONE")
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
    exe_path = dist_dir / "PPTrans.exe"
    
    if exe_path.exists():
        # Use plain text for Windows console compatibility
        print(f"[OK] Windows executable created: {exe_path}")
    else:
        print("[WARN] Executable not found")


def build_linux_app():
    """Build Linux executable."""
    print("Building Linux executable...")
    
    args = [
        "main.py",
        "--name=pptrans",
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
    exe_path = dist_dir / "pptrans"
    
    if exe_path.exists():
        print(f"[OK] Linux executable created: {exe_path}")
    else:
        print("[WARN] Executable not found")


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

