use std::path::PathBuf;
use tauri_app_lib::downscaler::{downscale_image, DownscalerSettings, BgRemovalMode};

fn main() {
    let input_path = PathBuf::from("S:/Pixels/downscale_tests/greenhouse-original.png");
    let output_path = PathBuf::from("S:/Pixels/downscale_tests/greenhouse-rust-single.png");

    let settings = DownscalerSettings {
        bg_removal_mode: BgRemovalMode::Conservative,
        bg_tolerance: 15,
        bg_edge_tolerance: 30,
        preserve_dark_lines: false,
        dark_line_threshold: 100,
        auto_trim: true,
        enable_fine_tune: false,
        pad_canvas: true,
        canvas_multiple: 16,
    };

    match downscale_image(input_path, output_path, settings) {
        Ok(result) => {
            println!("Result: {:?}", result.final_size);
        }
        Err(e) => println!("Error: {:?}", e),
    }
}
