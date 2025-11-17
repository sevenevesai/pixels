use image::GenericImageView;
use std::path::PathBuf;
use tauri_app_lib::downscaler::{DownscalerSettings, BgRemovalMode};

fn main() {
    let input_path = PathBuf::from("S:/Pixels/downscale_tests/greenhouse-original.png");
    let output_path = PathBuf::from("S:/Pixels/downscale_tests/greenhouse-rust-bg-removed.png");

    let img = image::open(&input_path).unwrap().to_rgba8();

    let orig_opaque: usize = img.pixels().filter(|p| p[3] > 0).count();

    let mut rgba = img.clone();

    // Apply same settings as Python
    let settings = DownscalerSettings {
        bg_removal_mode: BgRemovalMode::Conservative,
        bg_tolerance: 15,
        bg_edge_tolerance: 30,
        preserve_dark_lines: false,
        dark_line_threshold: 100,
        auto_trim: false,
        enable_fine_tune: false,
        pad_canvas: false,
        canvas_multiple: 16,
    };

    // This is a hack to access the private function - we'll need to make it public or copy the logic
    // For now, let me just inline the background removal logic here

    tauri_app_lib::downscaler::remove_background_public(&mut rgba, &settings);

    let clean_opaque: usize = rgba.pixels().filter(|p| p[3] > 0).count();

    rgba.save(&output_path).unwrap();

    println!("Original opaque pixels: {}", orig_opaque);
    println!("After removal opaque pixels: {}", clean_opaque);
    println!("Removed: {} pixels", orig_opaque - clean_opaque);
    println!("Saved to: {}", output_path.display());

    // Python removed: 9616 pixels
    println!("\nPython removed: 9616 pixels");
    println!("Match: {}", (orig_opaque - clean_opaque) == 9616);
}
