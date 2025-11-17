#!/usr/bin/env python3
from pixel_downscaler import *
from PIL import Image

im = Image.open('greenhouse-original.png').convert('RGBA')

# Full pipeline WITH fine-tuning
settings = {
    'bg_tolerance': 15,
    'bg_edge_tolerance': 30,
    'preserve_dark_lines': False,
    'dark_line_threshold': 100,
}
im_clean = remove_background_improved(im, settings)

# Find optimal scale
result_img, factor, grid = find_optimal_scale(im_clean, min_factor=6, max_factor=20)
print(f"Coarse scale: {factor}x, size: {result_img.size}")

# Fine-tune
result_fine, factor_fine = fine_tune_scale(im_clean, factor, grid)
print(f"Fine-tuned scale: {factor_fine:.2f}x, size: {result_fine.size}")

# Trim
result_trimmed = trim_transparency(result_fine)
print(f"After trim: {result_trimmed.size}")

print(f"\nExpected: 112x128")
print(f"Match: {result_trimmed.size == (112, 128)}")
