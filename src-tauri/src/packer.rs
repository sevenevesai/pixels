use image::{DynamicImage, RgbaImage, Rgba, GenericImageView};
use serde::{Deserialize, Serialize};
use std::path::PathBuf;
use crate::error::{Result, PixelsError};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PackerSettings {
    pub max_width: u32,
    pub item_padding: u32,
    pub row_padding: u32,
    pub border_padding: u32,
    pub background_color: (u8, u8, u8, u8),
    pub sort_order: SortOrder,
    pub export_metadata: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum SortOrder {
    Height,
    Width,
    Name,
    None,
}

impl Default for PackerSettings {
    fn default() -> Self {
        Self {
            max_width: 2048,
            item_padding: 2,
            row_padding: 2,
            border_padding: 4,
            background_color: (0, 0, 0, 0),
            sort_order: SortOrder::Height,
            export_metadata: true,
        }
    }
}

#[derive(Debug, Clone)]
struct SpriteItem {
    name: String,
    image: DynamicImage,
    width: u32,
    height: u32,
}

#[derive(Debug, Clone, Serialize)]
pub struct SpriteMetadata {
    pub x: u32,
    pub y: u32,
    pub w: u32,
    pub h: u32,
}

#[derive(Debug, Clone, Serialize)]
pub struct PackerResult {
    pub sprite_sheet: String, // Path to output
    pub width: u32,
    pub height: u32,
    pub items: std::collections::HashMap<String, SpriteMetadata>,
}

pub fn pack_sprites(
    input_paths: Vec<PathBuf>,
    output_path: PathBuf,
    settings: PackerSettings,
) -> Result<PackerResult> {
    if input_paths.is_empty() {
        return Err(PixelsError::InvalidParameter("No input files provided".to_string()));
    }

    // Load all sprites
    let mut sprites: Vec<SpriteItem> = Vec::new();
    for path in &input_paths {
        let img = image::open(path)
            .map_err(|e| PixelsError::Processing(format!("Failed to load {}: {}", path.display(), e)))?;

        let (width, height) = img.dimensions();
        let name = path.file_stem()
            .and_then(|s| s.to_str())
            .unwrap_or("unknown")
            .to_string();

        sprites.push(SpriteItem {
            name,
            image: img,
            width,
            height,
        });
    }

    // Sort sprites based on settings
    match settings.sort_order {
        SortOrder::Height => sprites.sort_by(|a, b| b.height.cmp(&a.height)),
        SortOrder::Width => sprites.sort_by(|a, b| b.width.cmp(&a.width)),
        SortOrder::Name => sprites.sort_by(|a, b| a.name.cmp(&b.name)),
        SortOrder::None => {}
    }

    // Layout algorithm (greedy bin packing)
    let mut positions: Vec<(u32, u32)> = Vec::new();
    let mut current_x = settings.border_padding;
    let mut current_y = settings.border_padding;
    let mut row_height = 0u32;
    let max_width = settings.max_width;

    for sprite in &sprites {
        let sprite_width = sprite.width + settings.item_padding;
        let sprite_height = sprite.height + settings.item_padding;

        // Check if we need to wrap to a new row
        if current_x + sprite.width + settings.border_padding > max_width && current_x > settings.border_padding {
            current_x = settings.border_padding;
            current_y += row_height + settings.row_padding;
            row_height = 0;
        }

        positions.push((current_x, current_y));
        current_x += sprite_width;
        row_height = row_height.max(sprite_height);
    }

    // Calculate final sheet dimensions
    let sheet_width = max_width;
    let sheet_height = current_y + row_height + settings.border_padding;

    // Create sprite sheet
    let mut sheet = RgbaImage::from_pixel(
        sheet_width,
        sheet_height,
        Rgba([
            settings.background_color.0,
            settings.background_color.1,
            settings.background_color.2,
            settings.background_color.3,
        ]),
    );

    // Composite sprites onto sheet
    let mut metadata_items = std::collections::HashMap::new();
    for (sprite, (x, y)) in sprites.iter().zip(positions.iter()) {
        let rgba = sprite.image.to_rgba8();
        image::imageops::overlay(&mut sheet, &rgba, *x as i64, *y as i64);

        metadata_items.insert(
            sprite.name.clone(),
            SpriteMetadata {
                x: *x,
                y: *y,
                w: sprite.width,
                h: sprite.height,
            },
        );
    }

    // Save sprite sheet
    sheet.save(&output_path)?;

    // Save metadata if requested
    if settings.export_metadata {
        let metadata_path = output_path.with_extension("json");
        let result = PackerResult {
            sprite_sheet: output_path.file_name()
                .and_then(|s| s.to_str())
                .unwrap_or("spritesheet.png")
                .to_string(),
            width: sheet_width,
            height: sheet_height,
            items: metadata_items.clone(),
        };

        let json = serde_json::to_string_pretty(&result)?;
        std::fs::write(metadata_path, json)?;
    }

    Ok(PackerResult {
        sprite_sheet: output_path.to_string_lossy().to_string(),
        width: sheet_width,
        height: sheet_height,
        items: metadata_items,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_default_settings() {
        let settings = PackerSettings::default();
        assert_eq!(settings.max_width, 2048);
        assert_eq!(settings.item_padding, 2);
    }
}
