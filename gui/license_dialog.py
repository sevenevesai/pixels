"""License key entry dialog."""
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QTextEdit, QPushButton, QMessageBox
)
from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QFont

from core.license_manager import LicenseManager


class LicenseDialog(QDialog):
    """Dialog for entering and validating license key."""
    
    def __init__(self, license_manager: LicenseManager, parent=None):
        super().__init__(parent)
        self.license_manager = license_manager
        self.setWindowTitle("Enter License Key")
        self.setModal(True)
        self.setMinimumWidth(500)
        
        self.init_ui()
        
    def init_ui(self):
        """Initialize UI."""
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        
        # Title
        title = QLabel("Enter Your License Key")
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title.setFont(title_font)
        layout.addWidget(title)
        
        # Instructions
        instructions = QLabel(
            "Please paste your license key below.\n"
            "You should have received this via email after purchase."
        )
        instructions.setWordWrap(True)
        layout.addWidget(instructions)
        
        # Current license info
        is_valid, email, expiry = self.license_manager.get_license_info()
        if is_valid:
            current_label = QLabel(f"<b>Current License:</b><br>Email: {email}<br>Expiry: {expiry}")
            current_label.setStyleSheet("color: #5294E2; padding: 10px; background: #f0f0f0; border-radius: 5px;")
            layout.addWidget(current_label)
        
        # License key input
        layout.addWidget(QLabel("License Key:"))
        self.key_input = QTextEdit()
        self.key_input.setPlaceholderText("Paste your license key here...")
        self.key_input.setMaximumHeight(100)
        layout.addWidget(self.key_input)
        
        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        self.validate_btn = QPushButton("Activate License")
        self.validate_btn.setStyleSheet("""
            QPushButton {
                background-color: #5294E2;
                color: white;
                padding: 8px 20px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #6BA4F2;
            }
        """)
        self.validate_btn.clicked.connect(self.activate_license)
        button_layout.addWidget(self.validate_btn)
        
        if is_valid:
            self.remove_btn = QPushButton("Remove License")
            self.remove_btn.clicked.connect(self.remove_license)
            button_layout.addWidget(self.remove_btn)
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)
        
        layout.addLayout(button_layout)
        
        # Purchase link
        purchase_label = QLabel(
            '<a href="https://seveneves.ai/pixels#purchase">Don\'t have a license? Purchase here</a>'
        )
        purchase_label.setOpenExternalLinks(True)
        purchase_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(purchase_label)
        
    @Slot()
    def activate_license(self):
        """Activate the entered license key."""
        key = self.key_input.toPlainText().strip()
        success, message = self.license_manager.set_license_key(key)
        
        if success:
            QMessageBox.information(self, "Success", message)
            self.accept()
        else:
            QMessageBox.warning(self, "Invalid License", message)
    
    @Slot()
    def remove_license(self):
        """Remove current license."""
        reply = QMessageBox.question(
            self,
            "Remove License",
            "Are you sure you want to remove your license?\n"
            "The app will revert to non-commercial use only.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            self.license_manager.remove_license()
            QMessageBox.information(self, "License Removed", "Your license has been removed.")
            self.accept()