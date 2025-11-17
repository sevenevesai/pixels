#!/usr/bin/env python3
from pixel_downscaler import sample_edge_colors, find_background_colors
from PIL import Image
import numpy as np

# Test greenhouse
im = Image.open('greenhouse-original.png').convert('RGBA')
arr = np.array(im)
h, w = arr.shape[:2]

# Sample and detect
edge_colors = sample_edge_colors(arr, sample_width=5)
bg_colors = find_background_colors(edge_colors, max_colors=3)
print(f"Background colors: {bg_colors}")

# Create mask like Python does (lines 182-193)
tolerance = 15
edge_tolerance = 30

mask = np.zeros((h, w), dtype=bool)

edge_mask = np.zeros((h, w), dtype=bool)
edge_mask[0:10, :] = True
edge_mask[-10:, :] = True
edge_mask[:, 0:10] = True
edge_mask[:, -10:] = True

for bg_color in bg_colors:
    diff = np.abs(arr[:, :, :3].astype(np.int16) - bg_color).sum(axis=2)
    color_mask = np.where(edge_mask, diff <= edge_tolerance, diff <= tolerance)
    mask |= color_mask

print(f"Mask contains {mask.sum()} pixels (out of {h*w} total)")
print(f"Mask percentage: {mask.sum() / (h*w) * 100:.2f}%")

# Check edge seed
edge_seed = np.zeros((h, w), dtype=bool)
edge_seed[0, :] = mask[0, :]
edge_seed[-1, :] = mask[-1, :]
edge_seed[:, 0] = mask[:, 0]
edge_seed[:, -1] = mask[:, -1]

print(f"Edge seed contains {edge_seed.sum()} pixels")
