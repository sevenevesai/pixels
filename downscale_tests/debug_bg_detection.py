#!/usr/bin/env python3
from pixel_downscaler import sample_edge_colors, find_background_colors
from PIL import Image
import numpy as np

# Test greenhouse
im = Image.open('greenhouse-original.png').convert('RGBA')
arr = np.array(im)

# Sample edge colors
edge_colors = sample_edge_colors(arr, sample_width=5)
print(f"Sampled {len(edge_colors)} edge colors")

# Find background colors
bg_colors = find_background_colors(edge_colors, max_colors=3)
print(f"Detected {len(bg_colors)} background colors:")
for i, color in enumerate(bg_colors):
    print(f"  {i+1}. {color}")

# Show some sample edge colors
print(f"\nFirst 10 edge colors:")
for i in range(min(10, len(edge_colors))):
    print(f"  {edge_colors[i]}")
