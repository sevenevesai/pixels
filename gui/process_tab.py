from pathlib import Path
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
    QLabel, QSpinBox, QDoubleSpinBox, QCheckBox,
    QComboBox, QLineEdit, QPushButton, QScrollArea,
    QMessageBox, QFileDialog
)
from PySide6.QtCore import Qt, QThreadPool, Slot

from gui.widgets.image_list_widget import ImageListWidget
from gui.widgets.color_picker import ColorPickerWidget
from core.workers import ProcessWorker
from core.settings_manager import SettingsManager
from core.project_manager import ProjectManager, Project


class ProcessTab(QWidget):
    """Tab for post-processing images."""

    def __init__(self, settings: SettingsManager, project_manager: ProjectManager, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.project_manager = project_manager
        self.threadpool = QThreadPool()
        self.current_folder = None
        self.current_project = None
        self._current_worker = None

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
        folder_layout.addWidget(QLabel("<b>Images to Process:</b>"))
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
        self.output_folder_edit.setPlaceholderText("processed")
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

        # Opacity Settings
        opacity_group = QGroupBox("Opacity Normalization")
        opacity_layout = QVBoxLayout()

        alpha_low_layout = QHBoxLayout()
        alpha_low_layout.addWidget(QLabel("Low Alpha Cutoff (→ 0):"))
        self.alpha_low_spin = QSpinBox()
        self.alpha_low_spin.setRange(0, 255)
        self.alpha_low_spin.setToolTip("Alpha values below this will be set to 0 (transparent)")
        alpha_low_layout.addWidget(self.alpha_low_spin)
        opacity_layout.addLayout(alpha_low_layout)

        alpha_high_layout = QHBoxLayout()
        alpha_high_layout.addWidget(QLabel("High Alpha Range (→ 255):"))
        self.alpha_high_min_spin = QSpinBox()
        self.alpha_high_min_spin.setRange(0, 255)
        self.alpha_high_min_spin.setSuffix(" - ")
        alpha_high_layout.addWidget(self.alpha_high_min_spin)
        self.alpha_high_max_spin = QSpinBox()
        self.alpha_high_max_spin.setRange(0, 255)
        self.alpha_high_max_spin.setToolTip("Alpha values in this range will be set to 255 (opaque)")
        alpha_high_layout.addWidget(self.alpha_high_max_spin)
        opacity_layout.addLayout(alpha_high_layout)

        opacity_group.setLayout(opacity_layout)
        settings_layout.addWidget(opacity_group)

        # Color Simplification Settings
        color_group = QGroupBox("Color Palette Simplification")
        color_layout = QVBoxLayout()

        self.enable_color_check = QCheckBox("Enable Color Merging")
        self.enable_color_check.setToolTip("Merge similar colors to reduce palette size")
        color_layout.addWidget(self.enable_color_check)

        threshold_layout = QHBoxLayout()
        threshold_layout.addWidget(QLabel("LAB Merge Threshold:"))
        self.lab_threshold_spin = QDoubleSpinBox()
        self.lab_threshold_spin.setRange(0.1, 50.0)
        self.lab_threshold_spin.setSingleStep(0.5)
        self.lab_threshold_spin.setDecimals(1)
        self.lab_threshold_spin.setToolTip("Lower = more similar colors, Higher = fewer merges (3-12 recommended)")
        threshold_layout.addWidget(self.lab_threshold_spin)
        color_layout.addLayout(threshold_layout)

        color_group.setLayout(color_layout)
        settings_layout.addWidget(color_group)

        # Outline Settings
        outline_group = QGroupBox("Outline Generation")
        outline_layout = QVBoxLayout()

        outline_layout.addWidget(QLabel("Outline Color (RGBA):"))
        self.outline_color_picker = ColorPickerWidget()
        outline_layout.addWidget(self.outline_color_picker)

        connectivity_layout = QHBoxLayout()
        connectivity_layout.addWidget(QLabel("Edge Detection:"))
        self.connectivity_combo = QComboBox()
        self.connectivity_combo.addItems(["4-way (Cardinal)", "8-way (Cardinal + Diagonal)"])
        self.connectivity_combo.setToolTip("4-way: only up/down/left/right, 8-way: includes diagonals")
        connectivity_layout.addWidget(self.connectivity_combo)
        outline_layout.addLayout(connectivity_layout)

        thickness_layout = QHBoxLayout()
        thickness_layout.addWidget(QLabel("Outline Thickness:"))
        self.thickness_spin = QSpinBox()
        self.thickness_spin.setRange(1, 10)
        self.thickness_spin.setToolTip("Thickness in pixels (1 = single pixel outline)")
        thickness_layout.addWidget(self.thickness_spin)
        outline_layout.addLayout(thickness_layout)

        edge_layout = QHBoxLayout()
        edge_layout.addWidget(QLabel("Transparent Cutoff:"))
        self.edge_cutoff_spin = QSpinBox()
        self.edge_cutoff_spin.setRange(0, 255)
        self.edge_cutoff_spin.setToolTip("Alpha values <= this are considered transparent for outline")
        edge_layout.addWidget(self.edge_cutoff_spin)
        outline_layout.addLayout(edge_layout)

        outline_group.setLayout(outline_layout)
        settings_layout.addWidget(outline_group)

        # Filename Processing
        filename_group = QGroupBox("Filename Processing")
        filename_layout = QVBoxLayout()

        prefix_layout = QHBoxLayout()
        prefix_layout.addWidget(QLabel("Strip Prefix:"))
        self.strip_prefix_edit = QLineEdit()
        self.strip_prefix_edit.setPlaceholderText("e.g., sprite_")
        self.strip_prefix_edit.setToolTip("Prefix to remove from filenames")
        prefix_layout.addWidget(self.strip_prefix_edit)
        filename_layout.addLayout(prefix_layout)

        filename_group.setLayout(filename_layout)
        settings_layout.addWidget(filename_group)

        scroll.setWidget(settings_widget)
        right_layout.addWidget(scroll, stretch=1)

        # Fixed button at bottom (outside scroll area)
        self.process_btn = QPushButton("🚀 Process Images")
        self.process_btn.setMinimumHeight(45)
        self.process_btn.setStyleSheet("""
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
        self.process_btn.clicked.connect(self.process_images)
        right_layout.addWidget(self.process_btn)

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
        self.alpha_low_spin.setValue(self.settings.get("process/alpha_low_cutoff"))
        self.alpha_high_min_spin.setValue(self.settings.get("process/alpha_high_min"))
        self.alpha_high_max_spin.setValue(self.settings.get("process/alpha_high_max"))
        self.enable_color_check.setChecked(self.settings.get("process/enable_color_simplify"))
        self.lab_threshold_spin.setValue(self.settings.get("process/lab_merge_threshold"))
        self.outline_color_picker.set_color(self.settings.get("process/outline_color"))
        self.edge_cutoff_spin.setValue(self.settings.get("process/edge_transparent_cutoff"))

        connectivity = self.settings.get("process/outline_connectivity")
        self.connectivity_combo.setCurrentIndex(0 if connectivity == 4 else 1)

        self.thickness_spin.setValue(self.settings.get("process/outline_thickness"))
        self.strip_prefix_edit.setText(self.settings.get("process/prefix_to_strip"))

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
                project, "process/output_folder", "processed"
            )
            use_transform = self.project_manager.get_project_setting(
                project, "process/use_filename_transform", False
            )
            prefix = self.project_manager.get_project_setting(
                project, "process/filename_prefix", ""
            )
            suffix = self.project_manager.get_project_setting(
                project, "process/filename_suffix", ""
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
            "Select Folder for Post-Process Tab",
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
            self.project_manager.set_project_folder(self.current_project, "process", folder_path)
            
    def refresh_files(self):
        """Refresh file list while maintaining selection state."""
        if self.current_folder:
            self.image_list.load_images_preserve_selection(self.current_folder)

    def save_settings(self):
        """Save current settings."""
        self.settings.set("process/alpha_low_cutoff", self.alpha_low_spin.value())
        self.settings.set("process/alpha_high_min", self.alpha_high_min_spin.value())
        self.settings.set("process/alpha_high_max", self.alpha_high_max_spin.value())
        self.settings.set("process/enable_color_simplify", self.enable_color_check.isChecked())
        self.settings.set("process/lab_merge_threshold", self.lab_threshold_spin.value())
        self.settings.set("process/outline_color", self.outline_color_picker.get_color())
        self.settings.set("process/edge_transparent_cutoff", self.edge_cutoff_spin.value())

        connectivity = 4 if self.connectivity_combo.currentIndex() == 0 else 8
        self.settings.set("process/outline_connectivity", connectivity)

        self.settings.set("process/outline_thickness", self.thickness_spin.value())
        self.settings.set("process/prefix_to_strip", self.strip_prefix_edit.text())
        
        # Save project-specific output settings
        if self.current_project:
            self.project_manager.set_project_setting(
                self.current_project, "process/output_folder", self.output_folder_edit.text()
            )
            self.project_manager.set_project_setting(
                self.current_project, "process/use_filename_transform", self.use_transform_check.isChecked()
            )
            self.project_manager.set_project_setting(
                self.current_project, "process/filename_prefix", self.prefix_edit.text()
            )
            self.project_manager.set_project_setting(
                self.current_project, "process/filename_suffix", self.suffix_edit.text()
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
        
        output_folder_name = self.output_folder_edit.text().strip() or "processed"
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

    def process_images(self):
        """Process selected images."""
        selected_files = self.image_list.get_selected_files()

        if not selected_files:
            QMessageBox.warning(self, "No Images Selected", "Please select at least one image.")
            return

        if not self.current_folder:
            QMessageBox.warning(self, "No Folder", "Please select a folder first.")
            return

        self.save_settings()

        output_folder_name = self.output_folder_edit.text().strip() or "processed"
        output_dir = self.current_folder / output_folder_name
        output_dir.mkdir(exist_ok=True)

        settings = {
            "alpha_low_cutoff": self.alpha_low_spin.value(),
            "alpha_high_min": self.alpha_high_min_spin.value(),
            "alpha_high_max": self.alpha_high_max_spin.value(),
            "enable_color_simplify": self.enable_color_check.isChecked(),
            "lab_merge_threshold": self.lab_threshold_spin.value(),
            "outline_color": self.outline_color_picker.get_color(),
            "edge_cutoff": self.edge_cutoff_spin.value(),
            "connectivity": 4 if self.connectivity_combo.currentIndex() == 0 else 8,
            "thickness": self.thickness_spin.value(),
            "prefix_to_strip": self.strip_prefix_edit.text(),
            "use_filename_transform": self.use_transform_check.isChecked(),
            "filename_prefix": self.prefix_edit.text(),
            "filename_suffix": self.suffix_edit.text(),
        }

        worker = ProcessWorker(selected_files, output_dir, settings)
        self._current_worker = worker

        worker.signals.progress.connect(self.on_progress)
        worker.signals.finished.connect(self.on_process_finished)
        worker.signals.error.connect(self.on_process_error)

        self.process_btn.setEnabled(False)
        self.process_btn.setText("Processing...")

        self.threadpool.start(worker)

    def on_progress(self, *args):
        if not args:
            return

        if len(args) == 1:
            try:
                percent = int(args[0])
            except Exception:
                return
            percent = max(0, min(100, percent))
            self.process_btn.setText(f"Processing… {percent}%")
            return

        current, total = args[0], args[1]
        filename = args[2] if len(args) > 2 else None
        try:
            percent = int((current / total) * 100) if total else 0
        except Exception:
            percent = 0
        percent = max(0, min(100, percent))

        label = f"Processing {current}/{total}…"
        if filename:
            label = f"Processing {current}/{total}…"
        self.process_btn.setText(label)

    def on_process_finished(self, *args):
        self.process_btn.setEnabled(True)
        self.process_btn.setText("🚀 Process Images")

        count = None
        if args:
            try:
                count = int(args[0])
            except Exception:
                count = None

        output_folder_name = self.output_folder_edit.text().strip() or "processed"
        out_dir = self.current_folder / output_folder_name if self.current_folder else None
        msg = (
            f"Successfully processed {count} images.\n\nOutput saved to: {out_dir}"
            if count is not None else
            f"Processing complete.\n\nOutput saved to: {out_dir}"
        )
        QMessageBox.information(self, "Processing Complete", msg)

        self._current_worker = None

    def on_process_error(self, error_msg):
        self.process_btn.setEnabled(True)
        self.process_btn.setText("🚀 Process Images")
        QMessageBox.critical(self, "Processing Error", f"An error occurred:\n\n{error_msg}")
        self._current_worker = None