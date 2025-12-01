"""
Test Runner - Compare downscaling algorithms and measure accuracy.

Compares:
1. Block Uniformity (new approach)
2. Original Python FFT+Reconstruction approach

Against expected outputs to measure accuracy.
"""
import numpy as np
from PIL import Image
from pathlib import Path
import time
import sys

# Add archive folder to path for original algorithm
sys.path.insert(0, str(Path(__file__).parent.parent / 'archive'))

from block_uniformity import process_image as block_uniformity_process


def load_image(path: Path) -> np.ndarray:
    """Load image as RGBA numpy array."""
    return np.array(Image.open(path).convert('RGBA'))


def compare_images(img1: np.ndarray, img2: np.ndarray) -> dict:
    """
    Compare two images and return metrics.
    """
    # Check dimensions
    same_dims = img1.shape == img2.shape

    if not same_dims:
        return {
            'same_dimensions': False,
            'dim1': (img1.shape[1], img1.shape[0]),
            'dim2': (img2.shape[1], img2.shape[0]),
            'pixel_match': 0.0,
            'mae': float('inf'),
            'psnr': 0.0
        }

    # Pixel-perfect match percentage (ignoring fully transparent pixels)
    mask1 = img1[:, :, 3] > 0
    mask2 = img2[:, :, 3] > 0
    combined_mask = mask1 | mask2

    if not combined_mask.any():
        return {
            'same_dimensions': True,
            'dim1': (img1.shape[1], img1.shape[0]),
            'dim2': (img2.shape[1], img2.shape[0]),
            'pixel_match': 100.0,
            'mae': 0.0,
            'psnr': float('inf')
        }

    # Compare RGB where either image has content
    rgb1 = img1[:, :, :3][combined_mask].astype(np.float32)
    rgb2 = img2[:, :, :3][combined_mask].astype(np.float32)

    # Exact pixel match
    exact_matches = np.all(img1[:, :, :3] == img2[:, :, :3], axis=2) & combined_mask
    pixel_match = 100.0 * exact_matches.sum() / combined_mask.sum()

    # Mean Absolute Error
    mae = np.mean(np.abs(rgb1 - rgb2))

    # PSNR
    mse = np.mean((rgb1 - rgb2) ** 2)
    if mse == 0:
        psnr = float('inf')
    else:
        psnr = 10 * np.log10(255**2 / mse)

    return {
        'same_dimensions': True,
        'dim1': (img1.shape[1], img1.shape[0]),
        'dim2': (img2.shape[1], img2.shape[0]),
        'pixel_match': pixel_match,
        'mae': mae,
        'psnr': psnr
    }


def run_original_python(input_path: Path, output_path: Path) -> dict:
    """Run the original Python FFT+reconstruction algorithm."""
    try:
        from pixel_downscaler import downscale_image

        settings = {
            'bg_removal_mode': 'conservative',
            'bg_tolerance': 15,
            'bg_edge_tolerance': 25,
            'preserve_dark_lines': False,
            'dark_line_threshold': 50,
            'auto_trim': True,
            'enable_fine_tune': True,
            'pad_canvas': False,
            'canvas_multiple': 16,
        }

        t0 = time.time()
        result = downscale_image(input_path, output_path, settings)
        elapsed = time.time() - t0

        return {
            'success': True,
            'time': elapsed,
            'scale': result.get('scale_factor', 0),
            'grid_detected': result.get('detected_grid'),
            'final_size': result.get('final_size')
        }
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }


def run_block_uniformity(input_path: Path, output_path: Path) -> dict:
    """Run the new block uniformity algorithm."""
    try:
        t0 = time.time()
        result = block_uniformity_process(input_path, output_path, verbose=False)
        elapsed = time.time() - t0

        return {
            'success': True,
            'time': elapsed,
            'scale': result['scale'],
            'phase': result['phase'],
            'score': result['score'],
            'final_size': result['final_size'],
            'all_results': result['all_results']
        }
    except Exception as e:
        import traceback
        return {
            'success': False,
            'error': str(e),
            'traceback': traceback.format_exc()
        }


def find_expected(input_name: str, expected_dir: Path) -> Path | None:
    """Find the expected output file for a given input."""
    stem = input_name.replace('-original', '').replace('.png', '')

    # Try various naming patterns
    patterns = [
        f"{stem}-downscaled-python.png",
        f"downscaled-{stem}.png",
        f"{stem}-downscaled.png",
        f"{stem}.png",
    ]

    for pattern in patterns:
        path = expected_dir / pattern
        if path.exists():
            return path

    return None


