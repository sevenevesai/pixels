//! AI Pixel Art Downscaler
//!
//! Detects the true pixel grid in AI-generated pixel art and downscales
//! to the actual resolution. Uses FFT for grid detection and block variance
//! with phase search for optimal alignment.

use image::{RgbaImage, Rgba, ImageBuffer};
use rustfft::{FftPlanner, num_complex::Complex};
use serde::{Deserialize, Serialize};
use std::path::PathBuf;
use crate::error::{Result, PixelsError};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DownscalerSettings {
    /// Auto-trim transparent borders before processing
    pub auto_trim: bool,
    /// Pad output canvas to a multiple of this value (0 = disabled)
    pub pad_canvas: bool,
    pub canvas_multiple: u32,
}

impl Default for DownscalerSettings {
    fn default() -> Self {
        Self {
            auto_trim: true,
            pad_canvas: false,
            canvas_multiple: 16,
        }
    }
}

#[derive(Debug, Clone, Serialize)]
pub struct DownscaleResult {
    pub original_size: (u32, u32),
    pub final_size: (u32, u32),
    pub scale_factor: f32,
    pub grid_detected: bool,
}

// ============================================================================
// FFT GRID DETECTION
// ============================================================================

/// Detect grid size using FFT on edge profiles
fn detect_grid_size(img: &RgbaImage) -> Option<f32> {
    let (width, height) = img.dimensions();

    // Convert to grayscale, masking transparent pixels
    let gray: Vec<f32> = (0..height)
        .flat_map(|y| {
            (0..width).map(move |x| {
                let pixel = img.get_pixel(x, y);
                if pixel[3] == 0 {
                    0.0
                } else {
                    (pixel[0] as f32 * 0.299 + pixel[1] as f32 * 0.587 + pixel[2] as f32 * 0.114) / 255.0
                }
            })
        })
        .collect();

    // Compute horizontal and vertical edge profiles
    let mut h_profile = vec![0.0f32; width as usize];
    let mut v_profile = vec![0.0f32; height as usize];

    for y in 0..height {
        for x in 0..(width - 1) {
            let idx = (y * width + x) as usize;
            let diff = (gray[idx + 1] - gray[idx]).abs();
            h_profile[x as usize] += diff;
        }
    }

    for x in 0..width {
        for y in 0..(height - 1) {
            let idx = (y * width + x) as usize;
            let diff = (gray[idx + width as usize] - gray[idx]).abs();
            v_profile[y as usize] += diff;
        }
    }

    let h_period = fft_detect_period(&h_profile, 6.0, 20.0);
    let v_period = fft_detect_period(&v_profile, 6.0, 20.0);

    match (h_period, v_period) {
        (Some(h), Some(v)) => Some((h + v) / 2.0),
        (Some(h), None) => Some(h),
        (None, Some(v)) => Some(v),
        (None, None) => None,
    }
}

/// Detect period using FFT
fn fft_detect_period(signal: &[f32], min_period: f32, max_period: f32) -> Option<f32> {
    let n = signal.len();
    if n < 20 {
        return None;
    }

    let mut planner = FftPlanner::new();
    let fft = planner.plan_fft_forward(n);

    let mean: f32 = signal.iter().sum::<f32>() / n as f32;
    let mut buffer: Vec<Complex<f32>> = signal
        .iter()
        .map(|&x| Complex::new(x - mean, 0.0))
        .collect();

    fft.process(&mut buffer);

    let min_freq = 1.0 / max_period;
    let max_freq = 1.0 / min_period;

    let min_idx = (min_freq * n as f32).max(1.0) as usize;
    let max_idx = (max_freq * n as f32).min((n / 2) as f32) as usize;

    if min_idx >= max_idx {
        return None;
    }

    let mut max_magnitude = 0.0f32;
    let mut peak_idx = 0;

    for i in min_idx..max_idx {
        let magnitude = buffer[i].norm();
        if magnitude > max_magnitude {
            max_magnitude = magnitude;
            peak_idx = i;
        }
    }

    if peak_idx > 0 && max_magnitude > 0.0 {
        Some(n as f32 / peak_idx as f32)
    } else {
        None
    }
}

