#!/usr/bin/env python3
"""
Test the current Rust downscaler and compare with expected output
"""
from PIL import Image
import subprocess
import os

# Paths
INPUT = 'chair-1.png'
EXPECTED = 'downscaled-chair-1.png'
RUST_OUTPUT = 'rust-output.png'

# Run Rust downscaler
print("Running Rust downscaler...")
result = subprocess.run([
    'src-tauri/target/release/pixels-toolkit.exe',  # Or whatever the binary name is
    'downscale',
    '--input', INPUT,
    '--output', RUST_OUTPUT
], capture_output=True, text=True)

print(result.stdout)
if result.stderr:
    print("STDERR:", result.stderr)

# Compare outputs if rust output exists
if os.path.exists(RUST_OUTPUT):
    rust_img = Image.open(RUST_OUTPUT)
    expected_img = Image.open(EXPECTED)

    print("\n=== Comparison ===")
    print(f"Rust output canvas: {rust_img.size}")
    print(f"Expected canvas: {expected_img.size}")

    # Get content bounds
    def get_bounds(img):
        pixels = img.load()
        width, height = img.size

        min_x, min_y = width, height
        max_x, max_y = 0, 0

        for y in range(height):
            for x in range(width):
                if pixels[x, y][3] > 0:  # Has alpha
                    min_x = min(min_x, x)
                    max_x = max(max_x, x)
                    min_y = min(min_y, y)
                    max_y = max(max_y, y)

        return (min_x, min_y, max_x + 1, max_y + 1)

    rust_bounds = get_bounds(rust_img)
    expected_bounds = get_bounds(expected_img)

    rust_size = (rust_bounds[2] - rust_bounds[0], rust_bounds[3] - rust_bounds[1])
    expected_size = (expected_bounds[2] - expected_bounds[0], expected_bounds[3] - expected_bounds[1])

    print(f"\nRust content size: {rust_size}")
    print(f"Expected content size: {expected_size}")

    if rust_size == expected_size:
        print("✓ Content sizes match!")
    else:
        diff_x = rust_size[0] - expected_size[0]
        diff_y = rust_size[1] - expected_size[1]
        print(f"✗ Content size difference: ({diff_x}, {diff_y})")
else:
    print("Rust output not created - running via Tauri command instead")
