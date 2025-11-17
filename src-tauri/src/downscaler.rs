use image::{RgbaImage, Rgba, ImageBuffer};
use rustfft::{FftPlanner, num_complex::Complex};
use serde::{Deserialize, Serialize};
use std::path::PathBuf;
use std::collections::VecDeque;
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
    // Expanded range to catch smaller grids for sharper results
    let h_period = fft_detect_period(&h_profile, 4.0, 24.0);
    let v_period = fft_detect_period(&v_profile, 4.0, 24.0);

    // Return average if both detected
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

/// Remove background using flood fill
fn remove_background(img: &mut RgbaImage, settings: &DownscalerSettings) {
    if matches!(settings.bg_removal_mode, BgRemovalMode::None) {
        return;
    }

    let (width, height) = img.dimensions();
    let tolerance = settings.bg_tolerance as i32;
    let edge_tolerance = settings.bg_edge_tolerance as i32;

    // Sample edge colors to determine background
    let mut edge_colors: Vec<Rgba<u8>> = Vec::new();

    // Top and bottom edges
    for x in 0..width {
        edge_colors.push(*img.get_pixel(x, 0));
        edge_colors.push(*img.get_pixel(x, height - 1));
    }

    // Left and right edges
    for y in 0..height {
        edge_colors.push(*img.get_pixel(0, y));
        edge_colors.push(*img.get_pixel(width - 1, y));
    }

    // Find most common edge color
    let bg_color = edge_colors.iter()
        .max_by_key(|c| {
            edge_colors.iter().filter(|&x| color_distance(c, x) < edge_tolerance).count()
        })
        .copied()
        .unwrap_or(Rgba([255, 255, 255, 255]));

    // Flood fill from edges
    let mut visited = vec![vec![false; width as usize]; height as usize];
    let mut queue = VecDeque::new();

    // Add all edge pixels that match background color
    for x in 0..width {
        for y in &[0, height - 1] {
            if color_distance(&bg_color, img.get_pixel(x, *y)) < tolerance {
                queue.push_back((x, *y));
            }
        }
    }
    for y in 0..height {
        for x in &[0, width - 1] {
            if color_distance(&bg_color, img.get_pixel(*x, y)) < tolerance {
                queue.push_back((*x, y));
            }
        }
    }

    // Flood fill
    while let Some((x, y)) = queue.pop_front() {
        if visited[y as usize][x as usize] {
            continue;
        }

        visited[y as usize][x as usize] = true;

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

        // Add neighbors
        let neighbors = [(0, -1), (0, 1), (-1, 0), (1, 0)];
        for (dx, dy) in neighbors {
            let nx = x as i32 + dx;
            let ny = y as i32 + dy;

            if nx >= 0 && nx < width as i32 && ny >= 0 && ny < height as i32 {
                let nx = nx as u32;
                let ny = ny as u32;

                if !visited[ny as usize][nx as usize] {
                    let npixel = img.get_pixel(nx, ny);
                    if color_distance(&bg_color, &npixel) < tolerance {
                        queue.push_back((nx, ny));
                    }
                }
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

/// Find optimal scale factor
fn find_optimal_scale(img: &RgbaImage, min_scale: f32, max_scale: f32) -> f32 {
    let mut best_scale = min_scale;
    let mut best_score = grid_alignment_score(img, best_scale);

    for scale_int in (min_scale.ceil() as u32)..=(max_scale.floor() as u32) {
        let scale = scale_int as f32;
        let score = grid_alignment_score(img, scale);

        if score < best_score {
            best_score = score;
            best_scale = scale;
        }
    }

    best_scale
}

/// Fine-tune scale with fractional values
fn fine_tune_scale(img: &RgbaImage, base_scale: f32) -> f32 {
    let mut best_scale = base_scale;
    let mut best_score = grid_alignment_score(img, best_scale);

    // Test fractional scales around base with higher precision
    // First pass: coarse search ±1.0 with 0.1 steps
    for offset in -10..=10 {
        let scale = base_scale + (offset as f32 * 0.1);
        if scale < 1.0 {
            continue;
        }

        let score = grid_alignment_score(img, scale);
        if score < best_score {
            best_score = score;
            best_scale = scale;
        }
    }

    // Second pass: fine search ±0.2 around best with 0.02 steps
    let coarse_best = best_scale;
    for offset in -10..=10 {
        let scale = coarse_best + (offset as f32 * 0.02);
        if scale < 1.0 {
            continue;
        }

        let score = grid_alignment_score(img, scale);
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

    let scale = if let Some(grid_size) = detected_scale {
        // Find optimal scale in detected range
        let base_scale = find_optimal_scale(&rgba, (grid_size - 2.0).max(2.0), grid_size + 2.0);

        // Fine-tune if enabled
        if settings.enable_fine_tune {
            fine_tune_scale(&rgba, base_scale)
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
