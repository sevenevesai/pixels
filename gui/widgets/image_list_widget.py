from pathlib import Path
from typing import List, Optional
from PySide6.QtWidgets import QListWidget, QListWidgetItem
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QIcon


class ImageListWidget(QListWidget):
    """Custom list widget for displaying and selecting images."""
    
    SUPPORTED_FORMATS = {'.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp'}
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setIconSize(QSize(64, 64))
        self.setSpacing(2)
        self.setViewMode(QListWidget.ViewMode.IconMode)  # Default to thumbnail view
        self.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.setMovement(QListWidget.Movement.Static)
        self.setWrapping(True)
        
    def set_view_mode(self, thumbnail_mode: bool):
        """Switch between thumbnail and list view."""
        if thumbnail_mode:
            self.setViewMode(QListWidget.ViewMode.IconMode)
            self.setIconSize(QSize(64, 64))
            self.setSpacing(8)
            self.setWrapping(True)
        else:
            self.setViewMode(QListWidget.ViewMode.ListMode)
            self.setIconSize(QSize(32, 32))
            self.setSpacing(2)
            self.setWrapping(False)
        
    def load_images(self, folder: Path):
        """Load images from folder."""
        self.clear()
        
        if not folder.exists():
            return
        
        # Get all image files
        image_files = []
        for fmt in self.SUPPORTED_FORMATS:
            image_files.extend(folder.glob(f"*{fmt}"))
        
        # Sort by name
        image_files.sort(key=lambda p: p.name.lower())
        
        # Add to list
        for file_path in image_files:
            item = QListWidgetItem(file_path.name)
            item.setCheckState(Qt.CheckState.Checked)
            item.setData(Qt.ItemDataRole.UserRole, str(file_path))
            
            # Try to set thumbnail
            try:
                icon = QIcon(str(file_path))
                if not icon.isNull():
                    item.setIcon(icon)
            except Exception:
                pass
            
            self.addItem(item)
    
    def load_images_preserve_selection(self, folder: Path):
        """Load images from folder while preserving check states."""
        # Save current check states
        checked_names = set()
        for i in range(self.count()):
            item = self.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                checked_names.add(item.text())
        
        # Clear and reload
        self.clear()
        
        if not folder.exists():
            return
        
        # Get all image files
        image_files = []
        for fmt in self.SUPPORTED_FORMATS:
            image_files.extend(folder.glob(f"*{fmt}"))
        
        # Sort by name
        image_files.sort(key=lambda p: p.name.lower())
        
        # Add to list with preserved check state
        for file_path in image_files:
            item = QListWidgetItem(file_path.name)
            
            # Restore check state if it was checked before
            if file_path.name in checked_names:
                item.setCheckState(Qt.CheckState.Checked)
            else:
                item.setCheckState(Qt.CheckState.Unchecked)
            
            item.setData(Qt.ItemDataRole.UserRole, str(file_path))
            
            # Try to set thumbnail
            try:
                icon = QIcon(str(file_path))
                if not icon.isNull():
                    item.setIcon(icon)
            except Exception:
                pass
            
            self.addItem(item)
    
    def get_selected_files(self) -> List[Path]:
        """Get list of checked file paths."""
        selected = []
        for i in range(self.count()):
            item = self.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                file_path = item.data(Qt.ItemDataRole.UserRole)
                if file_path:
                    selected.append(Path(file_path))
        return selected
    
    def get_file_path(self, item: QListWidgetItem) -> Optional[Path]:
        """Get file path from list item."""
        file_path = item.data(Qt.ItemDataRole.UserRole)
        if file_path:
            return Path(file_path)
        return None
    
    def select_all(self):
        """Check all items."""
        for i in range(self.count()):
            self.item(i).setCheckState(Qt.CheckState.Checked)
    
    def deselect_all(self):
        """Uncheck all items."""
        for i in range(self.count()):
            self.item(i).setCheckState(Qt.CheckState.Unchecked)