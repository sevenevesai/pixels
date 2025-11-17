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

print("Testing scales with combined scoring:")
for scale in range(6, 12):
    align_score, down = grid_alignment_score(im_clean, float(scale))
    info = information_content(down)
    combined = align_score - info / 1000
    print(f"  Scale {scale}x: align={align_score:.2f}, info={info:.0f}, combined={combined:.2f}")
