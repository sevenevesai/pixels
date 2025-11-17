#!/usr/bin/env python3
from pixel_downscaler import *
from PIL import Image

im = Image.open('greenhouse-original.png').convert('RGBA')

print("=== Step 1: Detect Grid ===")
grid_size = detect_grid_size(im)
print(f"FFT detected grid: {grid_size}")

print("\n=== Step 2: Remove Background ===")
settings = {
    'bg_tolerance': 15,
    'bg_edge_tolerance': 30,
    'preserve_dark_lines': False,
    'dark_line_threshold': 100,
}
im_clean = remove_background_improved(im, settings)
print(f"After cleanup: {im_clean.size}")

print("\n=== Step 3: Find Optimal Scale ===")
result_img, factor, grid = find_optimal_scale(im_clean, min_factor=6, max_factor=20)
print(f"Best integer scale: {factor}")
print(f"Output size before fine-tune: {result_img.size}")

print("\n=== Step 4: Fine-tune ===")
result_img_fine, factor_fine = fine_tune_scale(im_clean, factor, grid_size)
print(f"After fine-tune: scale={factor_fine}, size={result_img_fine.size}")

print("\n=== Step 5: Auto-trim ===")
result_trimmed = auto_trim(result_img_fine)
print(f"After trim: {result_trimmed.size}")

print(f"\n=== Final Result ===")
print(f"Expected: 112x128")
print(f"Got: {result_trimmed.size}")
print(f"Match: {result_trimmed.size == (112, 128)}")
