from pathlib import Path
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
    QLabel, QSpinBox, QCheckBox, QComboBox,
    QPushButton, QScrollArea, QMessageBox, QFileDialog
)
from PySide6.QtCore import Qt, Signal, Slot, QThreadPool

from gui.widgets.image_list_widget import ImageListWidget
from gui.widgets.color_picker import ColorPickerWidget
from core.workers import PackWorker
from core.settings_manager import SettingsManager
from core.project_manager import ProjectManager, Project


class PackTab(QWidget):
    """Tab for packing sprites into a sheet."""
    
    def __init__(self, settings: SettingsManager, project_manager: ProjectManager, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.project_manager = project_manager
        self.threadpool = QThreadPool()
        self.current_folder = None
        self.current_project = None
        
        self.init_ui()
        self.load_settings()
        
    def init_ui(self):
        """Initialize the user interface."""
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(10)
        
        # Left side: Image list
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        
        # Folder info
        folder_layout = QHBoxLayout()
        folder_layout.addWidget(QLabel("<b>Images to Pack:</b>"))
        folder_layout.addStretch()
        
        # View mode toggle button
        self.view_toggle_btn = QPushButton("📋 List View")
        self.view_toggle_btn.setToolTip("Switch between thumbnail and list view")
        self.view_toggle_btn.setCheckable(True)
        self.view_toggle_btn.clicked.connect(self.toggle_view_mode)
        folder_layout.addWidget(self.view_toggle_btn)
        
        self.change_folder_btn = QPushButton("📁 Change Folder")
        self.change_folder_btn.setToolTip("Select a different folder for this tab")
        self.change_folder_btn.clicked.connect(self.change_folder)
        folder_layout.addWidget(self.change_folder_btn)
        left_layout.addLayout(folder_layout)
        
        self.folder_info_label = QLabel("<i>No folder loaded</i>")
        self.folder_info_label.setStyleSheet("font-size: 10px; color: #666;")
        left_layout.addWidget(self.folder_info_label)
        
        self.image_list = ImageListWidget()
        left_layout.addWidget(self.image_list)
        
        # Select/Deselect buttons
        button_layout = QHBoxLayout()
        self.select_all_btn = QPushButton("Select All")
        self.select_all_btn.clicked.connect(self.image_list.select_all)
        self.deselect_all_btn = QPushButton("Deselect All")
        self.deselect_all_btn.clicked.connect(self.image_list.deselect_all)
        button_layout.addWidget(self.select_all_btn)
        button_layout.addWidget(self.deselect_all_btn)
        left_layout.addLayout(button_layout)
        
        main_layout.addWidget(left_widget, stretch=2)
        
        # Right side: Settings (scrollable) + Fixed Button
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(10)
        
        # Scrollable settings area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        settings_widget = QWidget()
        settings_layout = QVBoxLayout(settings_widget)
        settings_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        
        # Layout Settings
        layout_group = QGroupBox("Layout Settings")
        layout_form = QVBoxLayout()
        
        width_layout = QHBoxLayout()
        width_layout.addWidget(QLabel("Max Sheet Width:"))
        self.max_width_spin = QSpinBox()
        self.max_width_spin.setRange(128, 8192)
        self.max_width_spin.setSingleStep(128)
        self.max_width_spin.setSuffix(" px")
        self.max_width_spin.setToolTip("Maximum width before wrapping to next row")
        width_layout.addWidget(self.max_width_spin)
        layout_form.addLayout(width_layout)
        
        sort_layout = QHBoxLayout()
        sort_layout.addWidget(QLabel("Sort By:"))
        self.sort_combo = QComboBox()
        self.sort_combo.addItems(["Height", "Width", "Name", "None"])
        self.sort_combo.setToolTip("Sorting order for sprite placement")
        sort_layout.addWidget(self.sort_combo)
        layout_form.addLayout(sort_layout)
        
        layout_group.setLayout(layout_form)
        settings_layout.addWidget(layout_group)
        
        # Spacing Settings
        spacing_group = QGroupBox("Spacing & Padding")
        spacing_layout = QVBoxLayout()
        
        item_layout = QHBoxLayout()
        item_layout.addWidget(QLabel("Item Padding:"))
        self.item_padding_spin = QSpinBox()
        self.item_padding_spin.setRange(0, 100)
        self.item_padding_spin.setSuffix(" px")
        self.item_padding_spin.setToolTip("Space between items in the same row")
        item_layout.addWidget(self.item_padding_spin)
        spacing_layout.addLayout(item_layout)
        
        row_layout = QHBoxLayout()
        row_layout.addWidget(QLabel("Row Padding:"))
        self.row_padding_spin = QSpinBox()
        self.row_padding_spin.setRange(0, 100)
        self.row_padding_spin.setSuffix(" px")
        self.row_padding_spin.setToolTip("Vertical space between rows")
        row_layout.addWidget(self.row_padding_spin)
        spacing_layout.addLayout(row_layout)
        
        border_layout = QHBoxLayout()
        border_layout.addWidget(QLabel("Border Padding:"))
        self.border_padding_spin = QSpinBox()
        self.border_padding_spin.setRange(0, 100)
        self.border_padding_spin.setSuffix(" px")
        self.border_padding_spin.setToolTip("Outer padding around entire sheet")
        border_layout.addWidget(self.border_padding_spin)
        spacing_layout.addLayout(border_layout)
        
        spacing_group.setLayout(spacing_layout)
        settings_layout.addWidget(spacing_group)
        
        # Background Settings
        bg_group = QGroupBox("Background")
        bg_layout = QVBoxLayout()
        
        bg_layout.addWidget(QLabel("Background Color (RGBA):"))
        self.bg_color_picker = ColorPickerWidget((0, 0, 0, 0))
        bg_layout.addWidget(self.bg_color_picker)
        
        bg_group.setLayout(bg_layout)
        settings_layout.addWidget(bg_group)
        
        # Export Settings
        export_group = QGroupBox("Export Options")
        export_layout = QVBoxLayout()
        
        self.export_metadata_check = QCheckBox("Export JSON Metadata")
        self.export_metadata_check.setChecked(True)
        self.export_metadata_check.setToolTip("Create JSON file with sprite positions")
        export_layout.addWidget(self.export_metadata_check)
        
        export_group.setLayout(export_layout)
        settings_layout.addWidget(export_group)
        
        scroll.setWidget(settings_widget)
        right_layout.addWidget(scroll, stretch=1)
        
        # Fixed button at bottom (outside scroll area)
        self.pack_btn = QPushButton("📦 Pack Sprites")
        self.pack_btn.setMinimumHeight(45)
        self.pack_btn.setStyleSheet("""
            QPushButton {
                background-color: #5294E2;
                color: #FFFFFF;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #6BA4F2;
            }
            QPushButton:disabled {
                background-color: #888888;
                color: #CCCCCC;
            }
        """)
        self.pack_btn.clicked.connect(self.pack_sprites)
        right_layout.addWidget(self.pack_btn)
        
        main_layout.addWidget(right_widget, stretch=1)

    @Slot()
    def toggle_view_mode(self):
        """Toggle between thumbnail and list view."""
        is_list_mode = self.view_toggle_btn.isChecked()
        self.image_list.set_view_mode(not is_list_mode)
        
        if is_list_mode:
            self.view_toggle_btn.setText("🖼️ Thumbnail View")
        else:
            self.view_toggle_btn.setText("📋 List View")

    def load_settings(self):
        """Load settings from settings manager."""
        self.max_width_spin.setValue(self.settings.get("pack/max_width"))
        self.item_padding_spin.setValue(self.settings.get("pack/item_padding"))
        self.row_padding_spin.setValue(self.settings.get("pack/row_padding"))
        self.border_padding_spin.setValue(self.settings.get("pack/border_padding"))
        self.bg_color_picker.set_color(self.settings.get("pack/background_color"))
        self.export_metadata_check.setChecked(self.settings.get("pack/export_metadata"))
        
        sort_order = self.settings.get("pack/sort_order")
        sort_index = {"height": 0, "width": 1, "name": 2, "none": 3}.get(sort_order.lower(), 0)
        self.sort_combo.setCurrentIndex(sort_index)
        
    def save_settings(self):
        """Save current settings."""
        self.settings.set("pack/max_width", self.max_width_spin.value())
        self.settings.set("pack/item_padding", self.item_padding_spin.value())
        self.settings.set("pack/row_padding", self.row_padding_spin.value())
        self.settings.set("pack/border_padding", self.border_padding_spin.value())
        self.settings.set("pack/background_color", self.bg_color_picker.get_color())
        self.settings.set("pack/export_metadata", self.export_metadata_check.isChecked())
        
        sort_map = ["height", "width", "name", "none"]
        self.settings.set("pack/sort_order", sort_map[self.sort_combo.currentIndex()])
        
    def load_project_folder(self, project: Project, folder: Path):
        """Load project and folder."""
        self.current_project = project
        self.current_folder = folder
        self.image_list.load_images(folder)
        self.folder_info_label.setText(f"<i>{folder}</i>")
        
    @Slot()
    def change_folder(self):
        """Change the folder for this tab."""
        if not self.current_project:
            QMessageBox.warning(
                self, 
                "No Project Selected", 
                "Please add or select a project from the toolbar first."
            )
            return
        
        # Get current folder or use project path as default
        start_dir = str(self.current_folder) if self.current_folder else str(self.current_project.path)
        
        folder = QFileDialog.getExistingDirectory(
            self,
            "Select Folder for Pack Sprites Tab",
            start_dir,
            QFileDialog.Option.ShowDirsOnly
        )
        
        if folder:
            folder_path = Path(folder)
            self.current_folder = folder_path
            
            # Reload images
            self.image_list.load_images(folder_path)
            self.folder_info_label.setText(f"<i>{folder_path}</i>")
            
            # Save this folder for the project with correct tab name
            self.project_manager.set_project_folder(self.current_project, "pack", folder_path)
            
    def refresh_files(self):
        """Refresh file list while maintaining selection state."""
        if self.current_folder:
            self.image_list.load_images_preserve_selection(self.current_folder)
        
    @Slot()
    def pack_sprites(self):
        """Pack selected sprites."""
        selected_files = self.image_list.get_selected_files()
        
        if not selected_files:
            QMessageBox.warning(self, "No Images Selected", "Please select at least one image.")
            return
            
        # Suggest output in current folder
        if self.current_folder:
            default_path = str(self.current_folder / "sprite_sheet.png")
        else:
            default_path = "sprite_sheet.png"
            
        output_file, _ = QFileDialog.getSaveFileName(
            self,
            "Save Sprite Sheet",
            default_path,
            "PNG Images (*.png)"
        )
        
        if not output_file:
            return
            
        output_path = Path(output_file)
        
        self.save_settings()
        
        settings = {
            "max_width": self.max_width_spin.value(),
            "item_padding": self.item_padding_spin.value(),
            "row_padding": self.row_padding_spin.value(),
            "border_padding": self.border_padding_spin.value(),
            "background_color": self.bg_color_picker.get_color(),
            "sort_order": ["height", "width", "name", "none"][self.sort_combo.currentIndex()],
            "export_metadata": self.export_metadata_check.isChecked(),
        }
        
        worker = PackWorker(selected_files, output_path, settings)
        worker.signals.progress.connect(self.on_progress)
        worker.signals.finished.connect(self.on_pack_finished)
        worker.signals.error.connect(self.on_pack_error)
        
        self.pack_btn.setEnabled(False)
        self.pack_btn.setText("Packing...")
        
        self.threadpool.start(worker)
        
    @Slot(str)
    def on_progress(self, message):
        self.pack_btn.setText(message)
        
    @Slot(tuple)
    def on_pack_finished(self, result):
        output_path, size = result
        self.pack_btn.setEnabled(True)
        self.pack_btn.setText("📦 Pack Sprites")
        
        w, h = size
        QMessageBox.information(
            self,
            "Packing Complete",
            f"Sprite sheet created successfully!\n\n"
            f"Size: {w}×{h} pixels\n"
            f"Output: {output_path}"
        )
        
    @Slot(str)
    def on_pack_error(self, error_msg):
        self.pack_btn.setEnabled(True)
        self.pack_btn.setText("📦 Pack Sprites")
        QMessageBox.critical(self, "Packing Error", f"An error occurred:\n\n{error_msg}")