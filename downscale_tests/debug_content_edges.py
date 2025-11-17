#!/usr/bin/env python3
from pixel_downscaler import is_content_edge
from PIL import Image
import numpy as np

# Test greenhouse
im = Image.open('greenhouse-original.png').convert('RGBA')
arr = np.array(im)
h, w = arr.shape[:2]

# Check content edges in 10-pixel edge zone
edge_width = 10
content_edge_count = 0

for y in range(h):
    for x in range(w):
        if x < edge_width or x >= w - edge_width or y < edge_width or y >= h - edge_width:
            if is_content_edge(arr, x, y):
                content_edge_count += 1

print(f"Python detected {content_edge_count} content edge pixels in 10-pixel zone")

# Sample a few edge pixels to see their variance/color_range
print("\nChecking a few pixels manually:")
test_pixels = [(5, 5), (100, 5), (500, 5), (120, 32)]  # last one is near content start

for x, y in test_pixels:
    is_content = is_content_edge(arr, x, y)
    window_size = 3
    y_start = max(0, y - window_size)
    y_end = min(h, y + window_size + 1)
    x_start = max(0, x - window_size)
    x_end = min(w, x + window_size + 1)

    neighborhood = arr[y_start:y_end, x_start:x_end, :3]
    variance = np.var(neighborhood)
    color_range = np.ptp(neighborhood, axis=(0, 1)).sum()

    print(f"  ({x}, {y}): is_content={is_content}, variance={variance:.2f}, color_range={color_range}")
