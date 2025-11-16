"""
Enhanced pixel art downscaler with improved background removal.
Detects true pixel resolution from AI-upscaled images.
SCALING LOGIC PRESERVED FROM ORIGINAL SCRIPT.
"""
import math
import numpy as np
from pathlib import Path
from PIL import Image
from scipy import ndimage
from collections import Counter


# ============================================================================
# IMPROVED BACKGROUND REMOVAL
# ============================================================================

def is_content_edge(arr, x, y, window_size=3):
    """
    Determine if a pixel at edge is likely content vs background.
    Looks for color variance and detail in neighborhood.
    """
    h, w = arr.shape[:2]
    
    y_start = max(0, y - window_size)
    y_end = min(h, y + window_size + 1)
    x_start = max(0, x - window_size)
    x_end = min(w, x + window_size + 1)
    
    neighborhood = arr[y_start:y_end, x_start:x_end, :3]
    
    variance = np.var(neighborhood)
    color_range = np.ptp(neighborhood, axis=(0, 1)).sum()
    
    return variance > 100 or color_range > 50


def detect_dark_lines(arr, threshold=50):
    """Detect dark lines that might be outlines."""
    rgb_sum = arr[:, :, :3].sum(axis=2)
    is_dark = rgb_sum < threshold
    has_alpha = arr[:, :, 3] > 10
    
    dark_with_alpha = is_dark & has_alpha
    
    from scipy.ndimage import binary_dilation, binary_erosion
    struct = np.array([[0, 1, 0], [1, 1, 1], [0, 1, 0]], dtype=bool)
    
    cleaned = binary_erosion(dark_with_alpha, structure=struct)
    cleaned = binary_dilation(cleaned, structure=struct)
    
    return cleaned


def sample_edge_colors(arr, sample_width=5):
    """Sample colors from all edges."""
    h, w = arr.shape[:2]
    colors = []
    
    colors.extend(arr[0:sample_width, :, :3].reshape(-1, 3))
    colors.extend(arr[-sample_width:, :, :3].reshape(-1, 3))
    colors.extend(arr[:, 0:sample_width, :3].reshape(-1, 3))
    colors.extend(arr[:, -sample_width:, :3].reshape(-1, 3))
    
    return np.array(colors, dtype=np.int16)


def find_background_colors(edge_colors, max_colors=3):
    """Cluster edge colors to find background colors."""
    rounded = np.round(edge_colors / 16) * 16
    color_tuples = [tuple(c) for c in rounded]
    color_counts = Counter(color_tuples)
    
    top_colors = [np.array(color, dtype=np.int16) 
                  for color, count in color_counts.most_common(max_colors)]
    
    return top_colors


def detect_checkerboard_pattern(arr, sample_size=50):
    """Detect checkerboard pattern."""
    h, w = arr.shape[:2]
    corner = arr[0:min(sample_size, h), 0:min(sample_size, w), :3]
    unique_colors = np.unique(corner.reshape(-1, 3), axis=0)
    
    if len(unique_colors) == 2:
        color1, color2 = unique_colors
        
        alternating_count = 0
        total_samples = 0
        
        for i in range(0, min(20, corner.shape[0]), 2):
            for j in range(0, min(20, corner.shape[1]), 2):
                if i < corner.shape[0] and j < corner.shape[1]:
                    pixel = corner[i, j]
                    if np.array_equal(pixel, color1) or np.array_equal(pixel, color2):
                        alternating_count += 1
                    total_samples += 1
        
        if total_samples > 0 and alternating_count / total_samples > 0.9:
            return [color1.astype(np.int16), color2.astype(np.int16)]
    
    return None


def conservative_flood_fill(mask, edge_seed, content_barrier):
    """Flood fill that stops at content boundaries."""
    result = edge_seed.copy()
    structure = ndimage.generate_binary_structure(2, 1)
    
    for _ in range(500):
        dilated = ndimage.binary_dilation(result, structure=structure)
        new_result = dilated & mask & ~content_barrier
        
        if np.array_equal(new_result, result):
            break
        
        result = new_result
    
    return result


def binary_propagation(mask, seed):
    """Standard flood fill."""
    result = seed.copy()
    structure = ndimage.generate_binary_structure(2, 1)
    
    for _ in range(1000):
        dilated = ndimage.binary_dilation(result, structure=structure)
        new_result = dilated & mask
        
        if np.array_equal(new_result, result):
            break
        
        result = new_result
    
    return result


