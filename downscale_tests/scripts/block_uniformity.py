"""
Pixel Art Downscaler v4 - Largest Valid Scale

Key insight: Multiple scales can produce "valid" pixel art, but we want
the LARGEST scale that still shows uniform blocks. Smaller scales always
work but aren't the "true" pixel size.

Approach:
1. FFT grid detection for initial hint
2. For each scale, find best phase via block variance
3. Select largest scale where variance is below threshold
4. If no clear winner, fall back to FFT hint
"""
import numpy as np
from PIL import Image
from pathlib import Path
import time


def detect_grid_size_fft(arr: np.ndarray, min_grid: int = 6, max_grid: int = 20) -> float | None:
    """Detect grid size using FFT on edge profiles."""
    if arr.shape[2] == 4:
        alpha = arr[:, :, 3].astype(np.float32) / 255.0
        gray = (arr[:, :, 0] * 0.299 + arr[:, :, 1] * 0.587 + arr[:, :, 2] * 0.114).astype(np.float32)
        gray = gray * alpha
    else:
        gray = (arr[:, :, 0] * 0.299 + arr[:, :, 1] * 0.587 + arr[:, :, 2] * 0.114).astype(np.float32)

    h, w = gray.shape
    edges_x = np.abs(np.diff(gray, axis=1))
    edges_y = np.abs(np.diff(gray, axis=0))
    horiz_profile = np.sum(edges_x, axis=0)
    vert_profile = np.sum(edges_y, axis=1)

    def find_period(profile, min_p, max_p):
        profile = profile - np.mean(profile)
        if len(profile) < 20:
            return None
        fft = np.fft.rfft(profile)
        power = np.abs(fft) ** 2
        freqs = np.fft.rfftfreq(len(profile))
        power[0] = 0
        valid_mask = (freqs >= 1/max_p) & (freqs <= 1/min_p)
        if not valid_mask.any():
            return None
        valid_power = power.copy()
        valid_power[~valid_mask] = 0
        peak_idx = np.argmax(valid_power)
        if power[peak_idx] < 0.1 * power.max():
            return None
        peak_freq = freqs[peak_idx]
        return 1.0 / peak_freq if peak_freq > 0 else None

    period_x = find_period(horiz_profile, min_grid, max_grid)
    period_y = find_period(vert_profile, min_grid, max_grid)

    if period_x and period_y:
        return (period_x + period_y) / 2
    return period_x or period_y


def calculate_block_variance_fast(arr: np.ndarray, scale: int, phase_x: int, phase_y: int) -> float:
    """Calculate average within-block variance at given scale and phase."""
    h, w = arr.shape[:2]

    # Use center region to avoid edge artifacts
    margin_y = h // 6
    margin_x = w // 6
    region = arr[margin_y:h-margin_y, margin_x:w-margin_x]
    rh, rw = region.shape[:2]

    # Adjust phase
    adj_py = phase_y % scale
    adj_px = phase_x % scale

    n_blocks_y = (rh - adj_py) // scale
    n_blocks_x = (rw - adj_px) // scale

    if n_blocks_y < 2 or n_blocks_x < 2:
        return float('inf')

    end_y = adj_py + n_blocks_y * scale
    end_x = adj_px + n_blocks_x * scale

    rgb = region[adj_py:end_y, adj_px:end_x, :3].astype(np.float32)

    # Reshape to blocks
    blocks = rgb.reshape(n_blocks_y, scale, n_blocks_x, scale, 3)
    blocks = blocks.transpose(0, 2, 1, 3, 4).reshape(-1, scale * scale, 3)

    # Calculate variance per block
    block_means = blocks.mean(axis=1, keepdims=True)
    variances = np.mean((blocks - block_means) ** 2, axis=(1, 2))

    return float(np.mean(variances))


