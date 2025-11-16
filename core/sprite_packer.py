import json
from pathlib import Path
from typing import List, Tuple
from PIL import Image


def pack_sprites(files: List[Path], output_path: Path, settings: dict) -> Tuple[int, int]:
    """Pack sprites into a sheet and optionally export metadata."""
    
    # Load and sort images
    images = []
    for file_path in files:
        try:
            img = Image.open(file_path).convert("RGBA")
            images.append({
                "path": file_path,
                "name": file_path.name,
                "image": img,
                "width": img.width,
                "height": img.height,
            })
        except Exception as e:
            print(f"Error loading {file_path}: {e}")
    
    if not images:
        raise ValueError("No valid images to pack")
    
    # Sort images
    sort_order = settings['sort_order'].lower()
    if sort_order == "height":
        images.sort(key=lambda x: (-x["height"], -x["width"], x["name"].lower()))
    elif sort_order == "width":
        images.sort(key=lambda x: (-x["width"], -x["height"], x["name"].lower()))
    elif sort_order == "name":
        images.sort(key=lambda x: x["name"].lower())
    
    # Layout sprites
    max_width = settings['max_width']
    item_padding = settings['item_padding']
    row_padding = settings['row_padding']
    border_padding = settings['border_padding']
    
    x = border_padding
    y = border_padding
    row_height = 0
    placements = []
    used_width_this_row = border_padding
    max_used_width = 0
    
    for item in images:
        w, h = item["width"], item["height"]
        
        # Wrap to next row if needed
        if x > border_padding and (x + w + border_padding) > max_width:
            max_used_width = max(max_used_width, used_width_this_row)
            y += row_height + row_padding
            x = border_padding
            row_height = 0
            used_width_this_row = border_padding
        
        placements.append({
            "name": item["name"],
            "x": x,
            "y": y,
            "width": w,
            "height": h,
            "image": item["image"],
        })
        
        x += w + item_padding
        used_width_this_row = max(used_width_this_row, x - item_padding)
        row_height = max(row_height, h)
    
    # Finalize dimensions
    if placements:
        max_used_width = max(max_used_width, used_width_this_row)
        sheet_w = min(max_width, max_used_width + border_padding)
        sheet_h = y + row_height + border_padding
    else:
        sheet_w = border_padding * 2
        sheet_h = border_padding * 2
    
    # Create sprite sheet
    bg_color = settings['background_color']
    sheet = Image.new("RGBA", (sheet_w, sheet_h), bg_color)
    
    for p in placements:
        sheet.alpha_composite(p["image"], (p["x"], p["y"]))
    
    # Save sheet
    sheet.save(output_path)
    
    # Export metadata if requested
    if settings['export_metadata']:
        metadata = {
            "spriteSheet": output_path.name,
            "width": sheet_w,
            "height": sheet_h,
            "items": {}
        }
        
        for p in placements:
            metadata["items"][p["name"]] = {
                "x": p["x"],
                "y": p["y"],
                "w": p["width"],
                "h": p["height"],
            }
        
        json_path = output_path.with_suffix('.json')
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2)
    
    return (sheet_w, sheet_h)