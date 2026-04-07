//! AI Pixel Art Downscaler
//!
//! Detects the true pixel grid in AI-generated pixel art and downscales
//! to the actual resolution. Uses edge consistency profiles with Harmonic
//! Product Spectrum (HPS) analysis for grid detection, and block variance
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

/// Result of scale detection analysis
#[derive(Debug, Clone, Serialize)]
pub struct ScaleDetectionResult {
    /// Detected scale factor (1 = native pixel art, >1 = AI upscaled)
    pub detected_scale: u32,
    /// Whether a clear pixel grid was detected via FFT
    pub grid_detected: bool,
    /// Confidence in the detection (0.0 - 1.0)
    pub confidence: f32,
    /// Whether this image appears to be AI-upscaled pixel art
    pub is_ai_upscaled: bool,
    /// Original image dimensions
    pub dimensions: (u32, u32),
    /// Estimated native dimensions after downscaling
    pub estimated_native_size: (u32, u32),
}

/// Settings for manual downscale with user-specified dimensions
#[derive(Debug, Clone, Deserialize)]
pub struct ManualDownscaleSettings {
    /// Target width in pixels
    pub target_width: u32,
    /// Target height in pixels
    pub target_height: u32,
    /// Auto-trim transparent borders before downscaling
    pub auto_trim: bool,
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
// SCALE DETECTION v5: Edge Profile Autocorrelation
// ============================================================================
//
// AI-upscaled pixel art has a periodic grid structure. The edge profile
// (sum of color differences at each row/column) should be periodic with
// period = true scale factor.
//
// We compute RGB edge profiles, then for each candidate scale S:
// 1. Autocorrelation at lag S: how periodic is the edge profile at this interval?
// 2. Phase search via block variance: find the grid alignment within the image
// 3. Divisor analysis: prefer fundamental frequency over harmonics (S over 2S)

/// Result of scale detection for a single scale
#[derive(Debug, Clone)]
#[allow(dead_code)]
struct ScaleResult {
    scale: u32,
    phase_x: u32,
    phase_y: u32,
    variance: f32,
    /// Autocorrelation-based periodicity score (higher = stronger grid)
    edge_score: f32,
}

/// Compute edge CONSISTENCY profiles for horizontal and vertical directions.
///
/// Instead of summing edge magnitudes (which are dominated by strong content
/// edges), this counts what FRACTION of rows/columns have ANY edge at each
/// position, using a low threshold.
///
/// At true grid boundaries, most rows have at least a subtle color change
/// (even between same-colored blocks, AI upscalers create slight blurring).
/// At positions within blocks, very few rows have any change.
///
/// This makes the profile specific to grid structure regardless of content.
///
/// H[x] = fraction of rows where |pixel(x,y) - pixel(x-1,y)| > threshold
/// V[y] = fraction of columns where |pixel(x,y) - pixel(x,y-1)| > threshold
fn compute_edge_profiles(img: &RgbaImage) -> (Vec<f32>, Vec<f32>) {
    let (width, height) = img.dimensions();

    // Very low threshold: detect even the most subtle AI blurring at grid
    // boundaries. Within blocks, pixel values are nearly identical (diff 0-1).
    // At grid boundaries, even between same-colored blocks, AI creates slight
    // color variations (diff 2-5+). Using threshold=2 maximizes sensitivity.
    let threshold = 2.0f32;

    let mut h_profile = vec![0.0f32; width as usize];
    let mut v_profile = vec![0.0f32; height as usize];

    // Count of valid (opaque) pixel pairs per column/row for normalization
    let mut h_count = vec![0u32; width as usize];
    let mut v_count = vec![0u32; height as usize];

    // Horizontal: for each column x, count rows where there's an edge
    for y in 0..height {
        for x in 1..width {
            let p = img.get_pixel(x, y);
            let q = img.get_pixel(x - 1, y);
            if p[3] > 128 && q[3] > 128 {
                h_count[x as usize] += 1;
                let dr = (p[0] as f32 - q[0] as f32).abs();
                let dg = (p[1] as f32 - q[1] as f32).abs();
                let db = (p[2] as f32 - q[2] as f32).abs();
                let max_diff = dr.max(dg).max(db);
                if max_diff > threshold {
                    h_profile[x as usize] += 1.0;
                }
            }
        }
    }

    // Vertical: for each row y, count columns where there's an edge
    for y in 1..height {
        for x in 0..width {
            let p = img.get_pixel(x, y);
            let q = img.get_pixel(x, y - 1);
            if p[3] > 128 && q[3] > 128 {
                v_count[y as usize] += 1;
                let dr = (p[0] as f32 - q[0] as f32).abs();
                let dg = (p[1] as f32 - q[1] as f32).abs();
                let db = (p[2] as f32 - q[2] as f32).abs();
                let max_diff = dr.max(dg).max(db);
                if max_diff > threshold {
                    v_profile[y as usize] += 1.0;
                }
            }
        }
    }

    // Normalize to fractions (0.0 - 1.0)
    for x in 0..width as usize {
        if h_count[x] > 0 {
            h_profile[x] /= h_count[x] as f32;
        }
    }
    for y in 0..height as usize {
        if v_count[y] > 0 {
            v_profile[y] /= v_count[y] as f32;
        }
    }

    (h_profile, v_profile)
}

/// Compute normalized autocorrelation of a profile at a specific lag.
/// Uses the center region to avoid edge artifacts.
fn autocorrelation_at_lag(profile: &[f32], lag: usize) -> f32 {
    let n = profile.len();
    if lag >= n / 2 || n < 20 {
        return 0.0;
    }

    // Use center 3/4 to avoid edge artifacts
    let margin = n / 8;
    let start = margin;
    let end = n - margin - lag;

    if end <= start {
        return 0.0;
    }

    // Subtract local mean for proper correlation
    let region = &profile[start..end + lag];
    let mean: f32 = region.iter().sum::<f32>() / region.len() as f32;

    let mut numerator = 0.0f64;
    let mut denom_a = 0.0f64;
    let mut denom_b = 0.0f64;

    for i in start..end {
        let a = (profile[i] - mean) as f64;
        let b = (profile[i + lag] - mean) as f64;
        numerator += a * b;
        denom_a += a * a;
        denom_b += b * b;
    }

    let denom = (denom_a * denom_b).sqrt();
    if denom < 1e-10 {
        return 0.0;
    }

    (numerator / denom) as f32
}

/// Compute Harmonic Product Spectrum score for a candidate scale.
/// For period S, checks FFT power at frequencies k/S for k=1,2,3,...
/// The true fundamental frequency accumulates power from all its harmonics.
fn harmonic_product_score(fft_magnitudes: &[f32], n: usize, scale: u32) -> f32 {
    if scale < 2 || n < 4 {
        return 0.0;
    }

    let max_harmonics = 6;
    let mut total_power = 0.0f64;
    let mut harmonic_count = 0;

    for k in 1..=max_harmonics {
        // Frequency index for the k-th harmonic of period S
        let freq_idx_f = (k as f64 * n as f64) / scale as f64;
        let freq_idx = freq_idx_f.round() as usize;

        if freq_idx >= n / 2 || freq_idx == 0 {
            break;
        }

        // Sample a small window around the peak (±1 bin) to handle spectral leakage
        let lo = freq_idx.saturating_sub(1);
        let hi = (freq_idx + 2).min(n / 2);
        let mut best_mag = 0.0f32;
        for i in lo..hi {
            best_mag = best_mag.max(fft_magnitudes[i]);
        }

        // Weight lower harmonics more (fundamental is most important)
        let weight = 1.0 / k as f64;
        total_power += best_mag as f64 * weight;
        harmonic_count += 1;
    }

    if harmonic_count == 0 {
        return 0.0;
    }

    (total_power / harmonic_count as f64) as f32
}

/// Compute FFT magnitude spectrum from an edge profile
fn compute_fft_magnitudes(profile: &[f32]) -> Vec<f32> {
    let n = profile.len();
    if n < 20 {
        return Vec::new();
    }

    let mut planner = FftPlanner::new();
    let fft = planner.plan_fft_forward(n);

    let mean: f32 = profile.iter().sum::<f32>() / n as f32;
    let mut buffer: Vec<Complex<f32>> = profile
        .iter()
        .map(|&x| Complex::new(x - mean, 0.0))
        .collect();

    fft.process(&mut buffer);

    buffer.iter().map(|c| c.norm()).collect()
}

/// Combined scale scoring using multiple signals:
/// 1. Harmonic Product Spectrum (FFT-based, handles sparse edges well)
/// 2. Autocorrelation (confirms periodicity directly)
/// 3. Block variance (lower = better grid alignment)
fn combined_score_for_scale(
    h_profile: &[f32],
    v_profile: &[f32],
    h_fft: &[f32],
    v_fft: &[f32],
    scale: u32,
) -> f32 {
    let h_n = h_profile.len();
    let v_n = v_profile.len();

    // HPS score (averaged across H and V)
    let hps_h = harmonic_product_score(h_fft, h_n, scale);
    let hps_v = harmonic_product_score(v_fft, v_n, scale);
    let hps = (hps_h + hps_v) / 2.0;

    // Autocorrelation score
    let lag = scale as usize;
    let ac_h = autocorrelation_at_lag(h_profile, lag);
    let ac_v = autocorrelation_at_lag(v_profile, lag);
    let ac = ((ac_h + ac_v) / 2.0).max(0.0);

    // Combined: HPS is the primary signal, autocorrelation provides confirmation
    hps + ac * hps * 0.5
}

/// Find the best phase for a given scale using block variance minimization.
fn find_best_phase_for_scale(img: &RgbaImage, scale: u32) -> (u32, u32, f32) {
    let mut best_var = f32::MAX;
    let mut best_px = 0u32;
    let mut best_py = 0u32;

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
        let sy = best_py.saturating_sub(step);
        let ey = (best_py + step + 1).min(scale);
        let sx = best_px.saturating_sub(step);
        let ex = (best_px + step + 1).min(scale);

        for py in sy..ey {
            for px in sx..ex {
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

/// Calculate block variance at given scale and phase offset.
/// Measures how uniform each NxN block is (lower = better grid alignment).
fn calculate_block_variance(img: &RgbaImage, scale: u32, phase_x: u32, phase_y: u32) -> f32 {
    let (width, height) = img.dimensions();

    // Center region to avoid edge artifacts
    let margin_x = width / 6;
    let margin_y = height / 6;
    let rx_start = margin_x;
    let rx_end = width - margin_x;
    let ry_start = margin_y;
    let ry_end = height - margin_y;

    let adj_px = phase_x % scale;
    let adj_py = phase_y % scale;

    let n_bx = (rx_end - rx_start).saturating_sub(adj_px) / scale;
    let n_by = (ry_end - ry_start).saturating_sub(adj_py) / scale;

    if n_bx < 2 || n_by < 2 {
        return f32::MAX;
    }

    let step = ((n_bx * n_by) as f32 / 400.0).sqrt().ceil().max(1.0) as u32;
    let mut total_var = 0.0f32;
    let mut count = 0u32;

    let mut by = 0;
    while by < n_by {
        let mut bx = 0;
        while bx < n_bx {
            let sx = rx_start + adj_px + bx * scale;
            let sy = ry_start + adj_py + by * scale;
            let mut r_sum = 0.0f32;
            let mut g_sum = 0.0f32;
            let mut b_sum = 0.0f32;
            let mut pc = 0u32;
            for dy in 0..scale {
                for dx in 0..scale {
                    let x = sx + dx;
                    let y = sy + dy;
                    if x < width && y < height {
                        let p = img.get_pixel(x, y);
                        if p[3] > 128 {
                            r_sum += p[0] as f32;
                            g_sum += p[1] as f32;
                            b_sum += p[2] as f32;
                            pc += 1;
                        }
                    }
                }
            }
            if pc > 1 {
                let rm = r_sum / pc as f32;
                let gm = g_sum / pc as f32;
                let bm = b_sum / pc as f32;
                let mut v = 0.0f32;
                for dy in 0..scale {
                    for dx in 0..scale {
                        let x = sx + dx;
                        let y = sy + dy;
                        if x < width && y < height {
                            let p = img.get_pixel(x, y);
                            if p[3] > 128 {
                                let dr = p[0] as f32 - rm;
                                let dg = p[1] as f32 - gm;
                                let db = p[2] as f32 - bm;
                                v += dr * dr + dg * dg + db * db;
                            }
                        }
                    }
                }
                total_var += v / (pc * 3) as f32;
                count += 1;
            }
            bx += step;
        }
        by += step;
    }

    if count == 0 { f32::MAX } else { total_var / count as f32 }
}

/// Find optimal scale using v5 algorithm (edge consistency + HPS + autocorrelation)
/// Returns (scale, phase_x, phase_y, all_results)
fn find_optimal_scale_v4_with_results(img: &RgbaImage, _grid_hint: Option<f32>) -> (u32, u32, u32, Vec<ScaleResult>) {
    let min_scale = 3u32;
    let max_scale = 20u32;

    // Step 1: Compute edge profiles (one-time cost)
    let (h_profile, v_profile) = compute_edge_profiles(img);

    // Step 2: Compute FFT magnitudes (one-time)
    let h_fft = compute_fft_magnitudes(&h_profile);
    let v_fft = compute_fft_magnitudes(&v_profile);

    // Step 3: Score each candidate scale using combined HPS + autocorrelation
    let mut all_results: Vec<ScaleResult> = Vec::new();

    for scale in min_scale..=max_scale {
        let score = combined_score_for_scale(&h_profile, &v_profile, &h_fft, &v_fft, scale);
        let (px, py, var) = find_best_phase_for_scale(img, scale);
        all_results.push(ScaleResult {
            scale,
            phase_x: px,
            phase_y: py,
            variance: var,
            edge_score: score,
        });
    }

    all_results.sort_by_key(|r| r.scale);

    // Step 4: Select best scale with variance-aware scoring.
    //
    // Edge score alone can produce false positives at high scales (e.g., scale=19
    // scoring high due to noise). Block variance directly measures grid quality:
    // true grid alignment produces uniform blocks (low variance), while false
    // detections at high scales span content boundaries (high variance).
    //
    // We use a combined score: edge_score_normalized + variance_rank_bonus.
    // This ensures a scale can't win on edge score alone if its variance is
    // much worse than alternatives.

    let max_edge = all_results.iter().map(|r| r.edge_score).fold(0.0f32, f32::max);

    if max_edge <= 0.0 {
        return (8, 0, 0, all_results);
    }

    let min_var = all_results.iter().map(|r| r.variance).fold(f32::MAX, f32::min);
    let max_var = all_results.iter().map(|r| r.variance).fold(0.0f32, f32::max);
    let var_range = max_var - min_var;

    // Combined score using geometric mean of edge and variance signals.
    // This heavily penalizes candidates that score well on one dimension
    // but poorly on the other — a false positive at scale=19 with high
    // edge score but terrible variance gets suppressed.
    //
    // We add a small floor (0.05) to prevent zero edge scores from
    // completely eliminating otherwise good variance candidates.
    let combined_scores: Vec<f32> = all_results.iter().map(|r| {
        let edge_norm = (r.edge_score / max_edge).max(0.05);
        let var_norm = if var_range > 0.0 {
            ((max_var - r.variance) / var_range).max(0.05)
        } else {
            0.5
        };
        (edge_norm * var_norm).sqrt()  // geometric mean
    }).collect();

    let max_combined = combined_scores.iter().cloned().fold(0.0f32, f32::max);

    // Candidates: within 80% of max combined score
    let threshold = max_combined * 0.80;
    let mut candidates: Vec<(usize, &ScaleResult)> = all_results
        .iter()
        .enumerate()
        .filter(|(i, _)| combined_scores[*i] >= threshold)
        .collect();
    candidates.sort_by_key(|(_, r)| r.scale);

    let best = if candidates.is_empty() {
        // Fallback: pick highest combined score
        let (best_idx, _) = combined_scores.iter().enumerate()
            .max_by(|(_, a), (_, b)| a.partial_cmp(b).unwrap())
            .unwrap();
        &all_results[best_idx]
    } else {
        // Among candidates, prefer smallest (fundamental frequency).
        // But if a larger candidate scores much better, pick that instead
        // (unless the smaller one divides it evenly — then it's a harmonic).
        let (_, mut pick) = candidates[0];
        let mut pick_score = combined_scores[candidates[0].0];

        for &(i, c) in &candidates[1..] {
            if combined_scores[i] > pick_score * 1.20 && c.scale % pick.scale != 0 {
                pick = c;
                pick_score = combined_scores[i];
            }
        }

        pick
    };

    (best.scale, best.phase_x, best.phase_y, all_results)
}

/// Find optimal scale using v5 algorithm
/// Returns (scale, phase_x, phase_y)
fn find_optimal_scale_v4(img: &RgbaImage, grid_hint: Option<f32>) -> (u32, u32, u32) {
    let (scale, px, py, _) = find_optimal_scale_v4_with_results(img, grid_hint);
    (scale, px, py)
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
// PUBLIC API
// ============================================================================

/// Public wrapper: Auto-trim transparent borders from an image
pub fn auto_trim_image(img: &RgbaImage) -> RgbaImage {
    auto_trim(img)
}

/// Public wrapper: Detect grid size using FFT
pub fn detect_grid_for_image(img: &RgbaImage) -> Option<f32> {
    detect_grid_size(img)
}

/// Public wrapper: Find optimal scale and phase
pub fn find_optimal_scale_for_image(img: &RgbaImage, grid_hint: Option<f32>) -> (u32, u32, u32) {
    find_optimal_scale_v4(img, grid_hint)
}

/// Public wrapper: Downsample with phase-aware sampling
pub fn downsample_image(img: &RgbaImage, scale: u32, phase_x: u32, phase_y: u32) -> RgbaImage {
    downsample_with_phase(img, scale, phase_x, phase_y)
}

/// Downscale image to exact target dimensions using nearest-neighbor sampling
/// This is for manual user-specified dimensions when auto-detection isn't right
pub fn downscale_to_dimensions(img: &RgbaImage, target_width: u32, target_height: u32) -> RgbaImage {
    let (src_width, src_height) = img.dimensions();

    if target_width == 0 || target_height == 0 {
        return img.clone();
    }

    // If upscaling or same size, just return as-is
    if target_width >= src_width && target_height >= src_height {
        return img.clone();
    }

    // Calculate scale factors
    let scale_x = src_width as f32 / target_width as f32;
    let scale_y = src_height as f32 / target_height as f32;

    let mut result = ImageBuffer::new(target_width, target_height);

    for out_y in 0..target_height {
        for out_x in 0..target_width {
            // Sample from center of source region
            let src_x = ((out_x as f32 + 0.5) * scale_x) as u32;
            let src_y = ((out_y as f32 + 0.5) * scale_y) as u32;

            // Clamp to valid range
            let src_x = src_x.min(src_width - 1);
            let src_y = src_y.min(src_height - 1);

            result.put_pixel(out_x, out_y, *img.get_pixel(src_x, src_y));
        }
    }

    result
}

/// Downscale image with manual settings (target dimensions)
/// Returns PNG bytes for preview
pub fn downscale_manual_preview(img: &RgbaImage, settings: &ManualDownscaleSettings) -> RgbaImage {
    let mut working = img.clone();

    // Auto-trim if enabled
    if settings.auto_trim {
        working = auto_trim(&working);
    }

    // Downscale to target dimensions
    downscale_to_dimensions(&working, settings.target_width, settings.target_height)
}

/// Detect the scale factor of an image without modifying it
/// Returns detection results including whether the image appears to be AI-upscaled
pub fn detect_scale(input_path: PathBuf) -> Result<ScaleDetectionResult> {
    // Load image
    let img = image::open(&input_path)
        .map_err(|e| PixelsError::Processing(format!("Failed to load {}: {}", input_path.display(), e)))?;

    let rgba = img.to_rgba8();
    let dimensions = rgba.dimensions();

    // Trim for accurate detection (same as downscale_image does)
    let trimmed = auto_trim(&rgba);

    // Find optimal scale using v5 algorithm (edge consistency + HPS)
    let grid_hint = detect_grid_size(&trimmed);
    let (scale, _phase_x, _phase_y, all_results) = find_optimal_scale_v4_with_results(&trimmed, grid_hint);

    // Calculate confidence from multiple signals:
    // 1. Edge score separation (how much better is our pick vs runner-up)
    // 2. Variance separation (how much lower is our pick's block variance)
    let detected_result = all_results.iter().find(|r| r.scale == scale);
    let detected_edge = detected_result.map(|r| r.edge_score).unwrap_or(0.0);
    let detected_var = detected_result.map(|r| r.variance).unwrap_or(f32::MAX);

    let mut other_scores: Vec<f32> = all_results.iter()
        .filter(|r| r.scale != scale)
        .map(|r| r.edge_score)
        .collect();
    other_scores.sort_by(|a, b| b.partial_cmp(a).unwrap());
    let second_best = other_scores.first().copied().unwrap_or(0.0);

    let edge_confidence = if detected_edge > 0.0 && second_best > 0.0 {
        // Ratio-based confidence: how much better is our pick vs runner-up
        let ratio = detected_edge / second_best;
        // ratio=1.0 → 0.0 confidence, ratio=2.0 → 0.6, ratio=3.0 → 0.8, ratio=5.0 → 0.9
        (1.0 - 1.0 / ratio).clamp(0.0, 1.0)
    } else if detected_edge > 0.0 {
        0.8
    } else {
        0.0
    };

    // Variance-based confidence: compare detected scale's variance to the median
    // Low variance relative to others indicates good grid alignment
    let mut other_variances: Vec<f32> = all_results.iter()
        .filter(|r| r.scale != scale && r.variance < f32::MAX)
        .map(|r| r.variance)
        .collect();
    other_variances.sort_by(|a, b| a.partial_cmp(b).unwrap());
    let median_var = if !other_variances.is_empty() {
        other_variances[other_variances.len() / 2]
    } else {
        detected_var
    };
    let variance_confidence = if detected_var > 0.0 && median_var > 0.0 {
        // If detected variance is much lower than median, high confidence
        // ratio=1.0 → 0.0, ratio=2.0 → 0.5, ratio=3.0 → 0.67
        let ratio = median_var / detected_var;
        (1.0 - 1.0 / ratio).clamp(0.0, 1.0)
    } else {
        0.0
    };

    // Use whichever signal is stronger
    let confidence = edge_confidence.max(variance_confidence);

    // Consider it AI-upscaled if scale > 1 and we have some confidence
    let is_ai_upscaled = scale > 1 && confidence > 0.1;

    // Estimate native size
    let estimated_native_size = if scale > 1 {
        (dimensions.0 / scale, dimensions.1 / scale)
    } else {
        dimensions
    };

    Ok(ScaleDetectionResult {
        detected_scale: scale,
        grid_detected: grid_hint.is_some(),
        confidence,
        is_ai_upscaled,
        dimensions,
        estimated_native_size,
    })
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

    #[test]
    fn diagnostic_test_all_images() {
        let test_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR")).parent().unwrap().join("downscale_tests");
        let input_dir = test_dir.join("input");
        let expected_dir = test_dir.join("expected");

        let test_cases = vec![
            ("chair-1.png", "downscaled-chair-1.png"),
            ("greenhouse-original.png", "greenhouse-downscaled-python.png"),
            ("grindstone-original.png", "grindstone-downscaled-python.png"),
            ("snowman-original.png", "snowman-downscaled.png"),
            ("truck-original.png", "truck-downscaled-python.png"),
        ];

        println!("\n{}", "=".repeat(60));
        println!("DOWNSCALER DIAGNOSTIC REPORT");
        println!("{}", "=".repeat(60));

        for (input_name, expected_name) in &test_cases {
            let input_path = input_dir.join(input_name);
            let expected_path = expected_dir.join(expected_name);

            if !input_path.exists() {
                println!("\n[SKIP] {} - file not found", input_name);
                continue;
            }

            let img = image::open(&input_path).unwrap().to_rgba8();
            let (w, h) = img.dimensions();

            // Load expected to get target dimensions
            let expected_dims = if expected_path.exists() {
                let exp = image::open(&expected_path).unwrap().to_rgba8();
                Some(exp.dimensions())
            } else {
                None
            };

            // Trim (same as detect_scale does)
            let trimmed = auto_trim(&img);
            let (tw, th) = trimmed.dimensions();

            // FFT detection
            let grid_hint = detect_grid_size(&trimmed);

            // Block variance detection (current algorithm: scales 6-20)
            let (scale, px, py, all_results) = find_optimal_scale_v4_with_results(&trimmed, grid_hint);

            // What dimensions would we get?
            let detected_out_w = tw / scale;
            let detected_out_h = th / scale;

            // Calculate what scale SHOULD be based on expected
            let ideal_scale = expected_dims.map(|(ew, _eh)| {
                (tw as f32 / ew as f32).round() as u32
            });

            println!("\n--- {} ---", input_name);
            println!("  Input:       {}x{}", w, h);
            println!("  Trimmed:     {}x{}", tw, th);
            println!("  FFT hint:    {:?}", grid_hint);
            println!("  Detected:    scale={}, phase=({},{})", scale, px, py);
            println!("  Output dims: {}x{}", detected_out_w, detected_out_h);
            if let Some((ew, eh)) = expected_dims {
                println!("  Expected:    {}x{}", ew, eh);
                println!("  Ideal scale: {:?}", ideal_scale);
                let correct = detected_out_w == ew && detected_out_h == eh;
                println!("  MATCH:       {}", if correct { "YES" } else { "NO <<<" });
            }

            // Print full landscape for all scales
            println!("  Full landscape (scale: edge, var):");
            for r in &all_results {
                let marker = if Some(r.scale) == ideal_scale { " <-- ideal" } else { "" };
                println!("    scale={:2}: edge={:12.1}, var={:8.2}{}", r.scale, r.edge_score, r.variance, marker);
            }
        }

        println!("\n{}", "=".repeat(60));
    }
}