def find_best_phase_for_scale(arr: np.ndarray, scale: int) -> tuple[int, int, float]:
    """Find the phase offset that minimizes block variance for this scale."""
    best_var = float('inf')
    best_px, best_py = 0, 0

    # Coarse search
    step = max(1, scale // 3)
    for py in range(0, scale, step):
        for px in range(0, scale, step):
            var = calculate_block_variance_fast(arr, scale, px, py)
            if var < best_var:
                best_var = var
                best_px, best_py = px, py

    # Fine search around best
    if step > 1:
        for py in range(max(0, best_py - step), min(scale, best_py + step + 1)):
            for px in range(max(0, best_px - step), min(scale, best_px + step + 1)):
                var = calculate_block_variance_fast(arr, scale, px, py)
                if var < best_var:
                    best_var = var
                    best_px, best_py = px, py

    return best_px, best_py, best_var


def find_optimal_scale(arr: np.ndarray, min_scale: int = 6, max_scale: int = 20,
                        grid_hint: float | None = None) -> tuple[int, int, int, float, list]:
    """
    Find optimal scale by looking for largest scale with low variance.
    """
    all_results = []

    # Test all scales
    for scale in range(min_scale, max_scale + 1):
        px, py, var = find_best_phase_for_scale(arr, scale)
        all_results.append({
            'scale': scale,
            'phase_x': px,
            'phase_y': py,
            'variance': var
        })

    # Sort by variance to find threshold
    sorted_by_var = sorted(all_results, key=lambda x: x['variance'])

    # The minimum variance is our baseline - good scales should be within 2x of this
    min_var = sorted_by_var[0]['variance']
    threshold = min_var * 2.0  # Allow 2x tolerance

    # Find all "valid" scales (variance below threshold)
    valid_scales = [r for r in all_results if r['variance'] <= threshold]

    if not valid_scales:
        # Fallback to minimum variance
        best = sorted_by_var[0]
    else:
        # If we have FFT hint, prefer scale closest to it among valid scales
        if grid_hint:
            best = min(valid_scales, key=lambda x: abs(x['scale'] - grid_hint))
        else:
            # Otherwise take largest valid scale
            best = max(valid_scales, key=lambda x: x['scale'])

    return best['scale'], best['phase_x'], best['phase_y'], best['variance'], all_results


def downsample_with_phase(arr: np.ndarray, scale: int, phase_x: int, phase_y: int) -> np.ndarray:
    """Downsample by taking center pixel of each block."""
    h, w = arr.shape[:2]
    out_h = (h - phase_y) // scale
    out_w = (w - phase_x) // scale

    if out_h < 1 or out_w < 1:
        return arr

    center = scale // 2
    result = np.zeros((out_h, out_w, 4), dtype=np.uint8)

    for oy in range(out_h):
        for ox in range(out_w):
            sy = phase_y + oy * scale + center
            sx = phase_x + ox * scale + center
            if sy < h and sx < w:
                result[oy, ox] = arr[sy, sx]

    return result


def remove_background_simple(arr: np.ndarray, tolerance: int = 20) -> np.ndarray:
    """Simple background removal via flood fill from edges."""
    from scipy import ndimage

    h, w = arr.shape[:2]
    result = arr.copy()

    # Sample edge colors
    edge_pixels = []
    for y in range(min(5, h)):
        for x in range(w):
            edge_pixels.append(arr[y, x, :3])
    for y in range(max(0, h-5), h):
        for x in range(w):
            edge_pixels.append(arr[y, x, :3])
    for y in range(h):
        for x in range(min(5, w)):
            edge_pixels.append(arr[y, x, :3])
        for x in range(max(0, w-5), w):
            edge_pixels.append(arr[y, x, :3])

    edge_pixels = np.array(edge_pixels)
    rounded = (edge_pixels // 16) * 16
    unique, counts = np.unique(rounded, axis=0, return_counts=True)
    bg_color = unique[np.argmax(counts)]

    diff = np.abs(arr[:, :, :3].astype(np.int16) - bg_color.astype(np.int16)).sum(axis=2)
    bg_mask = diff <= tolerance

    edge_seed = np.zeros((h, w), dtype=bool)
    edge_seed[0, :] = bg_mask[0, :]
    edge_seed[-1, :] = bg_mask[-1, :]
    edge_seed[:, 0] = bg_mask[:, 0]
    edge_seed[:, -1] = bg_mask[:, -1]

    struct = ndimage.generate_binary_structure(2, 1)
    bg_mask_dilated = ndimage.binary_dilation(bg_mask, structure=struct, iterations=1)

    flooded = edge_seed.copy()
    for _ in range(max(h, w)):
        new_flooded = ndimage.binary_dilation(flooded, structure=struct) & bg_mask_dilated
        if np.array_equal(new_flooded, flooded):
            break
        flooded = new_flooded

    result[flooded, 3] = 0
    return result


def trim_transparency(arr: np.ndarray) -> np.ndarray:
    """Crop to non-transparent content."""
    alpha = arr[:, :, 3]
    rows = np.any(alpha > 0, axis=1)
    cols = np.any(alpha > 0, axis=0)

    if not rows.any() or not cols.any():
        return arr

    y_min, y_max = np.where(rows)[0][[0, -1]]
    x_min, x_max = np.where(cols)[0][[0, -1]]

    return arr[y_min:y_max+1, x_min:x_max+1]


def process_image(input_path: Path, output_path: Path, verbose: bool = True) -> dict:
    """Full pipeline: bg removal -> trim -> detect scale -> downsample."""
    img = Image.open(input_path).convert('RGBA')
    arr = np.array(img)
    original_size = arr.shape[:2]

    if verbose:
        print(f"Loaded {input_path.name}: {arr.shape[1]}x{arr.shape[0]}")

    # Background removal
    t0 = time.time()
    arr = remove_background_simple(arr, tolerance=25)
    if verbose:
        print(f"  Background removal: {time.time()-t0:.2f}s")

    # Trim
    arr = trim_transparency(arr)
    trimmed_size = arr.shape[:2]
    if verbose:
        print(f"  After trim: {arr.shape[1]}x{arr.shape[0]}")

    # FFT hint
    t0 = time.time()
    grid_hint = detect_grid_size_fft(arr)
    if verbose:
        print(f"  FFT grid: {grid_hint:.2f}" if grid_hint else "  FFT grid: None")

    # Find optimal scale
    t0 = time.time()
    best_scale, best_px, best_py, best_var, all_results = find_optimal_scale(arr, grid_hint=grid_hint)
    if verbose:
        print(f"  Scale detection: {time.time()-t0:.2f}s")
        print(f"  Best: scale={best_scale}, phase=({best_px},{best_py}), var={best_var:.1f}")

        # Show variance for each scale
        print("  All scales (variance):")
        for r in all_results:
            marker = " <--" if r['scale'] == best_scale else ""
            print(f"    {r['scale']:2d}: var={r['variance']:7.1f}{marker}")

    # Downsample
    result = downsample_with_phase(arr, best_scale, best_px, best_py)

    # Save
    output_path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(result, 'RGBA').save(output_path)

    final_size = result.shape[:2]
    if verbose:
        print(f"  Output: {result.shape[1]}x{result.shape[0]}")

    return {
        'input': input_path.name,
        'original_size': (original_size[1], original_size[0]),
        'trimmed_size': (trimmed_size[1], trimmed_size[0]),
        'final_size': (final_size[1], final_size[0]),
        'scale': best_scale,
        'phase': (best_px, best_py),
        'variance': best_var,
        'grid_hint': grid_hint,
        'all_results': all_results
    }


if __name__ == '__main__':
    import sys

    script_dir = Path(__file__).parent.parent
    input_dir = script_dir / 'input'
    output_dir = script_dir / 'output'

    if len(sys.argv) > 1:
        input_path = Path(sys.argv[1])
        output_path = output_dir / f"{input_path.stem}-block-uniformity.png"
        process_image(input_path, output_path)
    else:
        print("=" * 60)
        print("Pixel Art Downscaler v4 - Largest Valid Scale")
        print("=" * 60)

        for input_path in sorted(input_dir.glob('*.png')):
            print()
            output_path = output_dir / f"{input_path.stem}-block-uniformity.png"
            process_image(input_path, output_path)

        print()
        print("=" * 60)
        print("Done!")
