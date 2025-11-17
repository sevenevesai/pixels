#!/usr/bin/env python3
from pixel_downscaler import *
from PIL import Image

im = Image.open('greenhouse-original.png').convert('RGBA')
print(f"Original: {im.size}")

# Step 1: Remove background
settings = {
    'bg_tolerance': 15,
    'bg_edge_tolerance': 30,
    'preserve_dark_lines': False,
    'dark_line_threshold': 100,
}
im_clean = remove_background_improved(im, settings)
print(f"After BG removal: {im_clean.size}")

# Step 2: Find optimal scale (WITHOUT fine-tuning)
result_img, factor, grid = find_optimal_scale(im_clean, min_factor=6, max_factor=20)
print(f"After downscale at {factor}x: {result_img.size}")

# Step 3: Auto-trim
result_trimmed = trim_transparency(result_img)
print(f"After trim: {result_trimmed.size}")

print(f"\nExpected: 112x128")
print(f"Match: {result_trimmed.size == (112, 128)}")

result_trimmed.save('greenhouse-python-full-pipeline.png')
