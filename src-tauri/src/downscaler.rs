use image::{RgbaImage, Rgba, ImageBuffer};
use rustfft::{FftPlanner, num_complex::Complex};
use serde::{Deserialize, Serialize};
use std::path::PathBuf;
use crate::error::{Result, PixelsError};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DownscalerSettings {
    pub bg_removal_mode: BgRemovalMode,
    pub bg_tolerance: u8,
    pub bg_edge_tolerance: u8,
    pub preserve_dark_lines: bool,
    pub dark_line_threshold: u16,
    pub auto_trim: bool,
    pub enable_fine_tune: bool,
    pub pad_canvas: bool,
    pub canvas_multiple: u32,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum BgRemovalMode {
    Conservative,
    Aggressive,
    None,
}

impl Default for DownscalerSettings {
    fn default() -> Self {
        Self {
            bg_removal_mode: BgRemovalMode::Conservative,
            bg_tolerance: 15,
            bg_edge_tolerance: 30,
            preserve_dark_lines: true,
            dark_line_threshold: 100,
            auto_trim: true,
            enable_fine_tune: true,
            pad_canvas: true,
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

/// Detect grid size using FFT on edge profiles
fn detect_grid_size(img: &RgbaImage) -> Option<f32> {
    let (width, height) = img.dimensions();

    // Convert to grayscale
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

    // Horizontal differences
    for y in 0..height {
        for x in 0..(width - 1) {
            let idx = (y * width + x) as usize;
            let diff = (gray[idx + 1] - gray[idx]).abs();
            h_profile[x as usize] += diff;
        }
    }

    // Vertical differences
    for x in 0..width {
        for y in 0..(height - 1) {
            let idx = (y * width + x) as usize;
            let diff = (gray[idx + width as usize] - gray[idx]).abs();
            v_profile[y as usize] += diff;
        }
    }

    // Perform FFT on both profiles
    // Use Python's proven range: 6-20
    let h_period = fft_detect_period(&h_profile, 6.0, 20.0);
    let v_period = fft_detect_period(&v_profile, 6.0, 20.0);

    // Return average if both detected
    let result = match (h_period, v_period) {
        (Some(h), Some(v)) => Some((h + v) / 2.0),
        (Some(h), None) => Some(h),
        (None, Some(v)) => Some(v),
        (None, None) => None,
    };

    result
}

/// Detect period using FFT
fn fft_detect_period(signal: &[f32], min_period: f32, max_period: f32) -> Option<f32> {
    let n = signal.len();
    if n < 20 {
        return None;
    }

    // Prepare FFT input
    let mut planner = FftPlanner::new();
    let fft = planner.plan_fft_forward(n);

    let mut buffer: Vec<Complex<f32>> = signal
        .iter()
        .map(|&x| Complex::new(x, 0.0))
        .collect();

    fft.process(&mut buffer);

    // Find peak in frequency range
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

/// Public wrapper for testing
pub fn remove_background_public(img: &mut RgbaImage, settings: &DownscalerSettings) {
    remove_background(img, settings);
}

/// Sample RGB colors from canvas edges (Python's approach)
fn sample_edge_colors(img: &RgbaImage, sample_width: u32) -> Vec<[u8; 3]> {
    let (width, height) = img.dimensions();
    let mut colors = Vec::new();

    // Top edge
    for y in 0..sample_width.min(height) {
        for x in 0..width {
            let pixel = img.get_pixel(x, y);
            colors.push([pixel[0], pixel[1], pixel[2]]);
        }
    }

    // Bottom edge
    for y in (height.saturating_sub(sample_width))..height {
        for x in 0..width {
            let pixel = img.get_pixel(x, y);
            colors.push([pixel[0], pixel[1], pixel[2]]);
        }
    }

    // Left edge
    for y in 0..height {
        for x in 0..sample_width.min(width) {
            let pixel = img.get_pixel(x, y);
            colors.push([pixel[0], pixel[1], pixel[2]]);
        }
    }

    // Right edge
    for y in 0..height {
        for x in (width.saturating_sub(sample_width))..width {
            let pixel = img.get_pixel(x, y);
            colors.push([pixel[0], pixel[1], pixel[2]]);
        }
    }

    colors
}

/// Find most common background colors (Python's approach)
fn find_background_colors(edge_colors: &[[u8; 3]], max_colors: usize) -> Vec<[u8; 3]> {
    use std::collections::HashMap;

    // Round to nearest 16 (like Python)
    let mut color_counts: HashMap<[u8; 3], usize> = HashMap::new();
    for color in edge_colors {
        let rounded = [
            (color[0] / 16) * 16,
            (color[1] / 16) * 16,
            (color[2] / 16) * 16,
        ];
        *color_counts.entry(rounded).or_insert(0) += 1;
    }

    // Get top N colors
    let mut counts: Vec<_> = color_counts.into_iter().collect();
    counts.sort_by(|a, b| b.1.cmp(&a.1));
    counts.into_iter().take(max_colors).map(|(c, _)| c).collect()
}

/// RGB color distance (Python uses sum of absolute differences)
fn rgb_color_distance(c1: &[u8; 3], c2: &[u8; 3]) -> i32 {
    (c1[0] as i32 - c2[0] as i32).abs() +
    (c1[1] as i32 - c2[1] as i32).abs() +
    (c1[2] as i32 - c2[2] as i32).abs()
}

/// Check if edge pixel is likely content (Python's is_content_edge)
fn is_content_edge(img: &RgbaImage, x: u32, y: u32, window_size: u32) -> bool {
    let (width, height) = img.dimensions();

    let x_start = x.saturating_sub(window_size);
    let x_end = (x + window_size + 1).min(width);
    let y_start = y.saturating_sub(window_size);
    let y_end = (y + window_size + 1).min(height);

    // Calculate variance and color range in neighborhood
    let mut rgb_values: Vec<[u8; 3]> = Vec::new();
    for ny in y_start..y_end {
        for nx in x_start..x_end {
            let pixel = img.get_pixel(nx, ny);
            rgb_values.push([pixel[0], pixel[1], pixel[2]]);
        }
    }

    if rgb_values.is_empty() {
        return false;
    }

    // Calculate variance
    let mean: [f32; 3] = [
        rgb_values.iter().map(|p| p[0] as f32).sum::<f32>() / rgb_values.len() as f32,
        rgb_values.iter().map(|p| p[1] as f32).sum::<f32>() / rgb_values.len() as f32,
        rgb_values.iter().map(|p| p[2] as f32).sum::<f32>() / rgb_values.len() as f32,
    ];

    let variance: f32 = rgb_values.iter().map(|p| {
        let diff = [
            p[0] as f32 - mean[0],
            p[1] as f32 - mean[1],
            p[2] as f32 - mean[2],
        ];
        diff[0] * diff[0] + diff[1] * diff[1] + diff[2] * diff[2]
    }).sum::<f32>() / rgb_values.len() as f32;

    // Calculate color range (ptp = peak-to-peak = max - min)
    let min_vals = [
        rgb_values.iter().map(|p| p[0]).min().unwrap(),
        rgb_values.iter().map(|p| p[1]).min().unwrap(),
        rgb_values.iter().map(|p| p[2]).min().unwrap(),
    ];
    let max_vals = [
        rgb_values.iter().map(|p| p[0]).max().unwrap(),
        rgb_values.iter().map(|p| p[1]).max().unwrap(),
        rgb_values.iter().map(|p| p[2]).max().unwrap(),
    ];
    let color_range = (max_vals[0] - min_vals[0]) as i32 +
                      (max_vals[1] - min_vals[1]) as i32 +
                      (max_vals[2] - min_vals[2]) as i32;

    // Python's thresholds: variance > 100 or color_range > 50
    variance > 100.0 || color_range > 50
}

/// Remove background using Python's algorithm
fn remove_background(img: &mut RgbaImage, settings: &DownscalerSettings) {
    if matches!(settings.bg_removal_mode, BgRemovalMode::None) {
        return;
    }

    let (width, height) = img.dimensions();
    let tolerance = settings.bg_tolerance as i32;
    let edge_tolerance = settings.bg_edge_tolerance as i32;

    // Sample RGB colors from canvas edges (Python line 178)
    let edge_colors = sample_edge_colors(img, 5);

    // Find background colors (Python line 179)
    let bg_colors = find_background_colors(&edge_colors, 3);

    if bg_colors.is_empty() {
        return;
    }

    // Detect content edges in conservative mode (Python lines 161-170)
    let mut content_edge_mask = vec![vec![false; width as usize]; height as usize];
    if matches!(settings.bg_removal_mode, BgRemovalMode::Conservative) {
        let edge_width = 10u32;
        for y in 0..height {
            for x in 0..width {
                if x < edge_width || x >= width - edge_width ||
                   y < edge_width || y >= height - edge_width {
                    if is_content_edge(img, x, y, 3) {
                        content_edge_mask[y as usize][x as usize] = true;
                    }
                }
            }
        }
    }

    // Create background mask (Python lines 182-193)
    // Pixels matching background colors, with different tolerance for edges vs interior
    let mut mask = vec![vec![false; width as usize]; height as usize];
    let edge_zone = 10u32; // 10-pixel border for higher tolerance

    for y in 0..height {
        for x in 0..width {
            let pixel = img.get_pixel(x, y);
            let rgb = [pixel[0], pixel[1], pixel[2]];

            // Check if in edge zone
            let in_edge_zone = x < edge_zone || x >= width - edge_zone ||
                               y < edge_zone || y >= height - edge_zone;

            let threshold = if in_edge_zone { edge_tolerance } else { tolerance };

            // Check if matches any background color
            for bg_color in &bg_colors {
                if rgb_color_distance(&rgb, bg_color) <= threshold {
                    mask[y as usize][x as usize] = true;
                    break;
                }
            }
        }
    }

    // Protect content edges (Python line 199)
    if matches!(settings.bg_removal_mode, BgRemovalMode::Conservative) {
        for y in 0..height {
            for x in 0..width {
                if content_edge_mask[y as usize][x as usize] {
                    mask[y as usize][x as usize] = false;
                }
            }
        }
    }

    // Binary dilation of mask (Python line 209)
    // In conservative mode: 1 iteration, otherwise 2
    let dilation_iterations = if matches!(settings.bg_removal_mode, BgRemovalMode::Conservative) { 1 } else { 2 };
    let mut mask_dilated = mask.clone();
    for _ in 0..dilation_iterations {
        let mut new_mask = mask_dilated.clone();
        for y in 0..height as usize {
            for x in 0..width as usize {
                if mask_dilated[y][x] {
                    // Dilate to 4-connected neighbors
                    if y > 0 { new_mask[y - 1][x] = true; }
                    if y < height as usize - 1 { new_mask[y + 1][x] = true; }
                    if x > 0 { new_mask[y][x - 1] = true; }
                    if x < width as usize - 1 { new_mask[y][x + 1] = true; }
                }
            }
        }
        mask_dilated = new_mask;
    }

    // Create edge seed from canvas edges that are in dilated mask (Python lines 202-206)
    let mut edge_seed = vec![vec![false; width as usize]; height as usize];
    for x in 0..width as usize {
        if mask_dilated[0][x] {
            edge_seed[0][x] = true;
        }
        if mask_dilated[height as usize - 1][x] {
            edge_seed[height as usize - 1][x] = true;
        }
    }
    for y in 0..height as usize {
        if mask_dilated[y][0] {
            edge_seed[y][0] = true;
        }
        if mask_dilated[y][width as usize - 1] {
            edge_seed[y][width as usize - 1] = true;
        }
    }

    // Conservative flood fill (Python lines 211-214, function at 106-120)
    // Iteratively dilate the result while staying within mask and avoiding barriers
    let mut flooded = edge_seed.clone();
    let max_iterations = 500;

    for _iteration in 0..max_iterations {
        let mut new_flooded = flooded.clone();
        let mut changed = false;

        for y in 0..height as usize {
            for x in 0..width as usize {
                if flooded[y][x] {
                    // Dilate to 4-connected neighbors
                    let neighbors = [(0i32, -1i32), (0i32, 1i32), (-1i32, 0i32), (1i32, 0i32)];
                    for (dx, dy) in neighbors {
                        let nx = x as i32 + dx;
                        let ny = y as i32 + dy;

                        if nx >= 0 && nx < width as i32 && ny >= 0 && ny < height as i32 {
                            let nx = nx as usize;
                            let ny = ny as usize;

                            // Only grow into pixels in dilated mask and not already flooded
                            // (content_barrier would go here, but it's empty for greenhouse)
                            if mask_dilated[ny][nx] && !flooded[ny][nx] {
                                new_flooded[ny][nx] = true;
                                changed = true;
                            }
                        }
                    }
                }
            }
        }

        if !changed {
            break;
        }

        flooded = new_flooded;
    }

    // Apply the flood fill result: make flooded pixels transparent (Python line 218)
    for y in 0..height {
        for x in 0..width {
            if flooded[y as usize][x as usize] {
                let pixel = img.get_pixel(x, y);

                // Check if should preserve (dark lines)
                if settings.preserve_dark_lines {
                    let sum = pixel[0] as u16 + pixel[1] as u16 + pixel[2] as u16;
                    if sum < settings.dark_line_threshold {
                        continue;
                    }
                }

                // Make transparent
                img.put_pixel(x, y, Rgba([pixel[0], pixel[1], pixel[2], 0]));
            }
        }
    }
}

/// Calculate color distance
fn color_distance(c1: &Rgba<u8>, c2: &Rgba<u8>) -> i32 {
    let dr = c1[0] as i32 - c2[0] as i32;
    let dg = c1[1] as i32 - c2[1] as i32;
    let db = c1[2] as i32 - c2[2] as i32;
    (dr * dr + dg * dg + db * db).abs()
}

/// Measure information content (variance + edge count) - from Python
fn information_content(img: &RgbaImage) -> f32 {
    let (width, height) = img.dimensions();

    // Calculate variance of visible pixels
    let mut rgb_sum = [0.0f32; 3];
    let mut count = 0;

    for pixel in img.pixels() {
        if pixel[3] > 0 {
            rgb_sum[0] += pixel[0] as f32;
            rgb_sum[1] += pixel[1] as f32;
            rgb_sum[2] += pixel[2] as f32;
            count += 1;
        }
    }

    if count == 0 {
        return 0.0;
    }

    let mean = [
        rgb_sum[0] / count as f32,
        rgb_sum[1] / count as f32,
        rgb_sum[2] / count as f32,
    ];

    let mut variance = 0.0f32;
    for pixel in img.pixels() {
        if pixel[3] > 0 {
            for i in 0..3 {
                let diff = pixel[i] as f32 - mean[i];
                variance += diff * diff;
            }
        }
    }
    variance /= (count * 3) as f32;

    // Count edges (pixels with gradient > 20)
    let mut edge_count = 0;

    // Horizontal edges
    for y in 0..height {
        for x in 0..(width - 1) {
            let p1 = img.get_pixel(x, y);
            let p2 = img.get_pixel(x + 1, y);

            let gray1 = (p1[0] as f32 + p1[1] as f32 + p1[2] as f32) / 3.0;
            let gray2 = (p2[0] as f32 + p2[1] as f32 + p2[2] as f32) / 3.0;

            if (gray1 - gray2).abs() > 20.0 {
                edge_count += 1;
            }
        }
    }

    // Vertical edges
    for y in 0..(height - 1) {
        for x in 0..width {
            let p1 = img.get_pixel(x, y);
            let p2 = img.get_pixel(x, y + 1);

            let gray1 = (p1[0] as f32 + p1[1] as f32 + p1[2] as f32) / 3.0;
            let gray2 = (p2[0] as f32 + p2[1] as f32 + p2[2] as f32) / 3.0;

            if (gray1 - gray2).abs() > 20.0 {
                edge_count += 1;
            }
        }
    }

    variance + edge_count as f32 / 10.0
}

/// Calculate grid alignment score
fn grid_alignment_score(img: &RgbaImage, scale: f32) -> f32 {
    let (width, height) = img.dimensions();
    let new_width = (width as f32 / scale).round() as u32;
    let new_height = (height as f32 / scale).round() as u32;

    if new_width == 0 || new_height == 0 {
        return f32::MAX;
    }

    // Downscale using nearest neighbor
    let downscaled = image::imageops::resize(
        img,
        new_width,
        new_height,
        image::imageops::FilterType::Nearest,
    );

    // Upscale back
    let upscaled = image::imageops::resize(
        &downscaled,
        width,
        height,
        image::imageops::FilterType::Nearest,
    );

    // Calculate reconstruction error
    let mut rgb_error = 0.0f32;
    let mut alpha_error = 0.0f32;
    let mut semi_transparent = 0;
    let mut total_pixels = 0;

    for y in 0..height {
        for x in 0..width {
            let orig = img.get_pixel(x, y);
            let recon = upscaled.get_pixel(x, y);

            if orig[3] > 0 {
                total_pixels += 1;

                // RGB MAE
                for i in 0..3 {
                    rgb_error += (orig[i] as f32 - recon[i] as f32).abs();
                }

                // Alpha error
                alpha_error += (orig[3] as f32 - recon[3] as f32).abs();
            }
        }
    }

    // Count semi-transparent pixels in downscaled
    for pixel in downscaled.pixels() {
        if pixel[3] > 0 && pixel[3] < 255 {
            semi_transparent += 1;
        }
    }

    if total_pixels == 0 {
        return f32::MAX;
    }

    rgb_error /= (total_pixels * 3) as f32;
    alpha_error /= total_pixels as f32;
    let semi_ratio = semi_transparent as f32 / (new_width * new_height) as f32;

    rgb_error + 0.5 * alpha_error + semi_ratio * 100.0
}

/// Find optimal scale factor using combined scoring (Python's approach)
fn find_optimal_scale(img: &RgbaImage, min_scale: f32, max_scale: f32, grid_size: Option<f32>) -> f32 {
    // Narrow search range based on grid_size (Python lines 4-10)
    let (search_min, search_max) = if let Some(grid) = grid_size {
        if grid >= min_scale && grid <= max_scale {
            let narrowed_min = min_scale.max((grid - 2.0).floor());
            let narrowed_max = max_scale.min((grid + 2.0).ceil());
            (narrowed_min, narrowed_max)
        } else {
            (min_scale, max_scale)
        }
    } else {
        (min_scale, max_scale)
    };

    let mut best_scale = search_min;
    let mut best_combined_score = f32::MAX;
    let mut closest_to_grid: Option<(f32, f32)> = None; // (scale, combined_score)

    for scale_int in (search_min.ceil() as u32)..=(search_max.floor() as u32) {
        let scale = scale_int as f32;

        // Calculate alignment score
        let alignment_score = grid_alignment_score(img, scale);

        // Calculate information content
        let new_width = (img.width() as f32 / scale).round() as u32;
        let new_height = (img.height() as f32 / scale).round() as u32;
        let downscaled = image::imageops::resize(
            img, new_width, new_height,
            image::imageops::FilterType::Nearest,
        );
        let info = information_content(&downscaled);

        // Combined score (Python line 20)
        let combined_score = alignment_score - info / 1000.0;

        // Track best by combined score
        if combined_score < best_combined_score {
            best_combined_score = combined_score;
            best_scale = scale;
        }

        // Track closest to grid (Python lines 37-40)
        if let Some(grid) = grid_size {
            let distance = (scale - grid).abs();
            if let Some((prev_scale, _)) = closest_to_grid {
                let prev_distance = (prev_scale - grid).abs();
                if distance < prev_distance {
                    closest_to_grid = Some((scale, combined_score));
                }
            } else {
                closest_to_grid = Some((scale, combined_score));
            }
        }
    }

    // Python's special logic: if grid was detected and closest-to-grid is within 20% of best, use it
    if grid_size.is_some() {
        if let Some((closest_scale, closest_score)) = closest_to_grid {
            if closest_score < best_combined_score * 1.2 {
                best_scale = closest_scale;
            }
        }
    }

    best_scale
}

/// Fine-tune scale with fractional values - Python uses ONLY alignment score here
/// Centers search around grid_size if provided, otherwise around base_scale
fn fine_tune_scale(img: &RgbaImage, base_scale: f32, grid_size: Option<f32>) -> f32 {
    // Python centers around grid_size if provided
    let center = grid_size.unwrap_or(base_scale);

    let mut best_scale = center;  // Initialize to center, not base
    let mut best_score = grid_alignment_score(img, center);

    // Test fractional scales around center with 0.05 steps (Python uses 0.05)
    // Search range: center ± 1.0
    let steps = 40; // 2.0 range / 0.05 step = 40 steps

    for i in -steps..=steps {
        let scale = center + (i as f32 * 0.05);
        if scale < 1.0 {
            continue;
        }

        let score = grid_alignment_score(img, scale);

        // Python deduplicates by output size - we just track best score
        if score < best_score {
            best_score = score;
            best_scale = scale;
        }
    }

    best_scale
}

/// Trim transparent borders
fn auto_trim(img: &RgbaImage) -> RgbaImage {
    let (width, height) = img.dimensions();

    // Find content bounds
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
        // Empty image
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

/// Main downscale function
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

    // Remove background
    remove_background(&mut rgba, &settings);

    // Detect grid size
    let detected_scale = detect_grid_size(&rgba);

    let scale = if detected_scale.is_some() {
        // Python uses fixed range 6-20 for comprehensive search, but narrows based on grid
        let base_scale = find_optimal_scale(&rgba, 6.0, 20.0, detected_scale);

        // Fine-tune if enabled (Python centers around detected_scale, not base_scale!)
        if settings.enable_fine_tune {
            fine_tune_scale(&rgba, base_scale, detected_scale)
        } else {
            base_scale
        }
    } else {
        // No grid detected, use 1x
        1.0
    };

    // Downscale
    let _final_size = if scale > 1.0 {
        let new_width = (rgba.dimensions().0 as f32 / scale).round() as u32;
        let new_height = (rgba.dimensions().1 as f32 / scale).round() as u32;

        rgba = image::imageops::resize(
            &rgba,
            new_width,
            new_height,
            image::imageops::FilterType::Nearest,
        );

        (new_width, new_height)
    } else {
        rgba.dimensions()
    };

    // Auto trim if enabled
    if settings.auto_trim {
        rgba = auto_trim(&rgba);
    }

    // Pad canvas if enabled
    if settings.pad_canvas {
        rgba = pad_to_multiple(&rgba, settings.canvas_multiple);
    }

    // Save
    rgba.save(&output_path)?;

    Ok(DownscaleResult {
        original_size,
        final_size: rgba.dimensions(),
        scale_factor: scale,
        grid_detected: detected_scale.is_some(),
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_fft_detect_period() {
        // Create a simple periodic signal
        let signal: Vec<f32> = (0..100)
            .map(|i| (i as f32 * std::f32::consts::PI / 5.0).sin())
            .collect();

        let period = fft_detect_period(&signal, 5.0, 15.0);
        assert!(period.is_some());

        if let Some(p) = period {
            // Period should be around 10 (2π / (π/5) = 10)
            assert!((p - 10.0).abs() < 2.0);
        }
    }
}
