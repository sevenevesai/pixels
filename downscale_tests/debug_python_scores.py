#!/usr/bin/env python3
import sys
sys.path.insert(0, '.')

from pixel_downscaler import *
from PIL import Image

# Load and process greenhouse
im = Image.open('greenhouse-original.png').convert('RGBA')

# Remove background
settings = {
    'bg_tolerance': 15,
    'bg_edge_tolerance': 30,
    'preserve_dark_lines': False,
    'dark_line_threshold': 100,
}

from pixel_downscaler import remove_background_improved
im_clean = remove_background_improved(im, settings)

print("=== Python Scores for Greenhouse ===")
print(f"After cleanup: {im_clean.size}")

# Test scales 6-14
for factor in range(6, 15):
    alignment_score, down = grid_alignment_score(im_clean, factor)
    if down:
        info = information_content(down)
        combined = alignment_score - info / 1000
        print(f"Scale {factor:2}x: align={alignment_score:7.2f}, info={info:8.1f}, combined={combined:8.2f}, output={down.size}")
