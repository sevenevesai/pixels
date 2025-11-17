use image::RgbaImage;
use std::path::PathBuf;

mod downscaler_copy;
use downscaler_copy::{downscale_image, DownscalerSettings, BgRemovalMode};

fn main() {
    let input_path = PathBuf::from("S:/Pixels/snowman-original.png");
    let expected_path = PathBuf::from("S:/Pixels/snowman-downscaled.png");
    let test_output_path = PathBuf::from("S:/Pixels/rust-test-output.png");

    // Load images
    let input_img = image::open(&input_path).expect("Failed to load input").to_rgba8();
    let expected_img = image::open(&expected_path).expect("Failed to load expected").to_rgba8();

    println!("=== Image Analysis ===");
    println!("Input canvas: {:?}", input_img.dimensions());
    println!("Expected canvas: {:?}", expected_img.dimensions());

    // Measure actual pixel content (non-transparent bounds)
    let input_bounds = get_content_bounds(&input_img);
    let expected_bounds = get_content_bounds(&expected_img);

    println!("\nInput content bounds: {:?}", input_bounds);
    println!("Input content size: {}x{}",
        input_bounds.2 - input_bounds.0,
        input_bounds.3 - input_bounds.1);

    println!("\nExpected content bounds: {:?}", expected_bounds);
    println!("Expected content size: {}x{}",
        expected_bounds.2 - expected_bounds.0,
        expected_bounds.3 - expected_bounds.1);

    // Calculate scale factor based on actual content
    let input_width = (input_bounds.2 - input_bounds.0) as f32;
    let input_height = (input_bounds.3 - input_bounds.1) as f32;
    let expected_width = (expected_bounds.2 - expected_bounds.0) as f32;
    let expected_height = (expected_bounds.3 - expected_bounds.1) as f32;

    let scale_x = input_width / expected_width;
    let scale_y = input_height / expected_height;

    println!("\nActual content scale factors:");
    println!("  X: {:.4}", scale_x);
    println!("  Y: {:.4}", scale_y);
    println!("  Average: {:.4}", (scale_x + scale_y) / 2.0);
    println!("  Rounded: {}", ((scale_x + scale_y) / 2.0).round());

    // Count total pixels
    let input_pixels = count_opaque_pixels(&input_img);
    let expected_pixels = count_opaque_pixels(&expected_img);

    println!("\nPixel counts:");
    println!("  Input opaque pixels: {}", input_pixels);
    println!("  Expected opaque pixels: {}", expected_pixels);
    println!("  Pixel ratio: {:.2}", input_pixels as f32 / expected_pixels as f32);

    // Now test current algorithm
    println!("\n\n=== Testing Current Rust Algorithm ===");

    let settings = DownscalerSettings {
        bg_removal_mode: BgRemovalMode::Conservative,
        bg_tolerance: 15,
        bg_edge_tolerance: 30,
        preserve_dark_lines: false,
        dark_line_threshold: 100,
        auto_trim: true,
        enable_fine_tune: true,
        pad_canvas: false,
        canvas_multiple: 16,
    };

    let settings_copy = settings.clone();

    match downscale_image(input_path.clone(), test_output_path.clone(), settings) {
        Ok(result) => {
            println!("Scale detected: {:.4}", result.scale_factor);
            println!("Grid detected: {}", result.grid_detected);
            println!("Output size: {:?}", result.final_size);

            // Load and analyze output
            if let Ok(output_img) = image::open(&test_output_path) {
                let output_img = output_img.to_rgba8();
                let output_bounds = get_content_bounds(&output_img);

                println!("\nRust output content size: {}x{}",
                    output_bounds.2 - output_bounds.0,
                    output_bounds.3 - output_bounds.1);

                let diff_x = (output_bounds.2 - output_bounds.0) as i32 -
                             (expected_bounds.2 - expected_bounds.0) as i32;
                let diff_y = (output_bounds.3 - output_bounds.1) as i32 -
                             (expected_bounds.3 - expected_bounds.1) as i32;

                if diff_x == 0 && diff_y == 0 {
                    println!("✓ PERFECT MATCH!");
                } else {
                    println!("✗ Size difference: ({}, {}) pixels", diff_x, diff_y);
                    println!("  Target was: {}x{}",
                        expected_bounds.2 - expected_bounds.0,
                        expected_bounds.3 - expected_bounds.1);
                }
            }

            // Test what scale would actually be optimal
            println!("\n=== Testing Scale Range ===");
            let test_img_no_bg = {
                let mut test = image::open(&input_path).unwrap().to_rgba8();
                downscaler_copy::remove_background_public(&mut test, &settings_copy);
                test
            };

            // Test wide range
            for test_scale in [16.0, 18.0, 19.2, 20.0, 22.0, 24.0, 25.0, 26.0, 28.0] {
                let score = downscaler_copy::grid_alignment_score_public(&test_img_no_bg, test_scale);
                let (w, h) = test_img_no_bg.dimensions();
                let out_w = (w as f32 / test_scale).round() as u32;
                let out_h = (h as f32 / test_scale).round() as u32;
                println!("  Scale {:.1}x: score = {:.2}, output = {}x{}", test_scale, score, out_w, out_h);
            }
        }
        Err(e) => {
            println!("Error running downscaler: {:?}", e);
        }
    }
}

/// Get the bounding box of non-transparent content (min_x, min_y, max_x, max_y)
fn get_content_bounds(img: &RgbaImage) -> (u32, u32, u32, u32) {
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
        // Empty image
        return (0, 0, 0, 0);
    }

    (min_x, min_y, max_x + 1, max_y + 1)
}

/// Count pixels with non-zero alpha
fn count_opaque_pixels(img: &RgbaImage) -> usize {
    let mut count = 0;
    for pixel in img.pixels() {
        if pixel[3] > 0 {
            count += 1;
        }
    }
    count
}
