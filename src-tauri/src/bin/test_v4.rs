use tauri_app_lib::downscaler::{downscale_image, DownscalerSettings, BgRemovalMode};
use std::path::PathBuf;

fn main() {
    let test_dir = PathBuf::from(r"S:\Pixels\downscale_tests");
    let input_dir = test_dir.join("input");
    let output_dir = test_dir.join("output");

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

    let test_images = [
        "greenhouse-original.png",
        "grindstone-original.png",
        "truck-original.png",
        "chair-1.png",
        "snowman-original.png",
    ];

    println!("Testing Rust v4 Downscaler");
    println!("==========================");

    for name in &test_images {
        let input_path = input_dir.join(name);
        let stem = name.replace(".png", "");
        let output_path = output_dir.join(format!("{}-rust-v4.png", stem));

        if !input_path.exists() {
            println!("{}: Input not found", name);
            continue;
        }

        match downscale_image(input_path.clone(), output_path.clone(), settings.clone()) {
            Ok(result) => {
                println!("{}", name);
                println!("  Original: {}x{}", result.original_size.0, result.original_size.1);
                println!("  Final:    {}x{}", result.final_size.0, result.final_size.1);
                println!("  Scale:    {:.1}", result.scale_factor);
                println!("  Grid:     {}", if result.grid_detected { "detected" } else { "not detected" });
                println!();
            }
            Err(e) => {
                println!("{}: Error - {:?}", name, e);
            }
        }
    }

    println!("Done! Check output folder for results.");
}
