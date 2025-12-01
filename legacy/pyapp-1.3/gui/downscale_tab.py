from pathlib import Path
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
    QLabel, QSpinBox, QCheckBox, QComboBox,
    QPushButton, QScrollArea, QMessageBox, QSlider,
    QLineEdit, QFileDialog
)
from PySide6.QtCore import Qt, Signal, Slot, QThreadPool

from gui.widgets.image_list_widget import ImageListWidget
from core.workers import DownscaleWorker
from core.settings_manager import SettingsManager
from core.project_manager import ProjectManager, Project


class DownscaleTab(QWidget):
    """Tab for downscaling AI-generated images to true pixel resolution."""
    
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
        folder_layout.addWidget(QLabel("<b>AI Images to Downscale:</b>"))
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
        
        # Select/Deselect/Smart Select buttons
        button_layout = QHBoxLayout()
        self.select_all_btn = QPushButton("Select All")
        self.select_all_btn.clicked.connect(self.image_list.select_all)
        self.deselect_all_btn = QPushButton("Deselect All")
        self.deselect_all_btn.clicked.connect(self.image_list.deselect_all)
        self.smart_select_btn = QPushButton("🎯 Smart Select")
        self.smart_select_btn.setToolTip("Select only images that haven't been processed yet")
        self.smart_select_btn.clicked.connect(self.smart_select)
        button_layout.addWidget(self.select_all_btn)
        button_layout.addWidget(self.deselect_all_btn)
        button_layout.addWidget(self.smart_select_btn)
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
        
        # Output Settings
        output_group = QGroupBox("Output Settings")
        output_layout = QVBoxLayout()
        
        # Output folder
        folder_layout = QHBoxLayout()
        folder_layout.addWidget(QLabel("Output Folder:"))
        self.output_folder_edit = QLineEdit()
        self.output_folder_edit.setPlaceholderText("downscaled")
        self.output_folder_edit.textChanged.connect(self.on_output_settings_changed)
        folder_layout.addWidget(self.output_folder_edit)
        self.browse_output_btn = QPushButton("Browse")
        self.browse_output_btn.clicked.connect(self.browse_output_folder)
        folder_layout.addWidget(self.browse_output_btn)
        output_layout.addLayout(folder_layout)
        
        # Filename transform
        self.use_transform_check = QCheckBox("Use Filename Prefix/Suffix")
        self.use_transform_check.setToolTip("Transform output filenames with prefix/suffix")
        self.use_transform_check.toggled.connect(self.on_use_transform_toggled)
        self.use_transform_check.toggled.connect(self.on_output_settings_changed)
        output_layout.addWidget(self.use_transform_check)
        
        # Prefix/Suffix
        transform_layout = QHBoxLayout()
        transform_layout.addWidget(QLabel("Prefix:"))
        self.prefix_edit = QLineEdit()
        self.prefix_edit.setPlaceholderText("")
        self.prefix_edit.textChanged.connect(self.on_output_settings_changed)
        transform_layout.addWidget(self.prefix_edit)
        transform_layout.addWidget(QLabel("Suffix:"))
        self.suffix_edit = QLineEdit()
        self.suffix_edit.setPlaceholderText("")
        self.suffix_edit.textChanged.connect(self.on_output_settings_changed)
        transform_layout.addWidget(self.suffix_edit)
        output_layout.addLayout(transform_layout)
        
        output_info = QLabel(
            "<i><small>Smart Select uses these settings to check if files already exist.</small></i>"
        )
        output_info.setWordWrap(True)
        output_layout.addWidget(output_info)
        
        output_group.setLayout(output_layout)
        settings_layout.addWidget(output_group)
        
        # Scale Detection Settings
        scale_group = QGroupBox("Scale Detection")
        scale_layout = QVBoxLayout()
        
        self.fine_tune_check = QCheckBox("Enable Fine-Tuning (fractional scales)")
        self.fine_tune_check.setChecked(True)
        self.fine_tune_check.setToolTip("Test fractional scales for more precise results")
        scale_layout.addWidget(self.fine_tune_check)
        
        scale_info = QLabel(
            "<i><small>Automatically detects the pixel grid using FFT analysis<br>"
            "and tests scale factors from 6x to 20x by default.</small></i>"
        )
        scale_info.setWordWrap(True)
        scale_layout.addWidget(scale_info)
        
        scale_group.setLayout(scale_layout)
        settings_layout.addWidget(scale_group)
        
        # Background Removal Settings
        bg_group = QGroupBox("Background Removal")
        bg_layout = QVBoxLayout()
        
        mode_layout = QHBoxLayout()
        mode_layout.addWidget(QLabel("Removal Mode:"))
        self.bg_mode_combo = QComboBox()
        self.bg_mode_combo.addItems(["Conservative (Safe)", "Aggressive", "None (Skip)"])
        self.bg_mode_combo.setToolTip(
            "Conservative: Carefully preserves edges & content\n"
            "Aggressive: Removes more background, may affect edges\n"
            "None: Skip background removal entirely"
        )
        self.bg_mode_combo.currentIndexChanged.connect(self.on_mode_changed)
        mode_layout.addWidget(self.bg_mode_combo)
        bg_layout.addLayout(mode_layout)
        
        tol_layout = QVBoxLayout()
        tol_layout.addWidget(QLabel("Background Tolerance:"))
        self.bg_tolerance_slider = QSlider(Qt.Orientation.Horizontal)
        self.bg_tolerance_slider.setRange(5, 50)
        self.bg_tolerance_slider.setTickInterval(5)
        self.bg_tolerance_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.bg_tolerance_slider.valueChanged.connect(self.update_tolerance_label)
        tol_layout.addWidget(self.bg_tolerance_slider)
        self.tolerance_label = QLabel("15")
        self.tolerance_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tol_layout.addWidget(self.tolerance_label)
        bg_layout.addLayout(tol_layout)
        
        edge_layout = QVBoxLayout()
        edge_layout.addWidget(QLabel("Edge Region Tolerance:"))
        self.edge_tolerance_slider = QSlider(Qt.Orientation.Horizontal)
        self.edge_tolerance_slider.setRange(10, 80)
        self.edge_tolerance_slider.setTickInterval(10)
        self.edge_tolerance_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.edge_tolerance_slider.valueChanged.connect(self.update_edge_tolerance_label)
        bg_layout.addLayout(edge_layout)
        self.edge_tolerance_label = QLabel("25")
        self.edge_tolerance_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        bg_layout.addWidget(self.edge_tolerance_label)
        
        bg_group.setLayout(bg_layout)
        settings_layout.addWidget(bg_group)
        
        # Content Preservation Settings
        preserve_group = QGroupBox("Content Preservation")
        preserve_layout = QVBoxLayout()
        
        self.preserve_lines_check = QCheckBox("Preserve Dark Lines/Outlines")
        self.preserve_lines_check.setChecked(True)
        self.preserve_lines_check.setToolTip("Protect dark outlines from being removed as background")
        preserve_layout.addWidget(self.preserve_lines_check)
        
        dark_layout = QHBoxLayout()
        dark_layout.addWidget(QLabel("Dark Line Threshold:"))
        self.dark_threshold_spin = QSpinBox()
        self.dark_threshold_spin.setRange(0, 150)
        self.dark_threshold_spin.setToolTip("RGB sum below this is considered 'dark' (0=black, 255=mid-gray)")
        dark_layout.addWidget(self.dark_threshold_spin)
        preserve_layout.addLayout(dark_layout)
        
        preserve_group.setLayout(preserve_layout)
        settings_layout.addWidget(preserve_group)
        
        # Canvas Padding Settings
        canvas_group = QGroupBox("Canvas Options")
        canvas_layout = QVBoxLayout()
        
        self.auto_trim_check = QCheckBox("Auto-Trim Transparency")
        self.auto_trim_check.setChecked(True)
        self.auto_trim_check.setToolTip("Crop to remove transparent borders")
        canvas_layout.addWidget(self.auto_trim_check)
        
        self.pad_canvas_check = QCheckBox("Pad Canvas to Multiple")
        self.pad_canvas_check.setChecked(True)
        self.pad_canvas_check.setToolTip("Expand canvas to nearest multiple and center artwork")
        self.pad_canvas_check.toggled.connect(self.on_pad_canvas_toggled)
        canvas_layout.addWidget(self.pad_canvas_check)
        
        multiple_layout = QHBoxLayout()
        multiple_layout.addWidget(QLabel("Canvas Multiple:"))
        self.canvas_multiple_spin = QSpinBox()
        self.canvas_multiple_spin.setRange(8, 128)
        self.canvas_multiple_spin.setSingleStep(8)
        self.canvas_multiple_spin.setSuffix(" px")
        self.canvas_multiple_spin.setToolTip("Pad canvas to nearest multiple of this value (e.g., 16 or 32)")
        multiple_layout.addWidget(self.canvas_multiple_spin)
        canvas_layout.addLayout(multiple_layout)
        
        canvas_group.setLayout(canvas_layout)
        settings_layout.addWidget(canvas_group)
        
        # Info text
        info_label = QLabel(
            "<i><small>"
            "This tool analyzes AI-generated images to detect their fake pixel grid "
            "and downscales them to the true intended pixel resolution."
            "</small></i>"
        )
        info_label.setWordWrap(True)
        settings_layout.addWidget(info_label)
        
        scroll.setWidget(settings_widget)
        right_layout.addWidget(scroll, stretch=1)
        
        # Fixed button at bottom (outside scroll area)
        self.downscale_btn = QPushButton("🔍 Downscale Images")
        self.downscale_btn.setMinimumHeight(45)
        self.downscale_btn.setStyleSheet("""
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
        self.downscale_btn.clicked.connect(self.downscale_images)
        right_layout.addWidget(self.downscale_btn)
        
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
        """Load global settings."""
        self.fine_tune_check.setChecked(self.settings.get("downscale/enable_fine_tune"))
        
        mode = self.settings.get("downscale/bg_removal_mode")
        mode_index = {"conservative": 0, "aggressive": 1, "none": 2}.get(mode, 0)
        self.bg_mode_combo.setCurrentIndex(mode_index)
        
        self.bg_tolerance_slider.setValue(self.settings.get("downscale/bg_tolerance"))
        self.edge_tolerance_slider.setValue(self.settings.get("downscale/bg_edge_tolerance"))
        self.preserve_lines_check.setChecked(self.settings.get("downscale/preserve_dark_lines"))
        self.dark_threshold_spin.setValue(self.settings.get("downscale/dark_line_threshold"))
        self.auto_trim_check.setChecked(self.settings.get("downscale/auto_trim"))
        
        self.pad_canvas_check.setChecked(self.settings.get("downscale/pad_canvas"))
        self.canvas_multiple_spin.setValue(self.settings.get("downscale/canvas_multiple"))
        
        self.update_tolerance_label()
        self.update_edge_tolerance_label()
        self.on_pad_canvas_toggled(self.pad_canvas_check.isChecked())
        
    def load_project_folder(self, project: Project, folder: Path):
        """Load project and folder."""
        self.current_project = project
        self.current_folder = folder
        
        # Load images
        self.image_list.load_images(folder)
        self.folder_info_label.setText(f"<i>{folder}</i>")
        
        # Load project-specific output settings
        if project:
            output_folder = self.project_manager.get_project_setting(
                project, "downscale/output_folder", "downscaled"
            )
            use_transform = self.project_manager.get_project_setting(
                project, "downscale/use_filename_transform", False
            )
            prefix = self.project_manager.get_project_setting(
                project, "downscale/filename_prefix", ""
            )
            suffix = self.project_manager.get_project_setting(
                project, "downscale/filename_suffix", ""
            )
            
            self.output_folder_edit.setText(output_folder)
            self.use_transform_check.setChecked(use_transform)
            self.prefix_edit.setText(prefix)
            self.suffix_edit.setText(suffix)
            
            self.on_use_transform_toggled(use_transform)
        
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
            "Select Folder for AI Downscale Tab",
            start_dir,
            QFileDialog.Option.ShowDirsOnly
        )
        
        if folder:
            folder_path = Path(folder)
            self.current_folder = folder_path
            
            # Reload images
            self.image_list.load_images(folder_path)
            self.folder_info_label.setText(f"<i>{folder_path}</i>")
            
            # Save this folder for the project
            self.project_manager.set_project_folder(self.current_project, "downscale", folder_path)
                
    def refresh_files(self):
        """Refresh file list while maintaining selection state."""
        if self.current_folder:
            self.image_list.load_images_preserve_selection(self.current_folder)
        
    def save_settings(self):
        """Save current settings."""
        self.settings.set("downscale/enable_fine_tune", self.fine_tune_check.isChecked())
        
        mode_map = ["conservative", "aggressive", "none"]
        self.settings.set("downscale/bg_removal_mode", mode_map[self.bg_mode_combo.currentIndex()])
        
        self.settings.set("downscale/bg_tolerance", self.bg_tolerance_slider.value())
        self.settings.set("downscale/bg_edge_tolerance", self.edge_tolerance_slider.value())
        self.settings.set("downscale/preserve_dark_lines", self.preserve_lines_check.isChecked())
        self.settings.set("downscale/dark_line_threshold", self.dark_threshold_spin.value())
        self.settings.set("downscale/auto_trim", self.auto_trim_check.isChecked())
        
        self.settings.set("downscale/pad_canvas", self.pad_canvas_check.isChecked())
        self.settings.set("downscale/canvas_multiple", self.canvas_multiple_spin.value())
        
        # Save project-specific output settings
        if self.current_project:
            self.project_manager.set_project_setting(
                self.current_project, "downscale/output_folder", self.output_folder_edit.text()
            )
            self.project_manager.set_project_setting(
                self.current_project, "downscale/use_filename_transform", self.use_transform_check.isChecked()
            )
            self.project_manager.set_project_setting(
                self.current_project, "downscale/filename_prefix", self.prefix_edit.text()
            )
            self.project_manager.set_project_setting(
                self.current_project, "downscale/filename_suffix", self.suffix_edit.text()
            )
        
    @Slot()
    def browse_output_folder(self):
        """Browse for output folder."""
        if not self.current_folder:
            QMessageBox.warning(self, "No Folder", "Please select a folder first.")
            return
        
        folder = QFileDialog.getExistingDirectory(
            self,
            "Select Output Folder",
            str(self.current_folder),
            QFileDialog.Option.ShowDirsOnly
        )
        
        if folder:
            folder_path = Path(folder)
            try:
                relative = folder_path.relative_to(self.current_folder)
                self.output_folder_edit.setText(str(relative))
            except ValueError:
                self.output_folder_edit.setText(str(folder_path))
        
    @Slot()
    def on_output_settings_changed(self):
        """Handle output settings change."""
        if self.current_project:
            self.save_settings()
        
    @Slot(bool)
    def on_use_transform_toggled(self, checked):
        """Enable/disable prefix/suffix fields."""
        self.prefix_edit.setEnabled(checked)
        self.suffix_edit.setEnabled(checked)
        
    @Slot()
    def smart_select(self):
        """Smart select - only select images that haven't been processed."""
        if not self.current_folder:
            QMessageBox.warning(self, "No Folder", "Please select a folder first.")
            return
        
        output_folder_name = self.output_folder_edit.text().strip() or "downscaled"
        output_dir = self.current_folder / output_folder_name
        
        use_transform = self.use_transform_check.isChecked()
        prefix = self.prefix_edit.text() if use_transform else ""
        suffix = self.suffix_edit.text() if use_transform else ""
        
        checked_count = 0
        unchecked_count = 0
        
        for i in range(self.image_list.count()):
            item = self.image_list.item(i)
            file_path = self.image_list.get_file_path(item)
            
            if file_path:
                stem = file_path.stem
                expected_name = f"{prefix}{stem}{suffix}.png"
                expected_path = output_dir / expected_name
                alt_path = output_dir / f"{stem}.png"
                
                if expected_path.exists() or alt_path.exists():
                    item.setCheckState(Qt.CheckState.Unchecked)
                    unchecked_count += 1
                else:
                    item.setCheckState(Qt.CheckState.Checked)
                    checked_count += 1
        
        msg = f"Smart Select: {checked_count} need processing, {unchecked_count} already done."
        self.window().statusBar().showMessage(msg, 5000)

    @Slot()
    def update_tolerance_label(self):
        self.tolerance_label.setText(str(self.bg_tolerance_slider.value()))
        
    @Slot()
    def update_edge_tolerance_label(self):
        self.edge_tolerance_label.setText(str(self.edge_tolerance_slider.value()))
        
    @Slot(int)
    def on_mode_changed(self, index):
        enabled = index != 2
        self.bg_tolerance_slider.setEnabled(enabled)
        self.edge_tolerance_slider.setEnabled(enabled)
        self.preserve_lines_check.setEnabled(enabled)
        self.dark_threshold_spin.setEnabled(enabled)
        
    @Slot(bool)
    def on_pad_canvas_toggled(self, checked):
        self.canvas_multiple_spin.setEnabled(checked)
        
    @Slot()
    def downscale_images(self):
        """Downscale selected images."""
        selected_files = self.image_list.get_selected_files()
        
        if not selected_files:
            QMessageBox.warning(self, "No Images Selected", "Please select at least one image.")
            return
            
        if not self.current_folder:
            QMessageBox.warning(self, "No Folder", "Please select a folder first.")
            return
            
        self.save_settings()
        
        output_folder_name = self.output_folder_edit.text().strip() or "downscaled"
        output_dir = self.current_folder / output_folder_name
        output_dir.mkdir(exist_ok=True)
        
        settings = self.settings.get_all_downscale_settings()
        settings['use_filename_transform'] = self.use_transform_check.isChecked()
        settings['filename_prefix'] = self.prefix_edit.text()
        settings['filename_suffix'] = self.suffix_edit.text()
        
        worker = DownscaleWorker(selected_files, output_dir, settings)
        worker.signals.progress.connect(self.on_progress)
        worker.signals.finished.connect(self.on_downscale_finished)
        worker.signals.error.connect(self.on_downscale_error)
        
        self.downscale_btn.setEnabled(False)
        self.downscale_btn.setText("Downscaling...")
        
        self.threadpool.start(worker)
        
    @Slot(tuple)
    def on_progress(self, progress_data):
        current, total, filename = progress_data
        self.downscale_btn.setText(f"Processing {current}/{total}...")
        
    @Slot(list)
    def on_downscale_finished(self, results):
        self.downscale_btn.setEnabled(True)
        self.downscale_btn.setText("🔍 Downscale Images")
        
        if not results:
            QMessageBox.warning(self, "No Results", "No images were successfully downscaled.")
            return
        
        summary_lines = []
        for result in results[:5]:
            name = result.get('filename', 'Unknown')
            orig_size = result.get('original_size', (0, 0))
            final_size = result.get('final_size', (0, 0))
            factor = result.get('scale_factor', 0)
            
            summary_lines.append(
                f"• {name}: {orig_size[0]}×{orig_size[1]} → "
                f"{final_size[0]}×{final_size[1]} ({factor:.1f}x)"
            )
        
        if len(results) > 5:
            summary_lines.append(f"... and {len(results) - 5} more")
        
        summary = "\n".join(summary_lines)
        output_folder_name = self.output_folder_edit.text().strip() or "downscaled"
        
        QMessageBox.information(
            self,
            "Downscaling Complete",
            f"Successfully downscaled {len(results)} images.\n\n"
            f"{summary}\n\n"
            f"Output: {self.current_folder / output_folder_name}"
        )
        
    @Slot(str)
    def on_downscale_error(self, error_msg):
        self.downscale_btn.setEnabled(True)
        self.downscale_btn.setText("🔍 Downscale Images")
        QMessageBox.critical(self, "Error", f"An error occurred:\n\n{error_msg}")