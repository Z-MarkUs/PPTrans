#!/usr/bin/env python3
"""Test script to verify translation is working properly."""

import sys
from pathlib import Path

# Add the PPTrans directory to the Python path
pptrans_dir = Path("/Users/tianboxiong/Downloads/toy_project/PPTrans")
sys.path.insert(0, str(pptrans_dir))

from ppt_translator.pipeline import extract_text_from_slide, ppt_to_xml
from pptx import Presentation

# Create a minimal mock translator for testing
class MockTranslator:
    def translate(self, text, source_lang, target_lang):
        if not text or not text.strip():
            return text
        # Simple test: just add a prefix to show it was translated
        return f"[TRANSLATED] {text}"
    
    def cache_size(self):
        return 0

# Test with the first PPT file we find
ppt_files = list(pptrans_dir.glob("*.pptx"))
if not ppt_files:
    print("No .pptx files found in the PPTrans directory")
    sys.exit(1)

test_ppt = ppt_files[0]
print(f"Testing with: {test_ppt.name}")

# Generate XML with mock translation
translator = MockTranslator()
xml_result = ppt_to_xml(
    str(test_ppt),
    translator=translator,
    source_lang="en",
    target_lang="es",
    max_workers=1
)

if xml_result:
    print("\n✅ XML generation successful!")
    # Print first 1000 chars to verify translation happened
    print("\nFirst 1000 characters of translated XML:")
    print(xml_result[:1000])
    
    # Check if translation marker is in the XML
    if "[TRANSLATED]" in xml_result:
        print("\n✅ Translation marker found - translation is working!")
    else:
        print("\n❌ Translation marker NOT found - translation may not be working")
else:
    print("❌ XML generation failed")
