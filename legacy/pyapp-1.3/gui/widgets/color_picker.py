from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QPushButton, QSpinBox, QLabel, QColorDialog
)
from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QColor


class ColorPickerWidget(QWidget):
    """Custom color picker with RGBA spinboxes and color dialog."""
    
    colorChanged = Signal(tuple)  # (r, g, b, a)
    
    def __init__(self, initial_color=(255, 255, 255, 255), parent=None):
        super().__init__(parent)
        self._color = initial_color
        self.init_ui()
        self.set_color(initial_color)
        
    def init_ui(self):
        """Initialize the UI."""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)
        
        # Color preview button
        self.color_button = QPushButton()
        self.color_button.setFixedSize(50, 30)
        self.color_button.clicked.connect(self.open_color_dialog)
        self.color_button.setStyleSheet("QPushButton { border: 2px solid #555; }")
        layout.addWidget(self.color_button)
        
        # RGBA spinboxes
        self.spin_r = self._create_spinbox("R:")
        self.spin_g = self._create_spinbox("G:")
        self.spin_b = self._create_spinbox("B:")
        self.spin_a = self._create_spinbox("A:")
        
        for spin in [self.spin_r, self.spin_g, self.spin_b, self.spin_a]:
            spin.valueChanged.connect(self.on_spinbox_changed)
            
        layout.addWidget(QLabel("R:"))
        layout.addWidget(self.spin_r)
        layout.addWidget(QLabel("G:"))
        layout.addWidget(self.spin_g)
        layout.addWidget(QLabel("B:"))
        layout.addWidget(self.spin_b)
        layout.addWidget(QLabel("A:"))
        layout.addWidget(self.spin_a)
        layout.addStretch()
        
    def _create_spinbox(self, label):
        """Create a spinbox for color channel."""
        spin = QSpinBox()
        spin.setRange(0, 255)
        spin.setFixedWidth(60)
        return spin
        
    def set_color(self, color):
        """Set the current color (r, g, b, a)."""
        if len(color) == 3:
            color = (*color, 255)
            
        self._color = color
        r, g, b, a = color
        
        # Block signals to avoid recursion
        for spin, val in zip([self.spin_r, self.spin_g, self.spin_b, self.spin_a],
                            [r, g, b, a]):
            spin.blockSignals(True)
            spin.setValue(val)
            spin.blockSignals(False)
            
        # Update button color
        self.update_button_color()
        
    def get_color(self):
        """Get the current color as (r, g, b, a)."""
        return self._color
        
    def update_button_color(self):
        """Update the color preview button."""
        r, g, b, a = self._color
        self.color_button.setStyleSheet(
            f"QPushButton {{ background-color: rgba({r}, {g}, {b}, {a}); "
            f"border: 2px solid #555; }}"
        )
        
    def on_spinbox_changed(self):
        """Handle spinbox value changes."""
        r = self.spin_r.value()
        g = self.spin_g.value()
        b = self.spin_b.value()
        a = self.spin_a.value()
        
        self._color = (r, g, b, a)
        self.update_button_color()
        self.colorChanged.emit(self._color)
        
    def open_color_dialog(self):
        """Open the native color dialog."""
        r, g, b, a = self._color
        initial = QColor(r, g, b, a)
        
        color = QColorDialog.getColor(
            initial,
            self,
            "Select Color",
            QColorDialog.ColorDialogOption.ShowAlphaChannel
        )
        
        if color.isValid():
            rgba = (color.red(), color.green(), color.blue(), color.alpha())
            self.set_color(rgba)
            self.colorChanged.emit(self._color)