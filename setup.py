"""Setup script for PPT Translator."""
from setuptools import setup, find_packages
from pathlib import Path

# Read README
readme_file = Path(__file__).parent / "README.md"
long_description = readme_file.read_text(encoding="utf-8") if readme_file.exists() else ""

# Read requirements
requirements_file = Path(__file__).parent / "requirements.txt"
requirements = []
if requirements_file.exists():
    requirements = [
        line.strip()
        for line in requirements_file.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]
    # Remove pytest from runtime requirements
    requirements = [r for r in requirements if not r.startswith("pytest")]

setup(
    name="ppt-translator",
    version="1.0.0",
    description="Translate PowerPoint presentations using modern LLM providers",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="Hehan Zhao",
    author_email="80203549+Z-MarkUs@users.noreply.github.com",
    url="https://github.com/Z-MarkUs/PPTrans",
    packages=find_packages(exclude=["tests", "tests.*"]),
    python_requires=">=3.10",
    install_requires=requirements,
    entry_points={
        "console_scripts": [
            "ppt-translator=ppt_translator.cli:main",
        ],
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Office/Business",
        "Topic :: Text Processing :: Linguistic",
    ],
    keywords="powerpoint translation llm ppt pptx multimodal",
)

