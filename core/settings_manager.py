from PySide6.QtCore import QSettings
from typing import Any, Optional


class SettingsManager:
    """Manager for persistent application settings using QSettings."""
    
    # Default values for all settings
    DEFAULTS = {
        # Post-processing defaults
        "process/alpha_low_cutoff": 200,
        "process/alpha_high_min": 200,
        "process/alpha_high_max": 255,
        "process/enable_color_simplify": True,
        "process/lab_merge_threshold": 3.0,
        "process/outline_color": (17, 6, 2, 255),  # RGBA
        "process/edge_transparent_cutoff": 0,
        "process/outline_connectivity": 4,
        "process/outline_thickness": 1,
        "process/prefix_to_strip": "",  # Changed from "era_angel_"
        
        # Packing defaults
        "pack/max_width": 900,
        "pack/item_padding": 6,
        "pack/row_padding": 10,
        "pack/border_padding": 8,
        "pack/background_color": (0, 0, 0, 0),  # Transparent RGBA
        "pack/sort_order": "height",
        "pack/export_metadata": True,
        
        # Downscale defaults
        "downscale/enable_fine_tune": True,
        "downscale/bg_removal_mode": "conservative",  # conservative, aggressive, none
        "downscale/bg_tolerance": 15,
        "downscale/bg_edge_tolerance": 25,
        "downscale/preserve_dark_lines": True,
        "downscale/dark_line_threshold": 50,
        "downscale/auto_trim": True,
        "downscale/pad_canvas": True,
        "downscale/canvas_multiple": 16,
        
        # UI defaults
        "last_directory": "",
        "window_geometry": None,
        "window_state": None,
    }
    
    def __init__(self):
        self.settings = QSettings()
        
    def get(self, key: str, default: Optional[Any] = None) -> Any:
        """Get a setting value."""
        if default is None:
            default = self.DEFAULTS.get(key)
        
        value = self.settings.value(key, default)
        
        # Handle tuple conversion (QSettings stores as list)
        if isinstance(default, tuple) and isinstance(value, list):
            return tuple(value)
        
        # Handle bool conversion
        if isinstance(default, bool):
            return value in (True, 'true', '1', 1)
            
        # Handle numeric conversion
        if isinstance(default, (int, float)) and isinstance(value, str):
            try:
                return type(default)(value)
            except (ValueError, TypeError):
                return default
                
        return value
        
    def set(self, key: str, value: Any):
        """Set a setting value."""
        self.settings.setValue(key, value)
        
    def reset(self):
        """Reset all settings to defaults."""
        self.settings.clear()
        
    def get_all_process_settings(self) -> dict:
        """Get all post-processing settings as a dictionary."""
        return {
            "alpha_low_cutoff": self.get("process/alpha_low_cutoff"),
            "alpha_high_min": self.get("process/alpha_high_min"),
            "alpha_high_max": self.get("process/alpha_high_max"),
            "enable_color_simplify": self.get("process/enable_color_simplify"),
            "lab_merge_threshold": self.get("process/lab_merge_threshold"),
            "outline_color": self.get("process/outline_color"),
            "edge_transparent_cutoff": self.get("process/edge_transparent_cutoff"),
            "outline_connectivity": self.get("process/outline_connectivity"),
            "outline_thickness": self.get("process/outline_thickness"),
            "prefix_to_strip": self.get("process/prefix_to_strip"),
        }
        
    def get_all_pack_settings(self) -> dict:
        """Get all packing settings as a dictionary."""
        return {
            "max_width": self.get("pack/max_width"),
            "item_padding": self.get("pack/item_padding"),
            "row_padding": self.get("pack/row_padding"),
            "border_padding": self.get("pack/border_padding"),
            "background_color": self.get("pack/background_color"),
            "sort_order": self.get("pack/sort_order"),
            "export_metadata": self.get("pack/export_metadata"),
        }
    
    def get_all_downscale_settings(self) -> dict:
        """Get all downscale settings as a dictionary."""
        return {
            "enable_fine_tune": self.get("downscale/enable_fine_tune"),
            "bg_removal_mode": self.get("downscale/bg_removal_mode"),
            "bg_tolerance": self.get("downscale/bg_tolerance"),
            "bg_edge_tolerance": self.get("downscale/bg_edge_tolerance"),
            "preserve_dark_lines": self.get("downscale/preserve_dark_lines"),
            "dark_line_threshold": self.get("downscale/dark_line_threshold"),
            "auto_trim": self.get("downscale/auto_trim"),
            "pad_canvas": self.get("downscale/pad_canvas"),
            "canvas_multiple": self.get("downscale/canvas_multiple"),
        }