from pathlib import Path
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTabWidget, QPushButton, QFileDialog, QMessageBox,
    QStatusBar, QProgressBar, QLabel, QMenu, QInputDialog,
    QToolBar, QFrame
)
from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QAction, QDesktopServices
from PySide6.QtCore import QUrl

from gui.downscale_tab import DownscaleTab
from gui.process_tab import ProcessTab
from gui.pack_tab import PackTab
from gui.license_dialog import LicenseDialog
from core.settings_manager import SettingsManager
from core.project_manager import ProjectManager, Project
from core.license_manager import LicenseManager


class MainWindow(QMainWindow):
    """Main application window with tabbed interface."""
    
    def __init__(self):
        super().__init__()
        self.settings = SettingsManager()
        self.project_manager = ProjectManager(self.settings.settings)
        self.license_manager = LicenseManager(self.settings)
        self.current_project = None
        
        self.init_ui()
        self.restore_geometry()
        
        # Load last project if exists
        last_project = self.project_manager.get_current_project()
        if last_project:
            self.load_project(last_project)
        
    def init_ui(self):
        """Initialize the user interface."""
        self.setMinimumSize(1200, 750)
        
        # Update window title based on license
        self.update_window_title()
        
        # Create central widget and layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)
        
        # Project toolbar
        project_bar = self.create_project_toolbar()
        main_layout.addLayout(project_bar)
        
        # License banner (if not licensed)
        if not self.license_manager.is_licensed():
            self.license_banner = self.create_license_banner()
            main_layout.addWidget(self.license_banner)
        
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
    
    def update_window_title(self):
        """Update window title based on license status."""
        base_title = "Pixels Toolkit"
        if not self.license_manager.is_licensed():
            self.setWindowTitle(f"{base_title} - Non-commercial use only")
        else:
            self.setWindowTitle(base_title)
    
    def create_license_banner(self) -> QWidget:
        """Create license notification banner."""
        banner = QFrame()
        banner.setStyleSheet("""
            QFrame {
                background-color: #5294E2;
                border-bottom: 1px solid #4080D0;
                padding: 5px;
            }
        """)
        
        banner_layout = QHBoxLayout(banner)
        banner_layout.setContentsMargins(10, 5, 10, 5)
        
        icon_label = QLabel("ℹ️")
        icon_label.setStyleSheet("font-size: 16px;")
        banner_layout.addWidget(icon_label)
        
        text_label = QLabel(
            'Using Pixels Toolkit commercially? Please '
            '<a href="https://seveneves.ai/pixels#purchase" style="color: #FFFFFF; font-weight: bold; text-decoration: underline;">purchase a license</a>. '
            'Thanks!'
        )
        text_label.setStyleSheet("color: white; font-weight: normal;")
        text_label.setOpenExternalLinks(True)
        banner_layout.addWidget(text_label)
        
        banner_layout.addStretch()
        
        # Close button
        close_btn = QPushButton("✕")
        close_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: white;
                border: none;
                font-size: 18px;
                font-weight: bold;
                padding: 0px 5px;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 0.2);
                border-radius: 3px;
            }
        """)
        close_btn.setFixedSize(30, 30)
        close_btn.setToolTip("Dismiss banner")
        close_btn.clicked.connect(lambda: banner.setVisible(False))
        banner_layout.addWidget(close_btn)
        
        return banner

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
        
        # License actions
        purchase_action = QAction("&Purchase License...", self)
        purchase_action.triggered.connect(self.open_purchase_page)
        help_menu.addAction(purchase_action)
        
        enter_license_action = QAction("&Enter License Key...", self)
        enter_license_action.triggered.connect(self.show_license_dialog)
        help_menu.addAction(enter_license_action)
        
        help_menu.addSeparator()
        
        donate_action = QAction("❤️ &Donate", self)
        donate_action.triggered.connect(self.open_donate_page)
        help_menu.addAction(donate_action)
        
        help_menu.addSeparator()
        
        about_action = QAction("&About", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)
    
    @Slot()
    def open_purchase_page(self):
        """Open purchase page in browser."""
        QDesktopServices.openUrl(QUrl("https://seveneves.ai/pixels#purchase"))
    
    @Slot()
    def open_donate_page(self):
        """Open donation page in browser."""
        QDesktopServices.openUrl(QUrl("https://www.paypal.com/donate/?hosted_button_id=XJUQUE78JATMN"))
    
    @Slot()
    def show_license_dialog(self):
        """Show license entry dialog."""
        dialog = LicenseDialog(self.license_manager, self)
        if dialog.exec():
            # Refresh UI after license change
            self.update_window_title()
            
            # Remove banner if now licensed
            if self.license_manager.is_licensed() and hasattr(self, 'license_banner'):
                self.license_banner.setVisible(False)
            
            # Show banner if license removed
            elif not self.license_manager.is_licensed() and hasattr(self, 'license_banner'):
                self.license_banner.setVisible(True)
        
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
            "About Pixels Toolkit",
            "<h2>Pixels Toolkit v1.0.0</h2>"
            "<p>Image processing and sprite sheet packing tool.</p>"
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
            "<p><a href='https://seveneves.ai/pixels'>seveneves.ai/pixels</a></p>"
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