use std::path::PathBuf;
use tauri_app_lib::downscaler::{downscale_image, DownscalerSettings, BgRemovalMode};

fn main() {
    let input_path = PathBuf::from("S:/Pixels/snowman-original.png");
    let output_path = PathBuf::from("S:/Pixels/rust-quick-test.png");

    println!("Testing new algorithm on snowman...");

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

    match downscale_image(input_path.clone(), output_path.clone(), settings) {
        Ok(result) => {
            println!("\n=== Results ===");
            println!("Original size: {:?}", result.original_size);
            println!("Final size: {:?}", result.final_size);
            println!("Scale detected: {:.4}x", result.scale_factor);
            println!("Grid detected: {}", result.grid_detected);
            println!("\nOutput saved to: {}", output_path.display());

            // Expected: 87x91 pixels at ~10.3x scale
            println!("\nExpected: 87x91 pixels at ~10.3x scale");
            let (exp_w, exp_h) = (87, 91);
            let diff_w = result.final_size.0 as i32 - exp_w;
            let diff_h = result.final_size.1 as i32 - exp_h;

            if diff_w == 0 && diff_h == 0 {
                println!("✓ PERFECT MATCH!");
            } else {
                println!("✗ Difference: ({}, {}) pixels", diff_w, diff_h);
            }
        }
        Err(e) => {
            eprintln!("Error: {:?}", e);
        }
    }

    // Test chair too
    println!("\n\n=== Testing chair-1.png ===");
    let chair_input = PathBuf::from("S:/Pixels/chair-1.png");
    let chair_output = PathBuf::from("S:/Pixels/rust-chair-test.png");

    let settings2 = DownscalerSettings {
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

    match downscale_image(chair_input.clone(), chair_output.clone(), settings2) {
        Ok(result) => {
            println!("Original size: {:?}", result.original_size);
            println!("Final size: {:?}", result.final_size);
            println!("Scale detected: {:.4}x", result.scale_factor);
            println!("Grid detected: {}", result.grid_detected);

            // Expected: ~39x40 or 40x41 pixels
            println!("\nExpected: ~39x40 or 40x41 pixels");
        }
        Err(e) => {
            eprintln!("Error: {:?}", e);
        }
    }
}
