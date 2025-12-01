//! Post-Processing Module for Pixel Art
//!
//! Three main features (matching Python's image_processor.py exactly):
//! 1. Opacity Normalization - Quantize alpha to 0 or 255
//! 2. Color Simplification - LAB color space clustering to merge similar colors
//! 3. Outline Generation - Add outline/border around sprites (grows inward)
//!
//! ## V2 Architecture
//!
//! Each operation is now exposed as a standalone public function that operates
//! on in-memory `RgbaImage` data. This enables:
//! - Selective application (e.g., just outline, no color merge)
//! - Iterative processing (apply operations multiple times)
//! - Live preview generation without file I/O
//!
//! The original `process_image` function remains for backward compatibility.

use image::{RgbaImage, Rgba};
use serde::{Deserialize, Serialize};
use std::collections::{HashMap, HashSet};
use std::path::PathBuf;
use crate::error::{Result, PixelsError};

// ============================================================================
// SETTINGS
// ============================================================================

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProcessorSettings {
    /// Alpha threshold below which pixels become fully transparent (default: 200)
    pub alpha_low_cutoff: u8,
    /// Lower bound of range for making pixels fully opaque (default: 200)
    pub alpha_high_min: u8,
    /// Upper bound of range for making pixels fully opaque (default: 255)
    pub alpha_high_max: u8,
    /// Enable color simplification via LAB clustering (default: true)
    pub enable_color_simplify: bool,
    /// Delta E76 threshold for color clustering - lower = more aggressive merging (default: 3.0)
    pub lab_merge_threshold: f32,
    /// Enable outline generation (default: true)
    pub enable_outline: bool,
    /// Outline color as RGBA tuple (default: (17, 6, 2, 255) - dark brown)
    pub outline_color: (u8, u8, u8, u8),
    /// Alpha threshold for edge detection - pixels <= this are transparent (default: 0)
    pub edge_transparent_cutoff: u8,
    /// Neighbor connectivity: "four" or "eight" (default: four)
    pub outline_connectivity: Connectivity,
    /// Outline thickness in pixels to grow inward (default: 1)
    pub outline_thickness: u32,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum Connectivity {
    Four,
    Eight,
}

// ============================================================================
// INDIVIDUAL OPERATION SETTINGS (V2)
// ============================================================================

/// Settings for alpha/opacity normalization
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AlphaSettings {
    /// Alpha threshold below which pixels become fully transparent (default: 200)
    pub low_cutoff: u8,
    /// Lower bound of range for making pixels fully opaque (default: 200)
    pub high_min: u8,
    /// Upper bound of range for making pixels fully opaque (default: 255)
    pub high_max: u8,
}

impl Default for AlphaSettings {
    fn default() -> Self {
        Self {
            low_cutoff: 200,
            high_min: 200,
            high_max: 255,
        }
    }
}

/// Settings for LAB color space merging
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MergeSettings {
    /// Delta E76 threshold for color clustering - lower = more aggressive merging (default: 3.0)
    pub threshold: f32,
}

impl Default for MergeSettings {
    fn default() -> Self {
        Self { threshold: 3.0 }
    }
}

/// Settings for outline generation
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OutlineSettings {
    /// Outline color as RGBA tuple (default: (17, 6, 2, 255) - dark brown)
    pub color: (u8, u8, u8, u8),
    /// Neighbor connectivity: "four" or "eight" (default: four)
    pub connectivity: Connectivity,
    /// Outline thickness in pixels to grow inward (default: 1)
    pub thickness: u32,
    /// Alpha threshold for edge detection - pixels <= this are transparent (default: 0)
    pub edge_transparent_cutoff: u8,
}

impl Default for OutlineSettings {
    fn default() -> Self {
        Self {
            color: (17, 6, 2, 255),
            connectivity: Connectivity::Four,
            thickness: 1,
            edge_transparent_cutoff: 0,
        }
    }
}

/// Result from color merge operation
#[derive(Debug, Clone, Serialize)]
pub struct MergeResult {
    pub unique_colors_before: usize,
    pub unique_colors_after: usize,
    pub clusters_created: usize,
}

/// Result from outline detection
#[derive(Debug, Clone, Serialize)]
pub struct OutlineDetectionResult {
    /// Whether an existing outline was detected
    pub has_outline: bool,
    /// The detected outline color (if any)
    pub outline_color: Option<(u8, u8, u8, u8)>,
    /// Confidence score (0.0 - 1.0) - percentage of edge pixels matching detected color
    pub confidence: f32,
    /// Number of edge pixels analyzed
    pub edge_pixel_count: usize,
}

impl Default for ProcessorSettings {
    fn default() -> Self {
        Self {
            // Python defaults from settings_manager.py
            alpha_low_cutoff: 200,
            alpha_high_min: 200,
            alpha_high_max: 255,
            enable_color_simplify: true,
            lab_merge_threshold: 3.0,
            enable_outline: true,
            outline_color: (17, 6, 2, 255), // Dark brown
            edge_transparent_cutoff: 0,
            outline_connectivity: Connectivity::Four,
            outline_thickness: 1,
        }
    }
}

#[derive(Debug, Clone, Serialize)]
pub struct ProcessorResult {
    pub original_size: (u32, u32),
    pub unique_colors_before: usize,
    pub unique_colors_after: usize,
    pub clusters_created: usize,
}

// ============================================================================
// COLOR SPACE CONVERSIONS (sRGB <-> XYZ <-> LAB)
// Exact match to Python's rgb_to_lab() and lab_to_rgb()
// ============================================================================

/// Convert sRGB (0-255) to LAB color space
fn rgb_to_lab(r: u8, g: u8, b: u8) -> (f32, f32, f32) {
    // Step 1: sRGB to Linear RGB (gamma correction)
    fn srgb_to_linear(c: u8) -> f32 {
        let c = c as f32 / 255.0;
        if c <= 0.04045 {
            c / 12.92
        } else {
            ((c + 0.055) / 1.055).powf(2.4)
        }
    }

    let rl = srgb_to_linear(r);
    let gl = srgb_to_linear(g);
    let bl = srgb_to_linear(b);

    // Step 2: Linear RGB to XYZ (standard matrix)
    let x = rl * 0.4124564 + gl * 0.3575761 + bl * 0.1804375;
    let y = rl * 0.2126729 + gl * 0.7151522 + bl * 0.0721750;
    let z = rl * 0.0193339 + gl * 0.1191920 + bl * 0.9503041;

    // Step 3: XYZ to LAB (D65 illuminant)
    const XN: f32 = 0.95047;
    const YN: f32 = 1.00000;
    const ZN: f32 = 1.08883;

    let xr = x / XN;
    let yr = y / YN;
    let zr = z / ZN;

    fn f(t: f32) -> f32 {
        if t > 0.008856 {
            t.powf(1.0 / 3.0)
        } else {
            7.787 * t + 16.0 / 116.0
        }
    }

    let fx = f(xr);
    let fy = f(yr);
    let fz = f(zr);

    let l = (116.0 * fy - 16.0).max(0.0);
    let a = 500.0 * (fx - fy);
    let lab_b = 200.0 * (fy - fz);

    (l, a, lab_b)
}

/// Convert LAB color space back to sRGB (0-255)
fn lab_to_rgb(l: f32, a: f32, b: f32) -> (u8, u8, u8) {
    // Step 1: LAB to XYZ
    const XN: f32 = 0.95047;
    const YN: f32 = 1.00000;
    const ZN: f32 = 1.08883;

    let fy = (l + 16.0) / 116.0;
    let fx = a / 500.0 + fy;
    let fz = fy - b / 200.0;

    fn f_inv(t: f32) -> f32 {
        let t3 = t * t * t;
        if t3 > 0.008856 {
            t3
        } else {
            (t - 16.0 / 116.0) / 7.787
        }
    }

    let xr = f_inv(fx);
    let yr = f_inv(fy);
    let zr = f_inv(fz);

    let x = xr * XN;
    let y = yr * YN;
    let z = zr * ZN;

    // Step 2: XYZ to Linear RGB (inverse matrix)
    let rl = x *  3.2404542 + y * -1.5371385 + z * -0.4985314;
    let gl = x * -0.9692660 + y *  1.8760108 + z *  0.0415560;
    let bl = x *  0.0556434 + y * -0.2040259 + z *  1.0572252;

    // Step 3: Linear RGB to sRGB (inverse gamma)
    fn linear_to_srgb(c: f32) -> u8 {
        let c = c.clamp(0.0, 1.0);
        let v = if c <= 0.0031308 {
            12.92 * c
        } else {
            1.055 * c.powf(1.0 / 2.4) - 0.055
        };
        (v * 255.0).round().clamp(0.0, 255.0) as u8
    }

    (linear_to_srgb(rl), linear_to_srgb(gl), linear_to_srgb(bl))
}

/// Calculate Delta E76 color difference in LAB space
fn delta_e76(lab1: (f32, f32, f32), lab2: (f32, f32, f32)) -> f32 {
    let dl = lab1.0 - lab2.0;
    let da = lab1.1 - lab2.1;
    let db = lab1.2 - lab2.2;
    (dl * dl + da * da + db * db).sqrt()
}

// ============================================================================
// STEP 1: OPACITY NORMALIZATION
// Exact match to Python lines 77-89
// ============================================================================

/// Internal function using legacy ProcessorSettings
fn normalize_opacity_internal(img: &mut RgbaImage, settings: &ProcessorSettings) {
    let (width, height) = img.dimensions();

    for y in 0..height {
        for x in 0..width {
            let pixel = img.get_pixel_mut(x, y);
            let alpha = pixel[3];

            if alpha < settings.alpha_low_cutoff {
                pixel[3] = 0;
            } else if alpha >= settings.alpha_high_min && alpha <= settings.alpha_high_max {
                pixel[3] = 255;
            }
        }
    }
}

/// Normalize alpha channel to binary (0 or 255)
///
/// This operation quantizes semi-transparent pixels:
/// - Alpha < low_cutoff → 0 (fully transparent)
/// - Alpha >= high_min and <= high_max → 255 (fully opaque)
///
/// Safe to re-apply: idempotent operation (no change on second application)
pub fn normalize_alpha(img: &mut RgbaImage, settings: &AlphaSettings) {
    let (width, height) = img.dimensions();

    for y in 0..height {
        for x in 0..width {
            let pixel = img.get_pixel_mut(x, y);
            let alpha = pixel[3];

            if alpha < settings.low_cutoff {
                pixel[3] = 0;
            } else if alpha >= settings.high_min && alpha <= settings.high_max {
                pixel[3] = 255;
            }
        }
    }
}

// ============================================================================
// STEP 2: COLOR SIMPLIFICATION (LAB Clustering)
// Exact match to Python lines 91-149
// Key: greedy first-fit assignment, sorted by frequency, track members
// ============================================================================

struct LabCluster {
    center_lab: (f32, f32, f32),
    sum_l: f32,
    sum_a: f32,
    sum_b: f32,
    count: u32,
    members: Vec<((u8, u8, u8), u32)>,
}

impl LabCluster {
    fn new(rgb: (u8, u8, u8), lab: (f32, f32, f32), count: u32) -> Self {
        Self {
            center_lab: lab,
            sum_l: lab.0 * count as f32,
            sum_a: lab.1 * count as f32,
            sum_b: lab.2 * count as f32,
            count,
            members: vec![(rgb, count)],
        }
    }

    fn add(&mut self, rgb: (u8, u8, u8), lab: (f32, f32, f32), count: u32) {
        self.members.push((rgb, count));
        self.sum_l += lab.0 * count as f32;
        self.sum_a += lab.1 * count as f32;
        self.sum_b += lab.2 * count as f32;
        self.count += count;
        // Update center (weighted average) - Python lines 116-120
        self.center_lab = (
            self.sum_l / self.count as f32,
            self.sum_a / self.count as f32,
            self.sum_b / self.count as f32,
        );
    }
}

/// Internal color simplification (returns tuple for legacy API)
fn simplify_colors_internal(img: &mut RgbaImage, threshold: f32) -> (usize, usize, usize) {
    let result = merge_colors_impl(img, threshold);
    (result.unique_colors_before, result.unique_colors_after, result.clusters_created)
}

/// Core implementation of LAB color clustering
fn merge_colors_impl(img: &mut RgbaImage, threshold: f32) -> MergeResult {
    let (width, height) = img.dimensions();

    // Collect unique colors with counts (Python lines 96-102)
    let mut color_counts: HashMap<(u8, u8, u8), u32> = HashMap::new();
    for y in 0..height {
        for x in 0..width {
            let pixel = img.get_pixel(x, y);
            if pixel[3] >= 1 {
                let key = (pixel[0], pixel[1], pixel[2]);
                *color_counts.entry(key).or_insert(0) += 1;
            }
        }
    }

    let unique_before = color_counts.len();
    if color_counts.is_empty() {
        return MergeResult {
            unique_colors_before: 0,
            unique_colors_after: 0,
            clusters_created: 0,
        };
    }

    // Sort by frequency descending (Python line 107)
    let mut items: Vec<_> = color_counts.into_iter().collect();
    items.sort_by(|a, b| b.1.cmp(&a.1));

    // Build LAB clusters using greedy assignment (Python lines 109-132)
    let mut clusters: Vec<LabCluster> = Vec::new();

    for ((r, g, b), count) in items {
        let lab = rgb_to_lab(r, g, b);
        let mut assigned = false;

        for cluster in &mut clusters {
            if delta_e76(lab, cluster.center_lab) <= threshold {
                cluster.add((r, g, b), lab, count);
                assigned = true;
                break;
            }
        }

        if !assigned {
            clusters.push(LabCluster::new((r, g, b), lab, count));
        }
    }

    let clusters_created = clusters.len();

    // Build color mapping (Python lines 135-139)
    let mut colormap: HashMap<(u8, u8, u8), (u8, u8, u8)> = HashMap::new();
    for cluster in &clusters {
        let rep = lab_to_rgb(cluster.center_lab.0, cluster.center_lab.1, cluster.center_lab.2);
        for &(rgb, _) in &cluster.members {
            colormap.insert(rgb, rep);
        }
    }

    let unique_after = colormap.values().collect::<HashSet<_>>().len();

    // Apply color mapping (Python lines 142-149)
    for y in 0..height {
        for x in 0..width {
            let pixel = img.get_pixel_mut(x, y);
            if pixel[3] >= 1 {
                let key = (pixel[0], pixel[1], pixel[2]);
                if let Some(&(r, g, b)) = colormap.get(&key) {
                    pixel[0] = r;
                    pixel[1] = g;
                    pixel[2] = b;
                }
            }
        }
    }

    MergeResult {
        unique_colors_before: unique_before,
        unique_colors_after: unique_after,
        clusters_created,
    }
}

/// Merge similar colors using LAB color space clustering
///
/// Uses greedy first-fit assignment with Delta E76 distance metric.
/// Colors within `threshold` distance are merged to their weighted average.
///
/// Safe to re-apply: progressive simplification (may reduce colors further each time)
pub fn merge_colors(img: &mut RgbaImage, settings: &MergeSettings) -> MergeResult {
    merge_colors_impl(img, settings.threshold)
}

// ============================================================================
// STEP 3: OUTLINE GENERATION
// Exact match to Python lines 151-202 (frontier queue, grows inward)
// ============================================================================

fn get_neighbors(x: u32, y: u32, width: u32, height: u32, connectivity: &Connectivity) -> Vec<(u32, u32)> {
    let mut neighbors = Vec::new();

    match connectivity {
        Connectivity::Four => {
            // Python lines 165-169
            if x > 0 { neighbors.push((x - 1, y)); }
            if x < width - 1 { neighbors.push((x + 1, y)); }
            if y > 0 { neighbors.push((x, y - 1)); }
            if y < height - 1 { neighbors.push((x, y + 1)); }
        }
        Connectivity::Eight => {
            // Python lines 170-174
            for nx in x.saturating_sub(1)..=(x + 1).min(width - 1) {
                for ny in y.saturating_sub(1)..=(y + 1).min(height - 1) {
                    if !(nx == x && ny == y) {
                        neighbors.push((nx, ny));
                    }
                }
            }
        }
    }

    neighbors
}

/// Internal function using legacy ProcessorSettings
fn generate_outline_internal(img: &mut RgbaImage, settings: &ProcessorSettings) {
    let outline_settings = OutlineSettings {
        color: settings.outline_color,
        connectivity: settings.outline_connectivity.clone(),
        thickness: settings.outline_thickness,
        edge_transparent_cutoff: settings.edge_transparent_cutoff,
    };
    add_outline(img, &outline_settings);
}

/// Add outline/border around sprite (grows inward from edges)
///
/// Uses frontier queue algorithm:
/// 1. Find all border pixels (opaque pixels adjacent to transparent)
/// 2. Grow inward for `thickness` iterations
/// 3. Apply outline color to all pixels in the mask
///
/// **Warning**: Applying outline to an already-outlined image creates double-outline artifacts.
/// Use `detect_outline()` first to check if image already has an outline.
pub fn add_outline(img: &mut RgbaImage, settings: &OutlineSettings) {
    let (width, height) = img.dimensions();
    let edge_cutoff = settings.edge_transparent_cutoff;
    let connectivity = &settings.connectivity;
    let thickness = settings.thickness;

    if thickness == 0 {
        return;
    }

    // Extract alpha channel (Python line 158)
    let alpha: Vec<Vec<u8>> = (0..height)
        .map(|y| (0..width).map(|x| img.get_pixel(x, y)[3]).collect())
        .collect();

    // Build outline mask (Python line 161)
    let mut mask: Vec<Vec<bool>> = vec![vec![false; width as usize]; height as usize];

    // Find border pixels (Python lines 177-186)
    let mut frontier: Vec<(u32, u32)> = Vec::new();

    for y in 0..height {
        for x in 0..width {
            if alpha[y as usize][x as usize] > edge_cutoff {
                let is_border = get_neighbors(x, y, width, height, connectivity)
                    .iter()
                    .any(|&(nx, ny)| alpha[ny as usize][nx as usize] <= edge_cutoff);

                if is_border {
                    mask[y as usize][x as usize] = true;
                    frontier.push((x, y));
                }
            }
        }
    }

    // Grow inward for thickness (Python lines 189-196)
    for _ in 1..thickness {
        let mut new_frontier: Vec<(u32, u32)> = Vec::new();

        for &(x, y) in &frontier {
            for (nx, ny) in get_neighbors(x, y, width, height, connectivity) {
                if alpha[ny as usize][nx as usize] > edge_cutoff
                    && !mask[ny as usize][nx as usize]
                {
                    mask[ny as usize][nx as usize] = true;
                    new_frontier.push((nx, ny));
                }
            }
        }

        frontier = new_frontier;
    }

    // Apply outline color (Python lines 199-202)
    let outline_rgba = Rgba([
        settings.color.0,
        settings.color.1,
        settings.color.2,
        settings.color.3,
    ]);

    for y in 0..height {
        for x in 0..width {
            if mask[y as usize][x as usize] {
                img.put_pixel(x, y, outline_rgba);
            }
        }
    }
}

// ============================================================================
// OUTLINE DETECTION (V2)
// ============================================================================

/// Detect if an image already has an outline
///
/// Scans edge pixels (opaque pixels adjacent to transparent) and checks
/// if they form a uniform or near-uniform color pattern, which indicates
/// an existing outline.
///
/// Returns detection result with confidence score. Use this before `add_outline`
/// to warn users about potential double-outline artifacts.
pub fn detect_outline(img: &RgbaImage) -> OutlineDetectionResult {
    let (width, height) = img.dimensions();

    if width == 0 || height == 0 {
        return OutlineDetectionResult {
            has_outline: false,
            outline_color: None,
            confidence: 0.0,
            edge_pixel_count: 0,
        };
    }

    // Collect edge pixels (opaque pixels adjacent to transparent)
    let mut edge_colors: Vec<(u8, u8, u8, u8)> = Vec::new();

    for y in 0..height {
        for x in 0..width {
            let pixel = img.get_pixel(x, y);

            // Only consider opaque pixels
            if pixel[3] > 0 {
                // Check if adjacent to any transparent pixel (4-connectivity)
                let is_edge = [
                    (x.wrapping_sub(1), y),
                    (x + 1, y),
                    (x, y.wrapping_sub(1)),
                    (x, y + 1),
                ]
                .iter()
                .any(|&(nx, ny)| {
                    if nx < width && ny < height {
                        img.get_pixel(nx, ny)[3] == 0
                    } else {
                        true // Image boundary counts as transparent
                    }
                });

                if is_edge {
                    edge_colors.push((pixel[0], pixel[1], pixel[2], pixel[3]));
                }
            }
        }
    }

    let edge_count = edge_colors.len();

    if edge_count == 0 {
        return OutlineDetectionResult {
            has_outline: false,
            outline_color: None,
            confidence: 0.0,
            edge_pixel_count: 0,
        };
    }

    // Count color occurrences
    let mut color_counts: HashMap<(u8, u8, u8, u8), usize> = HashMap::new();
    for color in &edge_colors {
        *color_counts.entry(*color).or_insert(0) += 1;
    }

    // Find most common edge color
    let (most_common_color, most_common_count) = color_counts
        .iter()
        .max_by_key(|(_, count)| *count)
        .map(|(color, count)| (*color, *count))
        .unwrap();

    // Calculate confidence: what percentage of edge pixels match the most common color?
    let confidence = most_common_count as f32 / edge_count as f32;

    // Also count colors within small Delta E distance (allow slight variations)
    let most_common_lab = rgb_to_lab(most_common_color.0, most_common_color.1, most_common_color.2);
    let similar_count: usize = edge_colors
        .iter()
        .filter(|c| {
            let lab = rgb_to_lab(c.0, c.1, c.2);
            delta_e76(lab, most_common_lab) <= 5.0 // Tight threshold for "same" color
        })
        .count();

    let similar_confidence = similar_count as f32 / edge_count as f32;
    let final_confidence = similar_confidence.max(confidence);

    // Consider it an outline if >80% of edge pixels are the same/similar color
    let has_outline = final_confidence >= 0.80;

    OutlineDetectionResult {
        has_outline,
        outline_color: if has_outline { Some(most_common_color) } else { None },
        confidence: final_confidence,
        edge_pixel_count: edge_count,
    }
}

// ============================================================================
// MAIN ENTRY POINT
// ============================================================================

/// Legacy entry point - processes image file with all operations
///
/// This function is retained for backward compatibility with existing v1 UI.
/// For v2, use the individual operations: `normalize_alpha`, `merge_colors`, `add_outline`
pub fn process_image(
    input_path: PathBuf,
    output_path: PathBuf,
    settings: ProcessorSettings,
) -> Result<ProcessorResult> {
    // Load image
    let img = image::open(&input_path)
        .map_err(|e| PixelsError::Processing(format!("Failed to load {}: {}", input_path.display(), e)))?;

    let mut rgba = img.to_rgba8();
    let original_size = rgba.dimensions();

    // Step 1: Opacity normalization (always runs)
    normalize_opacity_internal(&mut rgba, &settings);

    // Step 2: Color simplification (if enabled)
    let (colors_before, colors_after, clusters) = if settings.enable_color_simplify {
        simplify_colors_internal(&mut rgba, settings.lab_merge_threshold)
    } else {
        (0, 0, 0)
    };

    // Step 3: Outline generation (if enabled and thickness > 0)
    if settings.enable_outline && settings.outline_thickness > 0 {
        generate_outline_internal(&mut rgba, &settings);
    }

    // Ensure output directory exists
    if let Some(parent) = output_path.parent() {
        std::fs::create_dir_all(parent)?;
    }

    // Save result
    rgba.save(&output_path)?;

    Ok(ProcessorResult {
        original_size,
        unique_colors_before: colors_before,
        unique_colors_after: colors_after,
        clusters_created: clusters,
    })
}

// ============================================================================
// V2 IN-MEMORY PROCESSING
// ============================================================================

/// Load an image from disk into memory
pub fn load_image(path: &PathBuf) -> Result<RgbaImage> {
    let img = image::open(path)
        .map_err(|e| PixelsError::Processing(format!("Failed to load {}: {}", path.display(), e)))?;
    Ok(img.to_rgba8())
}

/// Save an in-memory image to disk
pub fn save_image(img: &RgbaImage, path: &PathBuf) -> Result<()> {
    // Ensure output directory exists
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent)?;
    }
    img.save(path)?;
    Ok(())
}