// ============================================================================
// BLOCK VARIANCE + PHASE SEARCH (v4 Algorithm)
// ============================================================================

/// Result of scale detection for a single scale
#[derive(Debug, Clone)]
struct ScaleResult {
    scale: u32,
    phase_x: u32,
    phase_y: u32,
    variance: f32,
}

/// Calculate block variance at given scale and phase offset
/// Uses center region to avoid edge artifacts
fn calculate_block_variance(img: &RgbaImage, scale: u32, phase_x: u32, phase_y: u32) -> f32 {
    let (width, height) = img.dimensions();

    // Use center region (middle 2/3) to avoid edge artifacts
    let margin_y = height / 6;
    let margin_x = width / 6;

    let region_x_start = margin_x;
    let region_x_end = width - margin_x;
    let region_y_start = margin_y;
    let region_y_end = height - margin_y;

    let region_width = region_x_end - region_x_start;
    let region_height = region_y_end - region_y_start;

    // Adjust phase within the region
    let adj_px = phase_x % scale;
    let adj_py = phase_y % scale;

    let n_blocks_x = (region_width.saturating_sub(adj_px)) / scale;
    let n_blocks_y = (region_height.saturating_sub(adj_py)) / scale;

    if n_blocks_x < 2 || n_blocks_y < 2 {
        return f32::MAX;
    }

    let mut total_variance = 0.0f32;
    let mut block_count = 0u32;

    for block_y in 0..n_blocks_y {
        for block_x in 0..n_blocks_x {
            let start_x = region_x_start + adj_px + block_x * scale;
            let start_y = region_y_start + adj_py + block_y * scale;

            // Collect RGB values in this block
            let mut r_sum = 0.0f32;
            let mut g_sum = 0.0f32;
            let mut b_sum = 0.0f32;
            let mut pixel_count = 0u32;

            for dy in 0..scale {
                for dx in 0..scale {
                    let x = start_x + dx;
                    let y = start_y + dy;

                    if x < width && y < height {
                        let pixel = img.get_pixel(x, y);
                        r_sum += pixel[0] as f32;
                        g_sum += pixel[1] as f32;
                        b_sum += pixel[2] as f32;
                        pixel_count += 1;
                    }
                }
            }

            if pixel_count == 0 {
                continue;
            }

            let r_mean = r_sum / pixel_count as f32;
            let g_mean = g_sum / pixel_count as f32;
            let b_mean = b_sum / pixel_count as f32;

            // Calculate variance within block
            let mut variance = 0.0f32;
            for dy in 0..scale {
                for dx in 0..scale {
                    let x = start_x + dx;
                    let y = start_y + dy;

                    if x < width && y < height {
                        let pixel = img.get_pixel(x, y);
                        let dr = pixel[0] as f32 - r_mean;
                        let dg = pixel[1] as f32 - g_mean;
                        let db = pixel[2] as f32 - b_mean;
                        variance += dr * dr + dg * dg + db * db;
                    }
                }
            }

            variance /= (pixel_count * 3) as f32;
            total_variance += variance;
            block_count += 1;
        }
    }

    if block_count == 0 {
        return f32::MAX;
    }

    total_variance / block_count as f32
}

