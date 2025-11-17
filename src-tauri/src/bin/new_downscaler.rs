use image::RgbaImage;
use std::path::PathBuf;

fn main() {
    let input_path = PathBuf::from("S:/Pixels/snowman-original.png");
    let expected_path = PathBuf::from("S:/Pixels/snowman-downscaled.png");

    let input_img = image::open(&input_path).unwrap().to_rgba8();
    let expected_img = image::open(&expected_path).unwrap().to_rgba8();

    // Remove background
    let mut test_img = input_img.clone();
    remove_background(&mut test_img);

    println!("=== Block Uniformity Test ===");
    println!("Target output: {:?}", expected_img.dimensions());

    // Test common scales (fast)
    let test_scales = vec![4, 6, 8, 10, 12, 14, 16, 18, 20, 24, 28, 32];

    for &scale in &test_scales {
        let sharpness = edge_sharpness_score(&test_img, scale);
        let (w, h) = test_img.dimensions();
        let out_w = w / scale;
        let out_h = h / scale;
        println!("Scale {:2}x: sharpness={:.2}, output={}x{}",
                 scale, sharpness, out_w, out_h);
    }
}

/// Score based on edge sharpness after downscaling
/// Higher sharpness = better grid alignment
fn edge_sharpness_score(img: &RgbaImage, scale: u32) -> f32 {
    use image::imageops::FilterType;

    let (width, height) = img.dimensions();

    if scale == 0 || scale > width || scale > height {
        return 0.0;
    }

    let new_width = width / scale;
    let new_height = height / scale;

    if new_width < 2 || new_height < 2 {
        return 0.0;
    }

    // Downscale
    let downscaled = image::imageops::resize(
        img,
        new_width,
        new_height,
        FilterType::Nearest,
    );

    // Calculate edge strength (Sobel-like)
    let mut edge_strength = 0.0f32;
    let mut count = 0;

    for y in 1..(new_height - 1) {
        for x in 1..(new_width - 1) {
            let p = downscaled.get_pixel(x, y);

            if p[3] == 0 {
                continue;
            }

            count += 1;

            // Horizontal gradient
            let left = downscaled.get_pixel(x - 1, y);
            let right = downscaled.get_pixel(x + 1, y);
            let gx = ((right[0] as i32 - left[0] as i32).abs() +
                     (right[1] as i32 - left[1] as i32).abs() +
                     (right[2] as i32 - left[2] as i32).abs()) as f32;

            // Vertical gradient
            let top = downscaled.get_pixel(x, y - 1);
            let bottom = downscaled.get_pixel(x, y + 1);
            let gy = ((bottom[0] as i32 - top[0] as i32).abs() +
                     (bottom[1] as i32 - top[1] as i32).abs() +
                     (bottom[2] as i32 - top[2] as i32).abs()) as f32;

            edge_strength += (gx * gx + gy * gy).sqrt();
        }
    }

    if count == 0 {
        return 0.0;
    }

    edge_strength / count as f32
}

fn block_variance_score(img: &RgbaImage, scale: u32) -> f32 {
    let (width, height) = img.dimensions();

    if scale == 0 || scale > width || scale > height {
        return f32::MAX;
    }

    let blocks_x = width / scale;
    let blocks_y = height / scale;

    if blocks_x == 0 || blocks_y == 0 {
        return f32::MAX;
    }

    let mut total_variance = 0.0f32;
    let mut content_blocks = 0;

    // Test each block
    for by in 0..blocks_y {
        for bx in 0..blocks_x {
            let start_x = bx * scale;
            let start_y = by * scale;

            // Collect all pixels in this block
            let mut pixels = Vec::new();
            let mut has_content = false;

            for dy in 0..scale {
                for dx in 0..scale {
                    let x = start_x + dx;
                    let y = start_y + dy;

                    if x >= width || y >= height {
                        continue;
                    }

                    let pixel = img.get_pixel(x, y);

                    // Skip fully transparent
                    if pixel[3] == 0 {
                        continue;
                    }

                    has_content = true;
                    pixels.push(pixel);
                }
            }

            if !has_content || pixels.is_empty() {
                continue;
            }

            content_blocks += 1;

            // Calculate variance for this block
            // Mean color
            let mut mean_r = 0.0f32;
            let mut mean_g = 0.0f32;
            let mut mean_b = 0.0f32;

            for p in &pixels {
                mean_r += p[0] as f32;
                mean_g += p[1] as f32;
                mean_b += p[2] as f32;
            }

            let n = pixels.len() as f32;
            mean_r /= n;
            mean_g /= n;
            mean_b /= n;

            // Variance
            let mut var = 0.0f32;
            for p in &pixels {
                let dr = p[0] as f32 - mean_r;
                let dg = p[1] as f32 - mean_g;
                let db = p[2] as f32 - mean_b;
                var += dr * dr + dg * dg + db * db;
            }

            total_variance += var / n;
        }
    }

    if content_blocks == 0 {
        return f32::MAX;
    }

    total_variance / content_blocks as f32
}

fn remove_background(img: &mut RgbaImage) {
    let (width, height) = img.dimensions();

    // Sample edge to find bg color
    let bg_color = *img.get_pixel(0, 0);
    let tolerance = 30i32;

    for y in 0..height {
        for x in 0..width {
            let pixel = img.get_pixel(x, y);

            let dr = pixel[0] as i32 - bg_color[0] as i32;
            let dg = pixel[1] as i32 - bg_color[1] as i32;
            let db = pixel[2] as i32 - bg_color[2] as i32;
            let dist = (dr * dr + dg * dg + db * db).abs();

            if dist < tolerance * tolerance {
                img.put_pixel(x, y, image::Rgba([pixel[0], pixel[1], pixel[2], 0]));
            }
        }
    }
}