def print_comparison(name: str, metrics: dict, indent: int = 4):
    """Pretty print comparison metrics."""
    ind = " " * indent
    if metrics['same_dimensions']:
        print(f"{ind}Dimensions: {metrics['dim1'][0]}x{metrics['dim1'][1]} [MATCH]")
        print(f"{ind}Pixel match: {metrics['pixel_match']:.1f}%")
        print(f"{ind}MAE: {metrics['mae']:.2f}")
        print(f"{ind}PSNR: {metrics['psnr']:.1f} dB")
    else:
        print(f"{ind}Dimensions: {metrics['dim1'][0]}x{metrics['dim1'][1]} vs {metrics['dim2'][0]}x{metrics['dim2'][1]} [MISMATCH]")


def main():
    script_dir = Path(__file__).parent.parent
    input_dir = script_dir / 'input'
    output_dir = script_dir / 'output'
    expected_dir = script_dir / 'expected'

    output_dir.mkdir(exist_ok=True)

    # Collect all test images
    test_images = sorted(input_dir.glob('*.png'))

    print("=" * 70)
    print("PIXEL ART DOWNSCALER - TEST COMPARISON")
    print("=" * 70)
    print()

    results_summary = []

    for input_path in test_images:
        print(f"Testing: {input_path.name}")
        print("-" * 50)

        # Find expected output
        expected_path = find_expected(input_path.name, expected_dir)

        # Output paths
        output_block = output_dir / f"{input_path.stem}-block-uniformity.png"
        output_python = output_dir / f"{input_path.stem}-original-python.png"

        # Run block uniformity
        print("  [1] Block Uniformity Algorithm:")
        result_block = run_block_uniformity(input_path, output_block)

        if result_block['success']:
            print(f"      Scale: {result_block['scale']}, Phase: {result_block['phase']}")
            print(f"      Output: {result_block['final_size'][0]}x{result_block['final_size'][1]}")
            print(f"      Time: {result_block['time']:.2f}s")

            # Compare to expected if available
            if expected_path:
                expected_img = load_image(expected_path)
                output_img = load_image(output_block)
                metrics = compare_images(output_img, expected_img)
                print(f"      vs Expected ({expected_path.name}):")
                print_comparison("block", metrics, indent=8)
        else:
            print(f"      ERROR: {result_block.get('error', 'Unknown')}")

        # Run original Python (if available)
        print()
        print("  [2] Original Python (FFT+Reconstruction):")
        result_python = run_original_python(input_path, output_python)

        if result_python['success']:
            print(f"      Scale: {result_python['scale']:.2f}, Grid: {result_python['grid_detected']}")
            print(f"      Output: {result_python['final_size'][0]}x{result_python['final_size'][1]}")
            print(f"      Time: {result_python['time']:.2f}s")

            if expected_path:
                expected_img = load_image(expected_path)
                output_img = load_image(output_python)
                metrics = compare_images(output_img, expected_img)
                print(f"      vs Expected ({expected_path.name}):")
                print_comparison("python", metrics, indent=8)
        else:
            print(f"      ERROR: {result_python.get('error', 'Unknown')}")

        print()

        # Store for summary
        results_summary.append({
            'input': input_path.name,
            'block_uniformity': result_block,
            'original_python': result_python,
            'expected': expected_path.name if expected_path else None
        })

    # Print summary table
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print()
    print(f"{'Image':<25} {'Block Unif.':<15} {'Orig Python':<15} {'Expected':<12}")
    print("-" * 70)

    for r in results_summary:
        name = r['input'][:24]

        if r['block_uniformity']['success']:
            bu_size = r['block_uniformity']['final_size']
            bu_str = f"{bu_size[0]}x{bu_size[1]}"
        else:
            bu_str = "ERROR"

        if r['original_python']['success']:
            py_size = r['original_python']['final_size']
            py_str = f"{py_size[0]}x{py_size[1]}"
        else:
            py_str = "ERROR"

        exp_str = r['expected'] if r['expected'] else "N/A"
        if len(exp_str) > 11:
            exp_str = exp_str[:11]

        print(f"{name:<25} {bu_str:<15} {py_str:<15} {exp_str:<12}")

    print()
    print("Output files saved to:", output_dir)


if __name__ == '__main__':
    main()