/// Find best phase offset for a given scale
fn find_best_phase_for_scale(img: &RgbaImage, scale: u32) -> (u32, u32, f32) {
    let mut best_var = f32::MAX;
    let mut best_px = 0u32;
    let mut best_py = 0u32;

    // Coarse search first
    let step = (scale / 3).max(1);

    let mut py = 0;
    while py < scale {
        let mut px = 0;
        while px < scale {
            let var = calculate_block_variance(img, scale, px, py);
            if var < best_var {
                best_var = var;
                best_px = px;
                best_py = py;
            }
            px += step;
        }
        py += step;
    }

    // Fine-tune around best
    if step > 1 {
        let search_start_y = best_py.saturating_sub(step);
        let search_end_y = (best_py + step + 1).min(scale);
        let search_start_x = best_px.saturating_sub(step);
        let search_end_x = (best_px + step + 1).min(scale);

        for py in search_start_y..search_end_y {
            for px in search_start_x..search_end_x {
                let var = calculate_block_variance(img, scale, px, py);
                if var < best_var {
                    best_var = var;
                    best_px = px;
                    best_py = py;
                }
            }
        }
    }

    (best_px, best_py, best_var)
}

/// Find optimal scale using block variance + phase search
/// Returns (scale, phase_x, phase_y)
fn find_optimal_scale_v4(img: &RgbaImage, grid_hint: Option<f32>) -> (u32, u32, u32) {
    let min_scale = 6u32;
    let max_scale = 20u32;

    let mut all_results: Vec<ScaleResult> = Vec::new();

    // Test all scales
    for scale in min_scale..=max_scale {
        let (px, py, var) = find_best_phase_for_scale(img, scale);
        all_results.push(ScaleResult {
            scale,
            phase_x: px,
            phase_y: py,
            variance: var,
        });
    }

    // Find minimum variance
    let min_var = all_results
        .iter()
        .map(|r| r.variance)
        .fold(f32::MAX, f32::min);

    if min_var == f32::MAX {
        // Fallback to grid hint or default
        let scale = grid_hint.map(|g| g.round() as u32).unwrap_or(10);
        return (scale.clamp(min_scale, max_scale), 0, 0);
    }

    // Find all "valid" scales (variance within 2x of minimum)
    let threshold = min_var * 2.0;
    let valid_scales: Vec<&ScaleResult> = all_results
        .iter()
        .filter(|r| r.variance <= threshold)
        .collect();

    let best = if valid_scales.is_empty() {
        // Fallback to minimum variance
        all_results
            .iter()
            .min_by(|a, b| a.variance.partial_cmp(&b.variance).unwrap())
            .unwrap()
    } else if let Some(hint) = grid_hint {
        // Prefer scale closest to FFT hint among valid scales
        valid_scales
            .iter()
            .min_by(|a, b| {
                let dist_a = (a.scale as f32 - hint).abs();
                let dist_b = (b.scale as f32 - hint).abs();
                dist_a.partial_cmp(&dist_b).unwrap()
            })
            .unwrap()
    } else {
        // Take largest valid scale
        valid_scales
            .iter()
            .max_by_key(|r| r.scale)
            .unwrap()
    };

    (best.scale, best.phase_x, best.phase_y)
}

/// Downsample image using phase-aware sampling
fn downsample_with_phase(img: &RgbaImage, scale: u32, phase_x: u32, phase_y: u32) -> RgbaImage {
    let (width, height) = img.dimensions();

    let out_width = (width.saturating_sub(phase_x)) / scale;
    let out_height = (height.saturating_sub(phase_y)) / scale;

    if out_width == 0 || out_height == 0 {
        return img.clone();
    }

    let mut result = ImageBuffer::new(out_width, out_height);
    let center_offset = scale / 2;

    for out_y in 0..out_height {
        for out_x in 0..out_width {
            let src_x = phase_x + out_x * scale + center_offset;
            let src_y = phase_y + out_y * scale + center_offset;

            if src_x < width && src_y < height {
                result.put_pixel(out_x, out_y, *img.get_pixel(src_x, src_y));
            }
        }
    }

    result
}

// ============================================================================
// UTILITY FUNCTIONS
// ============================================================================

