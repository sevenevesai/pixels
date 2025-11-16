use image::{RgbaImage, Rgba, ImageBuffer};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::path::PathBuf;
use crate::error::{Result, PixelsError};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProcessorSettings {
    // Opacity normalization
    pub alpha_low_cutoff: u8,
    pub alpha_high_min: u8,
    pub alpha_high_max: u8,

    // Color simplification
    pub enable_color_simplify: bool,
    pub lab_merge_threshold: f32,

    // Outline generation
    pub enable_outline: bool,
    pub outline_color: (u8, u8, u8, u8),
    pub edge_transparent_cutoff: u8,
    pub outline_connectivity: Connectivity,
    pub outline_thickness: u32,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum Connectivity {
    Four,
    Eight,
}

impl Default for ProcessorSettings {
    fn default() -> Self {
        Self {
            alpha_low_cutoff: 30,
            alpha_high_min: 200,
            alpha_high_max: 255,
            enable_color_simplify: true,
            lab_merge_threshold: 10.0,
            enable_outline: false,
            outline_color: (0, 0, 0, 255),
            edge_transparent_cutoff: 128,
            outline_connectivity: Connectivity::Four,
            outline_thickness: 1,
        }
    }
}

/// RGB to LAB color space conversion
fn rgb_to_lab(r: u8, g: u8, b: u8) -> (f32, f32, f32) {
    // Convert to 0-1 range
    let mut r = r as f32 / 255.0;
    let mut g = g as f32 / 255.0;
    let mut b = b as f32 / 255.0;

    // Apply sRGB gamma correction
    r = if r > 0.04045 {
        ((r + 0.055) / 1.055).powf(2.4)
    } else {
        r / 12.92
    };
    g = if g > 0.04045 {
        ((g + 0.055) / 1.055).powf(2.4)
    } else {
        g / 12.92
    };
    b = if b > 0.04045 {
        ((b + 0.055) / 1.055).powf(2.4)
    } else {
        b / 12.92
    };

    // Convert to XYZ using D65 illuminant
    let x = r * 0.4124564 + g * 0.3575761 + b * 0.1804375;
    let y = r * 0.2126729 + g * 0.7151522 + b * 0.0721750;
    let z = r * 0.0193339 + g * 0.1191920 + b * 0.9503041;

    // Normalize by D65 white point
    let x = x / 0.95047;
    let y = y / 1.00000;
    let z = z / 1.08883;

    // Apply LAB transformation
    let fx = if x > 0.008856 {
        x.powf(1.0 / 3.0)
    } else {
        (7.787 * x) + (16.0 / 116.0)
    };
    let fy = if y > 0.008856 {
        y.powf(1.0 / 3.0)
    } else {
        (7.787 * y) + (16.0 / 116.0)
    };
    let fz = if z > 0.008856 {
        z.powf(1.0 / 3.0)
    } else {
        (7.787 * z) + (16.0 / 116.0)
    };

    let l = (116.0 * fy) - 16.0;
    let a = 500.0 * (fx - fy);
    let b = 200.0 * (fy - fz);

    (l, a, b)
}

/// LAB to RGB color space conversion
fn lab_to_rgb(l: f32, a: f32, b: f32) -> (u8, u8, u8) {
    // Convert LAB to XYZ
    let fy = (l + 16.0) / 116.0;
    let fx = a / 500.0 + fy;
    let fz = fy - b / 200.0;

    let xr = if fx.powi(3) > 0.008856 {
        fx.powi(3)
    } else {
        (fx - 16.0 / 116.0) / 7.787
    };
    let yr = if fy.powi(3) > 0.008856 {
        fy.powi(3)
    } else {
        (fy - 16.0 / 116.0) / 7.787
    };
    let zr = if fz.powi(3) > 0.008856 {
        fz.powi(3)
    } else {
        (fz - 16.0 / 116.0) / 7.787
    };

    // Denormalize by D65 white point
    let x = xr * 0.95047;
    let y = yr * 1.00000;
    let z = zr * 1.08883;

    // Convert XYZ to linear RGB
    let mut r = x * 3.2404542 + y * -1.5371385 + z * -0.4985314;
    let mut g = x * -0.9692660 + y * 1.8760108 + z * 0.0415560;
    let mut b = x * 0.0556434 + y * -0.2040259 + z * 1.0572252;

    // Apply sRGB gamma correction
    r = if r > 0.0031308 {
        1.055 * r.powf(1.0 / 2.4) - 0.055
    } else {
        12.92 * r
    };
    g = if g > 0.0031308 {
        1.055 * g.powf(1.0 / 2.4) - 0.055
    } else {
        12.92 * g
    };
    b = if b > 0.0031308 {
        1.055 * b.powf(1.0 / 2.4) - 0.055
    } else {
        12.92 * b
    };

    // Clamp and convert to u8
    let r = (r * 255.0).clamp(0.0, 255.0) as u8;
    let g = (g * 255.0).clamp(0.0, 255.0) as u8;
    let b = (b * 255.0).clamp(0.0, 255.0) as u8;

    (r, g, b)
}

/// Calculate Delta E76 color distance in LAB space
fn delta_e76(lab1: (f32, f32, f32), lab2: (f32, f32, f32)) -> f32 {
    let dl = lab1.0 - lab2.0;
    let da = lab1.1 - lab2.1;
    let db = lab1.2 - lab2.2;
    (dl * dl + da * da + db * db).sqrt()
}

/// Normalize opacity values
fn normalize_opacity(img: &mut RgbaImage, settings: &ProcessorSettings) {
    for pixel in img.pixels_mut() {
        let alpha = pixel[3];

        // Low cutoff: set to transparent
        if alpha < settings.alpha_low_cutoff {
            pixel[3] = 0;
        }
        // High range: set to opaque
        else if alpha >= settings.alpha_high_min && alpha <= settings.alpha_high_max {
            pixel[3] = 255;
        }
    }
}

/// Simplify colors using LAB clustering
fn simplify_colors(img: &mut RgbaImage, threshold: f32) {
    let (width, height) = img.dimensions();

    // Count unique colors and their frequencies
    let mut color_counts: HashMap<(u8, u8, u8), u32> = HashMap::new();
    for y in 0..height {
        for x in 0..width {
            let pixel = img.get_pixel(x, y);
            if pixel[3] > 0 {
                // Only process non-transparent pixels
                let rgb = (pixel[0], pixel[1], pixel[2]);
                *color_counts.entry(rgb).or_insert(0) += 1;
            }
        }
    }

    // Sort colors by frequency (most common first)
    let mut colors: Vec<_> = color_counts.into_iter().collect();
    colors.sort_by(|a, b| b.1.cmp(&a.1));

    // Build color clusters
    #[derive(Clone)]
    struct Cluster {
        lab: (f32, f32, f32),
        weight: f32,
    }

    let mut clusters: Vec<Cluster> = Vec::new();

    for (rgb, count) in colors {
        let lab = rgb_to_lab(rgb.0, rgb.1, rgb.2);
        let weight = count as f32;

        // Find nearest cluster
        let mut merged = false;
        for cluster in &mut clusters {
            if delta_e76(lab, cluster.lab) <= threshold {
                // Merge into this cluster (weighted average)
                let total_weight = cluster.weight + weight;
                cluster.lab.0 = (cluster.lab.0 * cluster.weight + lab.0 * weight) / total_weight;
                cluster.lab.1 = (cluster.lab.1 * cluster.weight + lab.1 * weight) / total_weight;
                cluster.lab.2 = (cluster.lab.2 * cluster.weight + lab.2 * weight) / total_weight;
                cluster.weight = total_weight;
                merged = true;
                break;
            }
        }

        // Create new cluster if not merged
        if !merged {
            clusters.push(Cluster { lab, weight });
        }
    }

    // Build color mapping
    let mut color_map: HashMap<(u8, u8, u8), (u8, u8, u8)> = HashMap::new();

    for (rgb, _) in img.pixels().map(|p| ((p[0], p[1], p[2]), p[3])).filter(|(_, a)| *a > 0) {
        if color_map.contains_key(&rgb) {
            continue;
        }

        let lab = rgb_to_lab(rgb.0, rgb.1, rgb.2);

        // Find nearest cluster
        let mut nearest_cluster = &clusters[0];
        let mut min_distance = delta_e76(lab, nearest_cluster.lab);

        for cluster in &clusters[1..] {
            let distance = delta_e76(lab, cluster.lab);
            if distance < min_distance {
                min_distance = distance;
                nearest_cluster = cluster;
            }
        }

        // Convert cluster LAB back to RGB
        let new_rgb = lab_to_rgb(nearest_cluster.lab.0, nearest_cluster.lab.1, nearest_cluster.lab.2);
        color_map.insert(rgb, new_rgb);
    }

    // Apply color mapping to image
    for pixel in img.pixels_mut() {
        if pixel[3] > 0 {
            let rgb = (pixel[0], pixel[1], pixel[2]);
            if let Some(&new_rgb) = color_map.get(&rgb) {
                pixel[0] = new_rgb.0;
                pixel[1] = new_rgb.1;
                pixel[2] = new_rgb.2;
            }
        }
    }
}

/// Generate outlines around sprites
fn generate_outline(img: &mut RgbaImage, settings: &ProcessorSettings) {
    let (width, height) = img.dimensions();
    let mut outline_mask = ImageBuffer::from_pixel(width, height, Rgba([0u8, 0, 0, 0]));

    // Find edge pixels
    for y in 0..height {
        for x in 0..width {
            let pixel = img.get_pixel(x, y);

            // Skip if already transparent
            if pixel[3] <= settings.edge_transparent_cutoff {
                continue;
            }

            // Check neighbors based on connectivity
            let neighbors = match settings.outline_connectivity {
                Connectivity::Four => vec![
                    (x.wrapping_sub(1), y),
                    (x + 1, y),
                    (x, y.wrapping_sub(1)),
                    (x, y + 1),
                ],
                Connectivity::Eight => vec![
                    (x.wrapping_sub(1), y),
                    (x + 1, y),
                    (x, y.wrapping_sub(1)),
                    (x, y + 1),
                    (x.wrapping_sub(1), y.wrapping_sub(1)),
                    (x + 1, y.wrapping_sub(1)),
                    (x.wrapping_sub(1), y + 1),
                    (x + 1, y + 1),
                ],
            };

            // Check if any neighbor is transparent (edge pixel)
            let is_edge = neighbors.iter().any(|&(nx, ny)| {
                if nx < width && ny < height {
                    img.get_pixel(nx, ny)[3] <= settings.edge_transparent_cutoff
                } else {
                    true // Treat out-of-bounds as transparent
                }
            });

            if is_edge {
                outline_mask.put_pixel(x, y, Rgba([255, 255, 255, 255]));
            }
        }
    }

    // Grow outline inward by thickness
    for _ in 1..settings.outline_thickness {
        let mut new_mask = outline_mask.clone();

        for y in 0..height {
            for x in 0..width {
                if outline_mask.get_pixel(x, y)[0] > 0 {
                    // Already marked, dilate
                    let neighbors = vec![
                        (x.wrapping_sub(1), y),
                        (x + 1, y),
                        (x, y.wrapping_sub(1)),
                        (x, y + 1),
                    ];

                    for (nx, ny) in neighbors {
                        if nx < width && ny < height {
                            let orig_pixel = img.get_pixel(nx, ny);
                            if orig_pixel[3] > settings.edge_transparent_cutoff {
                                new_mask.put_pixel(nx, ny, Rgba([255, 255, 255, 255]));
                            }
                        }
                    }
                }
            }
        }

        outline_mask = new_mask;
    }

    // Apply outline color
    let outline_rgba = Rgba([
        settings.outline_color.0,
        settings.outline_color.1,
        settings.outline_color.2,
        settings.outline_color.3,
    ]);

    for y in 0..height {
        for x in 0..width {
            if outline_mask.get_pixel(x, y)[0] > 0 {
                img.put_pixel(x, y, outline_rgba);
            }
        }
    }
}

/// Process a single image with the given settings
pub fn process_image(
    input_path: PathBuf,
    output_path: PathBuf,
    settings: ProcessorSettings,
) -> Result<()> {
    // Load image
    let img = image::open(&input_path)
        .map_err(|e| PixelsError::Processing(format!("Failed to load {}: {}", input_path.display(), e)))?;

    let mut rgba = img.to_rgba8();

    // Apply processing steps in order

    // 1. Normalize opacity
    normalize_opacity(&mut rgba, &settings);

    // 2. Simplify colors (if enabled)
    if settings.enable_color_simplify {
        simplify_colors(&mut rgba, settings.lab_merge_threshold);
    }

    // 3. Generate outline (if enabled)
    if settings.enable_outline {
        generate_outline(&mut rgba, &settings);
    }

    // Save result
    rgba.save(&output_path)?;

    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_rgb_lab_roundtrip() {
        let (r, g, b) = (128, 64, 200);
        let lab = rgb_to_lab(r, g, b);
        let (r2, g2, b2) = lab_to_rgb(lab.0, lab.1, lab.2);

        // Allow small rounding errors
        assert!((r as i16 - r2 as i16).abs() <= 2);
        assert!((g as i16 - g2 as i16).abs() <= 2);
        assert!((b as i16 - b2 as i16).abs() <= 2);
    }

    #[test]
    fn test_delta_e76() {
        let lab1 = (50.0, 25.0, -10.0);
        let lab2 = (50.0, 25.0, -10.0);
        assert_eq!(delta_e76(lab1, lab2), 0.0);

        let lab3 = (60.0, 25.0, -10.0);
        assert!(delta_e76(lab1, lab3) > 0.0);
    }
}
