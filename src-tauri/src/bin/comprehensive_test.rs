use std::path::PathBuf;
use tauri_app_lib::downscaler::{downscale_image, DownscalerSettings, BgRemovalMode};
use image::GenericImageView;

fn main() {
    let test_cases = vec![
        (
            "greenhouse-original.png",
            "greenhouse-downscaled-python.png",
            "greenhouse-rust-output.png",
            (112, 128),
        ),
        (
            "grindstone-original.png",
            "grindstone-downscaled-python.png",
            "grindstone-rust-output.png",
            (96, 80),
        ),
        (
            "truck-original.png",
            "truck-downscaled-python.png",
            "truck-rust-output.png",
            (144, 80),
        ),
    ];

    let settings = DownscalerSettings {
        bg_removal_mode: BgRemovalMode::Conservative,
        bg_tolerance: 15,
        bg_edge_tolerance: 30,
        preserve_dark_lines: false,
        dark_line_threshold: 100,
        auto_trim: true,
        enable_fine_tune: false,  // Disable fine-tuning - test padding alone
        pad_canvas: true,          // Enable canvas padding to 16x multiples
        canvas_multiple: 16,
    };

    println!("=== Testing Rust Downscaler Against Verified Cases ===\n");

    let mut all_pass = true;

    for (input_name, expected_name, output_name, expected_size) in test_cases {
        let input_path = PathBuf::from(format!("S:/Pixels/downscale_tests/{}", input_name));
        let expected_path = PathBuf::from(format!("S:/Pixels/downscale_tests/{}", expected_name));
        let output_path = PathBuf::from(format!("S:/Pixels/downscale_tests/{}", output_name));

        println!("Testing: {}", input_name);
        println!("  Expected output: {}x{}", expected_size.0, expected_size.1);

        match downscale_image(input_path.clone(), output_path.clone(), settings.clone()) {
            Ok(result) => {
                println!("  Rust output: {:?}", result.final_size);
                println!("  Scale detected: {:.2}x", result.scale_factor);
                println!("  Grid detected: {}", result.grid_detected);

                let diff_w = result.final_size.0 as i32 - expected_size.0 as i32;
                let diff_h = result.final_size.1 as i32 - expected_size.1 as i32;

                if diff_w == 0 && diff_h == 0 {
                    println!("  ✓ PERFECT MATCH!");
                } else {
                    println!("  ✗ Difference: ({}, {}) pixels", diff_w, diff_h);
                    all_pass = false;

                    // Calculate percentage error
                    let error_pct = ((diff_w.abs() + diff_h.abs()) as f32
                        / (expected_size.0 + expected_size.1) as f32 * 100.0);
                    println!("  Error: {:.1}%", error_pct);
                }

                // Compare pixels with expected
                if let Ok(expected_img) = image::open(&expected_path) {
                    if let Ok(rust_img) = image::open(&output_path) {
                        let exp_dims = expected_img.dimensions();
                        let rust_dims = rust_img.dimensions();

                        if exp_dims == rust_dims {
                            // Calculate pixel-level similarity
                            let expected_rgba = expected_img.to_rgba8();
                            let rust_rgba = rust_img.to_rgba8();

                            let mut total_diff = 0u64;
                            let mut pixel_count = 0u64;

                            for y in 0..exp_dims.1 {
                                for x in 0..exp_dims.0 {
                                    let exp_pixel = expected_rgba.get_pixel(x, y);
                                    let rust_pixel = rust_rgba.get_pixel(x, y);

                                    for i in 0..4 {
                                        total_diff += (exp_pixel[i] as i32 - rust_pixel[i] as i32).abs() as u64;
                                    }
                                    pixel_count += 4;
                                }
                            }

                            let avg_diff = total_diff as f32 / pixel_count as f32;
                            let similarity = 100.0 - (avg_diff / 2.55);
                            println!("  Pixel similarity: {:.2}%", similarity);

                            if similarity < 95.0 {
                                all_pass = false;
                            }
                        }
                    }
                }
            }
            Err(e) => {
                println!("  ✗ ERROR: {:?}", e);
                all_pass = false;
            }
        }

        println!();
    }

    println!("=== Summary ===");
    if all_pass {
        println!("✓ All tests passed!");
    } else {
        println!("✗ Some tests failed. Review output above.");
    }
}
