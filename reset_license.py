#!/usr/bin/env python3
"""Reset license activation for testing."""
from PySide6.QtCore import QSettings

# Initialize settings with same app info as main app
app_settings = QSettings("SpriteTools", "Pixels Toolkit")

# Clear license key
app_settings.setValue("license/key", "")
app_settings.sync()

print("✅ License key cleared!")
print("App will now show as non-commercial use.")