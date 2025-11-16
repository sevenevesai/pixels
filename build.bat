### **File 14: `build.bat` - Windows Build Script**
```batch
@echo off
echo Building Sprite Toolkit...
echo.

REM Clean previous builds
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

REM Build with PyInstaller
pyinstaller sprite_toolkit.spec

echo.
echo Build complete! Executable is in the dist folder.
pause