/// Encode image as PNG bytes (for preview/transfer without file I/O)
pub fn encode_png(img: &RgbaImage) -> Result<Vec<u8>> {
    use std::io::Cursor;
    let mut buffer = Cursor::new(Vec::new());
    img.write_to(&mut buffer, image::ImageFormat::Png)
        .map_err(|e| PixelsError::Processing(format!("Failed to encode PNG: {}", e)))?;
    Ok(buffer.into_inner())
}

// ============================================================================
// TESTS
// ============================================================================

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_rgb_lab_roundtrip() {
        let test_colors = [
            (255, 0, 0), (0, 255, 0), (0, 0, 255),
            (255, 255, 255), (0, 0, 0), (128, 128, 128),
            (17, 6, 2), // Default outline color
        ];

        for (r, g, b) in test_colors {
            let lab = rgb_to_lab(r, g, b);
            let (r2, g2, b2) = lab_to_rgb(lab.0, lab.1, lab.2);
            assert!((r as i16 - r2 as i16).abs() <= 1, "Red mismatch for ({}, {}, {})", r, g, b);
            assert!((g as i16 - g2 as i16).abs() <= 1, "Green mismatch for ({}, {}, {})", r, g, b);
            assert!((b as i16 - b2 as i16).abs() <= 1, "Blue mismatch for ({}, {}, {})", r, g, b);
        }
    }

    #[test]
    fn test_delta_e76_same_color() {
        let lab = rgb_to_lab(100, 100, 100);
        assert!(delta_e76(lab, lab) < 0.001);
    }

    #[test]
    fn test_neighbors_4way() {
        let neighbors = get_neighbors(5, 5, 10, 10, &Connectivity::Four);
        assert_eq!(neighbors.len(), 4);
    }

    #[test]
    fn test_neighbors_8way() {
        let neighbors = get_neighbors(5, 5, 10, 10, &Connectivity::Eight);
        assert_eq!(neighbors.len(), 8);
    }

    #[test]
    fn test_neighbors_corner() {
        let n4 = get_neighbors(0, 0, 10, 10, &Connectivity::Four);
        assert_eq!(n4.len(), 2);
        let n8 = get_neighbors(0, 0, 10, 10, &Connectivity::Eight);
        assert_eq!(n8.len(), 3);
    }
}