def remove_background_improved(im, settings):
    """Improved background removal with content preservation."""
    mode = settings.get('bg_removal_mode', 'conservative')
    
    if mode == 'none':
        return im
    
    im = im.convert("RGBA")
    arr = np.array(im)
    h, w = arr.shape[:2]
    
    tolerance = settings.get('bg_tolerance', 15)
    edge_tolerance = settings.get('bg_edge_tolerance', 25)
    preserve_dark_lines = settings.get('preserve_dark_lines', True)
    dark_threshold = settings.get('dark_line_threshold', 50)
    
    # Detect dark lines
    dark_line_mask = np.zeros((h, w), dtype=bool)
    if preserve_dark_lines:
        dark_line_mask = detect_dark_lines(arr, threshold=dark_threshold)
    
    # Detect content at edges
    content_edge_mask = np.zeros((h, w), dtype=bool)
    if mode == 'conservative':
        edge_width = 10
        for y in range(h):
            for x in range(w):
                if (x < edge_width or x >= w - edge_width or 
                    y < edge_width or y >= h - edge_width):
                    if is_content_edge(arr, x, y):
                        content_edge_mask[y, x] = True
    
    # Detect background colors
    checkerboard_colors = detect_checkerboard_pattern(arr)
    
    if checkerboard_colors:
        bg_colors = checkerboard_colors
    else:
        edge_colors = sample_edge_colors(arr, sample_width=5)
        bg_colors = find_background_colors(edge_colors, max_colors=3)
    
    # Create background mask
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
    
    # Protect content
    mask = mask & ~dark_line_mask
    
    if mode == 'conservative':
        mask = mask & ~content_edge_mask
    
    # Flood fill
    edge_seed = np.zeros((h, w), dtype=bool)
    edge_seed[0, :] = mask[0, :]
    edge_seed[-1, :] = mask[-1, :]
    edge_seed[:, 0] = mask[:, 0]
    edge_seed[:, -1] = mask[:, -1]
    
    from scipy.ndimage import binary_dilation
    mask_dilated = binary_dilation(mask, iterations=1 if mode == 'conservative' else 2)
    
    content_barrier = dark_line_mask | content_edge_mask
    
    if mode == 'conservative':
        flooded = conservative_flood_fill(mask_dilated, edge_seed, content_barrier)
    else:
        flooded = binary_propagation(mask_dilated, edge_seed)
    
    arr[..., 3] = np.where(flooded, 0, arr[..., 3])
    
    return Image.fromarray(arr, "RGBA")


def trim_transparency(im):
    """Crop image to non-transparent content."""
    arr = np.array(im)
    alpha = arr[:, :, 3]
    rows, cols = np.where(alpha > 0)
    
    if len(rows) == 0:
        return im
    
    return im.crop((cols.min(), rows.min(), cols.max() + 1, rows.max() + 1))


# ============================================================================
# ORIGINAL SCALING LOGIC (UNCHANGED FROM YOUR SCRIPT)
# ============================================================================

def detect_grid_size(im, min_grid=4, max_grid=30):
    """Detect fake pixel grid size using FFT - ORIGINAL LOGIC."""
    arr = np.array(im.convert("L"), dtype=np.float32)
    h, w = arr.shape
    
    edges_x = np.abs(np.diff(arr, axis=1))
    edges_y = np.abs(np.diff(arr, axis=0))
    
    horiz_profile = np.sum(edges_x, axis=0)
    vert_profile = np.sum(edges_y, axis=1)
    
    def find_grid_period(profile, min_p, max_p):
        """Find grid period using FFT."""
        profile = profile - np.mean(profile)
        
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
        period = 1.0 / peak_freq if peak_freq > 0 else None
        
        return period
    
    period_x = find_grid_period(horiz_profile, min_grid, max_grid)
    period_y = find_grid_period(vert_profile, min_grid, max_grid)
    
    if period_x and period_y:
        return (period_x + period_y) / 2
    return period_x or period_y


def grid_alignment_score(im, factor):
    """Measure grid alignment - ORIGINAL LOGIC."""
    new_w = int(round(im.width / factor))
    new_h = int(round(im.height / factor))
    
    if new_w < 8 or new_h < 8:
        return float('inf'), None
    
    down = im.resize((new_w, new_h), Image.Resampling.NEAREST)
    up = down.resize((im.width, im.height), Image.Resampling.NEAREST)
    
    orig_arr = np.array(im, dtype=np.float32)
    up_arr = np.array(up, dtype=np.float32)
    
    alpha_mask = orig_arr[:, :, 3] > 0
    if not alpha_mask.any():
        return float('inf'), None
    
    rgb_diff = np.abs(orig_arr[:, :, :3] - up_arr[:, :, :3])
    mae = np.mean(rgb_diff[alpha_mask])
    
    alpha_diff = np.abs(orig_arr[:, :, 3] - up_arr[:, :, 3])
    alpha_error = np.mean(alpha_diff[alpha_mask])
    
    down_arr = np.array(down)
    semi_pixels = ((down_arr[:, :, 3] > 0) & (down_arr[:, :, 3] < 255)).sum()
    semi_ratio = semi_pixels / (new_w * new_h)
    
    total_score = mae + alpha_error * 0.5 + semi_ratio * 100
    
    return total_score, down


