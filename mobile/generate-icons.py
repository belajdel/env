#!/usr/bin/env python3
"""
Generate PWA icons from SVG
Run with: python3 generate-icons.py
Requires: pip install cairosvg pillow
"""

import os
import sys
from pathlib import Path

# Try to import required libraries
try:
    import cairosvg
    from PIL import Image
    import io
except ImportError:
    print("Installing required packages...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "cairosvg", "pillow"])
    import cairosvg
    from PIL import Image
    import io

SVG_PATH = Path(__file__).parent / "icon.svg"
OUTPUT_DIR = Path(__file__).parent

SIZES = [72, 96, 128, 144, 152, 192, 384, 512]

def generate_icons():
    if not SVG_PATH.exists():
        print(f"SVG not found: {SVG_PATH}")
        return
    
    print(f"Generating icons from {SVG_PATH}")
    
    for size in SIZES:
        output_path = OUTPUT_DIR / f"icon-{size}.png"
        
        # Convert SVG to PNG
        png_data = cairosvg.svg2png(
            url=str(SVG_PATH),
            output_width=size,
            output_height=size,
        )
        
        # Save
        img = Image.open(io.BytesIO(png_data))
        img.save(output_path, "PNG", optimize=True)
        print(f"  Created {output_path.name} ({size}x{size})")
    
    # Also create a generic icon.png (192x192)
    png_data = cairosvg.svg2png(url=str(SVG_PATH), output_width=192, output_height=192)
    img = Image.open(io.BytesIO(png_data))
    img.save(OUTPUT_DIR / "icon.png", "PNG", optimize=True)
    print(f"  Created icon.png (192x192)")
    
    print("\nAll icons generated successfully!")

if __name__ == "__main__":
    generate_icons()