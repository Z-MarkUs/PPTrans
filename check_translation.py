#!/usr/bin/env python3
"""Quick test to verify translation is working end-to-end."""

import json
from pathlib import Path
import xml.etree.ElementTree as ET

# Find a translated XML file in the temp directory
temp_files = list(Path("/Users/tianboxiong/Downloads/toy_project/PPTrans").glob("*_temp/"))
if temp_files:
    temp_dir = temp_files[0]
    translated_xml = temp_dir / f"{temp_dir.name[:-5]}_translated.xml"
    
    if translated_xml.exists():
        print(f"Found translated XML: {translated_xml}")
        tree = ET.parse(translated_xml)
        root = tree.getroot()
        
        # Check first few text elements
        for i, text_elem in enumerate(root.findall(".//text_element")[:3]):
            props = text_elem.find("properties")
            if props is not None and props.text:
                try:
                    data = json.loads(props.text)
                    print(f"\nText Element {i}:")
                    print(f"  Original text: {data.get('text', 'N/A')}")
                    if data.get('paragraphs'):
                        print(f"  Has {len(data['paragraphs'])} paragraphs")
                        for j, para in enumerate(data['paragraphs'][:2]):
                            print(f"    Para {j}: {para.get('text', 'N/A')}")
                except Exception as e:
                    print(f"  Error parsing: {e}")
    else:
        print(f"No translated XML found. Checked: {translated_xml}")
else:
    print("No temp directories found")
