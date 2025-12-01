from pathlib import Path
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTabWidget, QPushButton, QFileDialog, QMessageBox,
    QStatusBar, QProgressBar, QLabel, QMenu, QInputDialog,
    QToolBar
)
from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QAction

from gui.downscale_tab import DownscaleTab
from gui.process_tab import ProcessTab
from gui.pack_tab import PackTab
from core.settings_manager import SettingsManager
from core.project_manager import ProjectManager, Project


class MainWindow(QMainWindow):
    """Main application window with tabbed interface."""
    
    def __init__(self):
        super().__init__()
        self.settings = SettingsManager()
        self.project_manager = ProjectManager(self.settings.settings)
        self.current_project = None
        
        self.init_ui()
        self.restore_geometry()
        
        # Load last project if exists
        last_project = self.project_manager.get_current_project()
        if last_project:
            self.load_project(last_project)
        
    def init_ui(self):
        """Initialize the user interface."""
        self.setWindowTitle("Sprite Toolkit")
        self.setMinimumSize(1200, 750)
        
        # Create central widget and layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)
        
        # Project toolbar
        project_bar = self.create_project_toolbar()
        main_layout.addLayout(project_bar)
        
        # Create tab widget
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.currentChanged.connect(self.on_tab_changed)
        
        # Create tabs
        self.downscale_tab = DownscaleTab(self.settings, self.project_manager)
        self.process_tab = ProcessTab(self.settings, self.project_manager)
        self.pack_tab = PackTab(self.settings, self.project_manager)
        
        self.tabs.addTab(self.downscale_tab, "🔍 AI Downscale")
        self.tabs.addTab(self.process_tab, "🎨 Post-Process")
        self.tabs.addTab(self.pack_tab, "📦 Pack Sprites")
        
        main_layout.addWidget(self.tabs)
        
        # Create status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready - Add or select a project to begin")
        
        # Progress bar (hidden by default)
        self.progress_bar = QProgressBar()
        self.progress_bar.setMaximumWidth(200)
        self.progress_bar.setVisible(False)
        self.status_bar.addPermanentWidget(self.progress_bar)
        
        # Create menu bar
        self.create_menus()
        
    def create_project_toolbar(self) -> QHBoxLayout:
        """Create project management toolbar."""
        layout = QHBoxLayout()
        
        # Add Project button
        self.add_project_btn = QPushButton("+ Add Project")
        self.add_project_btn.setToolTip("Add a new project directory")
        self.add_project_btn.clicked.connect(self.add_project)
        layout.addWidget(self.add_project_btn)
        
        # Projects dropdown button
        self.projects_btn = QPushButton("Projects ▼")
        self.projects_btn.setToolTip("Select or manage projects")
        self.projects_btn.clicked.connect(self.show_projects_menu)
        layout.addWidget(self.projects_btn)
        
        # Current project label
        layout.addWidget(QLabel("<b>Current Project:</b>"))
        self.current_project_label = QLabel("<i>None</i>")
        self.current_project_label.setStyleSheet("color: #888;")
        layout.addWidget(self.current_project_label)
        
        layout.addStretch()
        
        # Refresh button
        self.refresh_btn = QPushButton("🔄 Refresh")
        self.refresh_btn.setToolTip("Refresh current tab's file list")
        self.refresh_btn.clicked.connect(self.refresh_current_tab)
        layout.addWidget(self.refresh_btn)
        
        return layout
        
    @Slot()
    def add_project(self):
        """Add a new project."""
        # Ask for project name
        name, ok = QInputDialog.getText(
            self,
            "Add Project",
            "Project Name:",
            text="My Project"
        )
        
        if not ok or not name.strip():
            return
        
        # Ask for project directory
        folder = QFileDialog.getExistingDirectory(
            self,
            "Select Project Directory",
            str(Path.home()),
            QFileDialog.Option.ShowDirsOnly
        )
        
        if not folder:
            return
        
        project_path = Path(folder)
        
        # Add project
        project = self.project_manager.add_project(name.strip(), project_path)
        
        # Load it
        self.load_project(project)
        
        QMessageBox.information(
            self,
            "Project Added",
            f"Project '{project.name}' has been added successfully!"
        )
        
    @Slot()
    def show_projects_menu(self):
        """Show projects dropdown menu."""
        menu = QMenu(self)
        
        projects = self.project_manager.get_projects()
        
        if not projects:
            no_projects = menu.addAction("No projects yet")
            no_projects.setEnabled(False)
        else:
            for project in projects:
                # Create action for this project
                project_action = menu.addAction(f"📁 {project.name}")
                project_action.triggered.connect(lambda checked, p=project: self.load_project(p))
                
                # Add delete action as sub-menu
                delete_action = menu.addAction(f"   ✕ Delete")
                delete_action.triggered.connect(lambda checked, p=project: self.delete_project(p))
                menu.addSeparator()
        
        # Show menu below button
        menu.exec(self.projects_btn.mapToGlobal(self.projects_btn.rect().bottomLeft()))
        
    def load_project(self, project: Project):
        """Load a project and its settings."""
        self.current_project = project
        self.project_manager.set_current_project(project)
        
        # Update UI
        self.current_project_label.setText(f"<b>{project.name}</b>")
        self.current_project_label.setStyleSheet("color: #333;")
        
        # Load folders for each tab (or default to project path)
        downscale_folder = self.project_manager.get_project_folder(project, "downscale")
        process_folder = self.project_manager.get_project_folder(project, "process")
        pack_folder = self.project_manager.get_project_folder(project, "pack")
        
        #print(f"[Project Load] Downscale folder: {downscale_folder}")  # Debug
        #print(f"[Project Load] Process folder: {process_folder}")      # Debug
        #print(f"[Project Load] Pack folder: {pack_folder}")            # Debug
        
        # Default to project path if no folder set
        if not downscale_folder:
            downscale_folder = project.path
            self.project_manager.set_project_folder(project, "downscale", project.path)
        if not process_folder:
            process_folder = project.path
            self.project_manager.set_project_folder(project, "process", project.path)
        if not pack_folder:
            pack_folder = project.path
            self.project_manager.set_project_folder(project, "pack", project.path)
        
        # Load into tabs
        self.downscale_tab.load_project_folder(project, downscale_folder)
        self.process_tab.load_project_folder(project, process_folder)
        self.pack_tab.load_project_folder(project, pack_folder)
        
        self.status_bar.showMessage(f"Loaded project: {project.name}", 3000)
        
    def delete_project(self, project: Project):
        """Delete a project."""
        reply = QMessageBox.question(
            self,
            "Delete Project",
            f"Are you sure you want to remove project '{project.name}'?\n\n"
            "This will not delete any files, only remove it from the project list.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            self.project_manager.remove_project(project)
            
            # If current project was deleted, clear it
            if self.current_project and self.current_project.path == project.path:
                self.current_project = None
                self.current_project_label.setText("<i>None</i>")
                self.current_project_label.setStyleSheet("color: #888;")
                
            self.status_bar.showMessage(f"Removed project: {project.name}", 3000)
        
    @Slot()
    def refresh_current_tab(self):
        """Refresh the current tab's file list."""
        current_tab = self.tabs.currentWidget()
        
        if hasattr(current_tab, 'refresh_files'):
            current_tab.refresh_files()
            self.status_bar.showMessage("File list refreshed", 2000)
        
    @Slot(int)
    def on_tab_changed(self, index):
        """Handle tab change - could auto-refresh here."""
        # Optional: auto-refresh when switching tabs
        pass
        
    def create_menus(self):
        """Create application menus."""
        menubar = self.menuBar()
        
        # File menu
        file_menu = menubar.addMenu("&File")
        
        add_project_action = QAction("&Add Project...", self)
        add_project_action.setShortcut("Ctrl+N")
        add_project_action.triggered.connect(self.add_project)
        file_menu.addAction(add_project_action)
        
        file_menu.addSeparator()
        
        exit_action = QAction("E&xit", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # Settings menu
        settings_menu = menubar.addMenu("&Settings")
        
        reset_action = QAction("&Reset to Defaults", self)
        reset_action.triggered.connect(self.reset_settings)
        settings_menu.addAction(reset_action)
        
        # Help menu
        help_menu = menubar.addMenu("&Help")
        
        about_action = QAction("&About", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)
        
    @Slot()
    def reset_settings(self):
        """Reset all settings to defaults."""
        reply = QMessageBox.question(
            self,
            "Reset Settings",
            "Are you sure you want to reset all settings to defaults?\n\n"
            "Projects will not be removed.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            # Don't reset projects
            projects_backup = self.project_manager.get_projects()
            current_backup = self.project_manager.get_current_project()
            
            self.settings.reset()
            
            # Restore projects
            self.project_manager.save_projects(projects_backup)
            if current_backup:
                self.project_manager.set_current_project(current_backup)
            
            # Reload tabs
            if self.current_project:
                self.load_project(self.current_project)
            
            QMessageBox.information(
                self,
                "Settings Reset",
                "All settings have been reset to defaults.\nProjects were preserved."
            )
            
    @Slot()
    def show_about(self):
        """Show about dialog."""
        QMessageBox.about(
            self,
            "About Sprite Toolkit",
            "<h2>Sprite Toolkit v1.1.0</h2>"
            "<p>Professional image processing and sprite sheet packing tool.</p>"
            "<p><b>Features:</b></p>"
            "<ul>"
            "<li>Project-based workflow for easy management</li>"
            "<li>AI image downscaling to true pixel resolution</li>"
            "<li>Batch post-processing with color palette reduction</li>"
            "<li>Configurable outline generation</li>"
            "<li>Sprite sheet packing with metadata export</li>"
            "<li>Smart selection based on existing output</li>"
            "</ul>"
            "<p>Built with PySide6 and Python.</p>"
        )
        
    def restore_geometry(self):
        """Restore window geometry from settings."""
        geometry = self.settings.get("window_geometry")
        if geometry:
            self.restoreGeometry(geometry)
            
        state = self.settings.get("window_state")
        if state:
            self.restoreState(state)
            
    def closeEvent(self, event):
        """Save settings before closing."""
        self.settings.set("window_geometry", self.saveGeometry())
        self.settings.set("window_state", self.saveState())
        event.accept()