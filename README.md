# Sprite Toolkit

Desktop application for batch image processing and sprite sheet creation.

## Features

### Post-Processing
- **Opacity Normalization**: Clean up semi-transparent pixels
- **Color Palette Reduction**: Merge similar colors using LAB color space
- **Outline Generation**: Add configurable outlines with adjustable thickness
- **Batch Processing**: Process multiple images simultaneously

### Sprite Packing
- **Flexible Layout**: Configurable max width with automatic wrapping
- **Smart Sorting**: Sort by height, width, name, or none
- **Customizable Spacing**: Adjust item, row, and border padding
- **Metadata Export**: Generate JSON with sprite positions
- **Transparent Backgrounds**: Full RGBA support

## Installation

### From Source

1. Install Python 3.8 or higher
2. Install dependencies:
```bash
pip install -r requirements.txt