#!/usr/bin/env python3
"""
Sprite Toolkit - Image Processing & Sprite Sheet Packer
A professional desktop application for batch image processing and sprite sheet creation.
"""
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon

from gui.main_window import MainWindow

# Application metadata
APP_NAME = "Sprite Toolkit"
APP_VERSION = "1.0.0"
ORG_NAME = "SpriteTools"
ORG_DOMAIN = "spritetools.local"


def apply_dark_theme(app: QApplication) -> None:
    """
    Apply a dark theme using pyqtdarktheme (0.1.x API).
    Falls back to a Fusion dark palette if pyqtdarktheme isn't available.
    """
    try:
        # NOTE: package is installed as 'pyqtdarktheme' but imported as 'qdarktheme'
        import qdarktheme  # provided by pyqtdarktheme==0.1.x

        # Old API: returns a QSS string; apply to the app.
        app.setStyle("Fusion")
        app.setStyleSheet(qdarktheme.load_stylesheet("dark"))
    except Exception:
        # Fallback: Fusion dark palette
        from PySide6.QtGui import QPalette, QColor

        app.setStyle("Fusion")
        pal = QPalette()
        pal.setColor(QPalette.Window, QColor(53, 53, 53))
        pal.setColor(QPalette.WindowText, QColor(220, 220, 220))
        pal.setColor(QPalette.Base, QColor(35, 35, 35))
        pal.setColor(QPalette.AlternateBase, QColor(53, 53, 53))
        pal.setColor(QPalette.ToolTipBase, QColor(220, 220, 220))
        pal.setColor(QPalette.ToolTipText, QColor(220, 220, 220))
        pal.setColor(QPalette.Text, QColor(220, 220, 220))
        pal.setColor(QPalette.Button, QColor(53, 53, 53))
        pal.setColor(QPalette.ButtonText, QColor(220, 220, 220))
        pal.setColor(QPalette.Highlight, QColor(90, 110, 200))
        pal.setColor(QPalette.HighlightedText, QColor(0, 0, 0))
        app.setPalette(pal)


def main():
    # Enable High DPI scaling (Qt 6)
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    # Create application
    app = QApplication(sys.argv)

    # Set application metadata for QSettings
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setOrganizationName(ORG_NAME)
    app.setOrganizationDomain(ORG_DOMAIN)

    # Apply dark theme (pyqtdarktheme 0.1.x compatible)
    apply_dark_theme(app)

    # Set application icon if exists
    icon_path = Path(__file__).parent / "assets" / "icon.png"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    # Create and show main window
    window = MainWindow()
    window.show()

    # Run application
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