/// Trim transparent borders
fn auto_trim(img: &RgbaImage) -> RgbaImage {
    let (width, height) = img.dimensions();

    let mut min_x = width;
    let mut max_x = 0;
    let mut min_y = height;
    let mut max_y = 0;

    for y in 0..height {
        for x in 0..width {
            if img.get_pixel(x, y)[3] > 0 {
                min_x = min_x.min(x);
                max_x = max_x.max(x);
                min_y = min_y.min(y);
                max_y = max_y.max(y);
            }
        }
    }

    if min_x > max_x || min_y > max_y {
        return ImageBuffer::new(1, 1);
    }

    let crop_width = max_x - min_x + 1;
    let crop_height = max_y - min_y + 1;

    image::imageops::crop_imm(img, min_x, min_y, crop_width, crop_height).to_image()
}

/// Pad canvas to multiple
fn pad_to_multiple(img: &RgbaImage, multiple: u32) -> RgbaImage {
    let (width, height) = img.dimensions();

    let new_width = ((width + multiple - 1) / multiple) * multiple;
    let new_height = ((height + multiple - 1) / multiple) * multiple;

    if new_width == width && new_height == height {
        return img.clone();
    }

    let mut canvas = ImageBuffer::from_pixel(new_width, new_height, Rgba([0, 0, 0, 0]));

    let offset_x = (new_width - width) / 2;
    let offset_y = (new_height - height) / 2;

    image::imageops::overlay(&mut canvas, img, offset_x as i64, offset_y as i64);

    canvas
}

// ============================================================================
// MAIN ENTRY POINT
// ============================================================================

/// Main downscale function using v4 algorithm (block variance + phase search)
pub fn downscale_image(
    input_path: PathBuf,
    output_path: PathBuf,
    settings: DownscalerSettings,
) -> Result<DownscaleResult> {
    // Load image
    let img = image::open(&input_path)
        .map_err(|e| PixelsError::Processing(format!("Failed to load {}: {}", input_path.display(), e)))?;

    let mut rgba = img.to_rgba8();
    let original_size = rgba.dimensions();

    // Step 1: Auto trim before scale detection (important for accurate FFT)
    if settings.auto_trim {
        rgba = auto_trim(&rgba);
    }

    // Step 2: Detect grid size using FFT
    let grid_hint = detect_grid_size(&rgba);

    // Step 3: Find optimal scale and phase using v4 algorithm
    let (scale, phase_x, phase_y) = find_optimal_scale_v4(&rgba, grid_hint);

    // Step 4: Downsample with phase-aware sampling
    let scale_factor = scale as f32;
    if scale > 1 {
        rgba = downsample_with_phase(&rgba, scale, phase_x, phase_y);
    }

    // Step 5: Pad canvas if enabled
    if settings.pad_canvas {
        rgba = pad_to_multiple(&rgba, settings.canvas_multiple);
    }

    // Ensure output directory exists
    if let Some(parent) = output_path.parent() {
        std::fs::create_dir_all(parent)?;
    }

    // Save result
    rgba.save(&output_path)?;

    Ok(DownscaleResult {
        original_size,
        final_size: rgba.dimensions(),
        scale_factor,
        grid_detected: grid_hint.is_some(),
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_fft_detect_period() {
        let signal: Vec<f32> = (0..100)
            .map(|i| (i as f32 * std::f32::consts::PI / 5.0).sin())
            .collect();

        let period = fft_detect_period(&signal, 5.0, 15.0);
        assert!(period.is_some());

        if let Some(p) = period {
            assert!((p - 10.0).abs() < 2.0);
        }
    }

    #[test]
    fn test_block_variance_uniform() {
        // Create a simple uniform image - variance should be 0
        let img: RgbaImage = ImageBuffer::from_pixel(100, 100, Rgba([128, 128, 128, 255]));
        let var = calculate_block_variance(&img, 10, 0, 0);
        assert!(var < 0.1, "Uniform image should have near-zero variance");
    }
}
