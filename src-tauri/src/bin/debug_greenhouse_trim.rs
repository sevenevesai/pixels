use std::path::PathBuf;
use tauri_app_lib::downscaler::{downscale_image, DownscalerSettings, BgRemovalMode};
use image::GenericImageView;

fn main() {
    let input_path = PathBuf::from("S:/Pixels/downscale_tests/greenhouse-original.png");
    let output_path = PathBuf::from("S:/Pixels/downscale_tests/greenhouse-rust-debug.png");

    let settings = DownscalerSettings {
        bg_removal_mode: BgRemovalMode::Conservative,
        bg_tolerance: 15,
        bg_edge_tolerance: 30,
        preserve_dark_lines: false,
        dark_line_threshold: 100,
        auto_trim: true,
        enable_fine_tune: false,
        pad_canvas: false,
        canvas_multiple: 16,
    };

    match downscale_image(input_path, output_path.clone(), settings) {
        Ok(result) => {
            println!("Result: {:?}", result);

            // Load and check the actual output
            if let Ok(img) = image::open(&output_path) {
                println!("Output image dimensions: {:?}", img.dimensions());
                println!("Expected: 112x128");
            }
        }
        Err(e) => println!("Error: {:?}", e),
    }
}
