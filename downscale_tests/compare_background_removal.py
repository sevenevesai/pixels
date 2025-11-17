#!/usr/bin/env python3
from pixel_downscaler import remove_background_improved
from PIL import Image
import numpy as np

# Test greenhouse
im = Image.open('greenhouse-original.png').convert('RGBA')

settings = {
    'bg_tolerance': 15,
    'bg_edge_tolerance': 30,
    'preserve_dark_lines': False,
    'dark_line_threshold': 100,
}

im_clean = remove_background_improved(im, settings)
im_clean.save('greenhouse-python-bg-removed.png')

# Analyze what was removed
orig_arr = np.array(Image.open('greenhouse-original.png').convert('RGBA'))
clean_arr = np.array(im_clean)

orig_opaque = (orig_arr[:, :, 3] > 0).sum()
clean_opaque = (clean_arr[:, :, 3] > 0).sum()

print(f"Original opaque pixels: {orig_opaque}")
print(f"After removal opaque pixels: {clean_opaque}")
print(f"Removed: {orig_opaque - clean_opaque} pixels")
print(f"Saved to: greenhouse-python-bg-removed.png")
