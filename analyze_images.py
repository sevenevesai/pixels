#!/usr/bin/env python3
from PIL import Image
import numpy as np

# Load images
input_img = Image.open('chair-1.png')
output_img = Image.open('downscaled-chair-1.png')

print("=== Image Analysis ===")
print(f"Input size: {input_img.size}")
print(f"Output size: {output_img.size}")

scale_x = input_img.size[0] / output_img.size[0]
scale_y = input_img.size[1] / output_img.size[1]

print(f"\nScale factors:")
print(f"  X: {scale_x:.4f}")
print(f"  Y: {scale_y:.4f}")
print(f"  Average: {(scale_x + scale_y) / 2:.4f}")
print(f"  Rounded: {round((scale_x + scale_y) / 2)}")

# Analyze grid pattern in input
print("\n=== Grid Pattern Analysis ===")
arr = np.array(input_img)
print(f"Input shape: {arr.shape}")

# Try to detect grid by looking at edge profiles
if len(arr.shape) >= 3:
    # Convert to grayscale for analysis
    if arr.shape[2] == 4:  # RGBA
        gray = (arr[:,:,0] * 0.299 + arr[:,:,1] * 0.587 + arr[:,:,2] * 0.114).astype(np.uint8)
    else:  # RGB
        gray = (arr[:,:,0] * 0.299 + arr[:,:,1] * 0.587 + arr[:,:,2] * 0.114).astype(np.uint8)

    # Compute horizontal differences to find edges
    h_diff = np.abs(np.diff(gray, axis=1))
    h_profile = np.sum(h_diff, axis=0)

    # Find peaks in horizontal profile
    print(f"Horizontal profile length: {len(h_profile)}")

    # Simple peak detection - find strong edges
    threshold = np.percentile(h_profile, 75)
    peaks = np.where(h_profile > threshold)[0]

    if len(peaks) > 1:
        # Calculate distances between peaks
        distances = np.diff(peaks)
        common_distances = []
        for d in range(5, 25):  # Check for common distances
            count = np.sum((distances >= d-0.5) & (distances <= d+0.5))
            if count > 0:
                common_distances.append((d, count))

        print("\nMost common edge distances (potential grid sizes):")
        common_distances.sort(key=lambda x: x[1], reverse=True)
        for dist, count in common_distances[:5]:
            print(f"  {dist} pixels: {count} occurrences")

print("\n=== Recommendation ===")
expected_scale = round((scale_x + scale_y) / 2)
print(f"Target scale factor: {expected_scale}x")
print(f"FFT should detect period around: {expected_scale} pixels")