def information_content(im):
    """Measure information content - ORIGINAL LOGIC."""
    arr = np.array(im)
    alpha = arr[:, :, 3]
    visible = alpha > 0
    
    if not visible.any():
        return 0
    
    rgb = arr[visible][:, :3]
    variance = np.var(rgb)
    
    gray = arr[:, :, :3].mean(axis=2)
    edges_x = np.abs(np.diff(gray, axis=1))
    edges_y = np.abs(np.diff(gray, axis=0))
    edge_count = (edges_x > 20).sum() + (edges_y > 20).sum()
    
    return variance + edge_count / 10


def find_optimal_scale(im, min_factor=6, max_factor=20):
    """Find optimal scale - ORIGINAL LOGIC."""
    grid_size = detect_grid_size(im)
    
    if grid_size and min_factor <= grid_size <= max_factor:
        search_min = max(min_factor, int(grid_size - 2))
        search_max = min(max_factor, int(grid_size + 2))
    else:
        search_min = min_factor
        search_max = max_factor
    
    results = []
    
    for factor in range(search_min, search_max + 1):
        alignment_score, down = grid_alignment_score(im, factor)
        
        if down is None:
            continue
        
        info = information_content(down)
        combined = alignment_score - info / 1000
        
        results.append({
            'factor': factor,
            'width': down.width,
            'height': down.height,
            'alignment': alignment_score,
            'info': info,
            'combined': combined,
            'image': down
        })
    
    if not results:
        return im, 1, grid_size
    
    best = min(results, key=lambda x: x['combined'])
    
    if grid_size and search_min != min_factor:
        closest = min(results, key=lambda x: abs(x['factor'] - grid_size))
        if closest['combined'] < best['combined'] * 1.2:
            best = closest
    
    return best['image'], best['factor'], grid_size


def fine_tune_scale(im, initial_factor, grid_size=None):
    """Fine-tune with fractional scales - ORIGINAL LOGIC."""
    if grid_size:
        center = grid_size
        search_width = 1.0
    else:
        center = initial_factor
        search_width = 1.0
    
    factors = np.arange(center - search_width, center + search_width + 0.01, 0.05)
    
    best_score = float('inf')
    best_result = None
    best_factor = initial_factor
    
    results_by_size = {}
    
    for f in factors:
        if f < 1:
            continue
        
        score, down = grid_alignment_score(im, f)
        
        if down is None:
            continue
        
        size_key = (down.width, down.height)
        
        if size_key not in results_by_size or score < results_by_size[size_key]['score']:
            results_by_size[size_key] = {
                'score': score,
                'factor': f,
                'image': down
            }
        
        if score < best_score:
            best_score = score
            best_result = down
            best_factor = f
    
    return best_result, best_factor


# ============================================================================
# CANVAS PADDING (NEW FEATURE)
# ============================================================================

def pad_to_multiple(im, multiple=16):
    """
    Pad image canvas to nearest multiple, centering the artwork.
    E.g., 68x78 with multiple=16 becomes 80x80 centered.
    """
    import math
    
    # Calculate target dimensions
    target_w = math.ceil(im.width / multiple) * multiple
    target_h = math.ceil(im.height / multiple) * multiple
    
    # If already at multiple, return as-is
    if target_w == im.width and target_h == im.height:
        return im
    
    # Create new transparent canvas
    new_im = Image.new('RGBA', (target_w, target_h), (0, 0, 0, 0))
    
    # Calculate paste position (center)
    paste_x = (target_w - im.width) // 2
    paste_y = (target_h - im.height) // 2
    
    # Paste original image centered
    new_im.paste(im, (paste_x, paste_y))
    
    return new_im


# ============================================================================
# MAIN PROCESSING PIPELINE
# ============================================================================

def downscale_image(input_path: Path, output_path: Path, settings: dict) -> dict:
    """Process a single AI-generated image to find true pixel resolution."""
    im = Image.open(input_path).convert("RGBA")
    original_size = (im.width, im.height)
    
    # Step 1: Background removal
    im = remove_background_improved(im, settings)
    
    # Step 2: Trim transparency
    if settings.get('auto_trim', True):
        im = trim_transparency(im)
    
    after_cleanup_size = (im.width, im.height)
    
    # Step 3: Find optimal scale (using original logic with fixed 6-20 range)
    result, factor, grid_size = find_optimal_scale(im, min_factor=6, max_factor=20)
    
    # Step 4: Fine-tune if enabled
    if settings.get('enable_fine_tune', True) and result.width >= 16 and result.height >= 16:
        result, factor = fine_tune_scale(im, factor, grid_size)
    
    # Step 5: Pad canvas to multiple if enabled
    if settings.get('pad_canvas', True):
        multiple = settings.get('canvas_multiple', 16)
        result = pad_to_multiple(result, multiple)
    
    # Save result
    output_path.parent.mkdir(parents=True, exist_ok=True)
    result.save(output_path)
    
    # Return info
    return {
        'filename': input_path.name,
        'original_size': original_size,
        'after_cleanup_size': after_cleanup_size,
        'final_size': (result.width, result.height),
        'scale_factor': factor,
        'detected_grid': grid_size,
        'output_path': str(output_path)
    }