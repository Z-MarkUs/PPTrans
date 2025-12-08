#!/usr/bin/env python3
"""Simple test script to test PPT translation."""
import os
import sys
from pathlib import Path
from ppt_translator.cli import run_cli


def find_ppt_files(directory: Path = None) -> list[Path]:
    """Find all .ppt and .pptx files in the given directory."""
    if directory is None:
        directory = Path.cwd()
    
    ppt_files = []
    for ext in ['.ppt', '.pptx']:
        ppt_files.extend(directory.glob(f'*{ext}'))
    
    return sorted(ppt_files)


def main():
    """Run translation test on found PPT files."""
    # Check for OpenAI API key
    api_key = os.getenv('OPENAI_API_KEY')
    if not api_key:
        print("❌ Error: OPENAI_API_KEY environment variable not set")
        print("   Please set it with: export OPENAI_API_KEY='your-key-here'")
        sys.exit(1)
    
    # Find PPT files
    current_dir = Path.cwd()
    ppt_files = find_ppt_files(current_dir)
    
    if not ppt_files:
        print(f"❌ No PPT/PPTX files found in {current_dir}")
        sys.exit(1)
    
    print(f"✅ Found {len(ppt_files)} PPT file(s):")
    for ppt_file in ppt_files:
        print(f"   - {ppt_file.name}")
    print()
    
    # Run translation on each file
    for ppt_file in ppt_files:
        print(f"🔄 Processing: {ppt_file.name}")
        print("-" * 60)
        
        # Run CLI with OpenAI provider and vision review using GPT-5.1
        exit_code = run_cli([
            str(ppt_file),
            '--provider', 'openai',
            '--source-lang', 'zh',
            '--target-lang', 'en',
            '--vision-review',  # Enable vision review
            '--vision-model', 'gpt-5.1',  # Use GPT-5.1 for testing
            '--keep-intermediate',  # Keep XML files for inspection
        ])
        
        if exit_code == 0:
            # Check for output files
            base_name = ppt_file.stem
            output_pptx = current_dir / f"{base_name}_translated.pptx"
            temp_dir = current_dir / f"{base_name}_temp"
            output_xml = temp_dir / f"{base_name}_translated.xml"
            
            print()
            if output_pptx.exists():
                print(f"✅ Translated PPT created: {output_pptx.name}")
            if output_xml.exists():
                print(f"✅ Translated XML created: {output_xml.name}")
            if temp_dir.exists():
                print(f"📁 Temp directory: {temp_dir.name}/ (contains intermediate files)")
        else:
            print(f"❌ Translation failed for {ppt_file.name}")
        
        print()
    
    print("✨ Test complete!")


if __name__ == '__main__':
    main()

