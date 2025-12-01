#!/usr/bin/env python3
from pixel_downscaler import *
from PIL import Image

im = Image.open('grindstone-original.png').convert('RGBA')

settings = {
    'bg_tolerance': 15,
    'bg_edge_tolerance': 30,
    'preserve_dark_lines': False,
    'dark_line_threshold': 100,
}

im_clean = remove_background_improved(im, settings)

print("Testing scales 6 to 20:")
for scale in range(6, 21):
    score, _ = grid_alignment_score(im_clean, float(scale))
    print(f"  Scale {scale}x: score = {score:.2f}")
