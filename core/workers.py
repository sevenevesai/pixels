import traceback
from pathlib import Path
from typing import List
from PySide6.QtCore import QObject, QRunnable, Signal, Slot

from core.image_processor import process_image
from core.sprite_packer import pack_sprites
from core.pixel_downscaler import downscale_image


class WorkerSignals(QObject):
    """Signals for worker threads."""
    finished = Signal(object)
    error = Signal(str)
    progress = Signal(object)


class ProcessWorker(QRunnable):
    """Worker for processing images in background thread."""
    
    def __init__(self, files: List[Path], output_dir: Path, settings: dict):
        super().__init__()
        self.files = files
        self.output_dir = output_dir
        self.settings = settings
        self.signals = WorkerSignals()
        
    @Slot()
    def run(self):
        """Execute the processing."""
        try:
            total = len(self.files)
            processed = 0
            
            for i, file_path in enumerate(self.files, 1):
                # Emit progress with current/total/filename
                self.signals.progress.emit((i, total, file_path.name))
                
                # Determine output filename
                use_transform = self.settings.get('use_filename_transform', False)
                if use_transform:
                    prefix = self.settings.get('filename_prefix', '')
                    suffix = self.settings.get('filename_suffix', '')
                    output_name = f"{prefix}{file_path.stem}{suffix}.png"
                else:
                    output_name = file_path.name
                
                output_path = self.output_dir / output_name
                
                # Process image
                try:
                    process_image(file_path, output_path, self.settings)
                    processed += 1
                except Exception as e:
                    print(f"Error processing {file_path.name}: {e}")
                    traceback.print_exc()
                    
            self.signals.finished.emit(processed)
            
        except Exception as e:
            self.signals.error.emit(f"{str(e)}\n\n{traceback.format_exc()}")


class PackWorker(QRunnable):
    """Worker for packing sprites in background thread."""
    
    def __init__(self, files: List[Path], output_path: Path, settings: dict):
        super().__init__()
        self.files = files
        self.output_path = output_path
        self.settings = settings
        self.signals = WorkerSignals()
        
    @Slot()
    def run(self):
        """Execute the packing."""
        try:
            self.signals.progress.emit("Loading images...")
            
            # Pack sprites
            sheet_size = pack_sprites(
                self.files,
                self.output_path,
                self.settings
            )
            
            self.signals.finished.emit((str(self.output_path), sheet_size))
            
        except Exception as e:
            self.signals.error.emit(f"{str(e)}\n\n{traceback.format_exc()}")


class DownscaleWorker(QRunnable):
    """Worker for downscaling AI images in background thread."""
    
    def __init__(self, files: List[Path], output_dir: Path, settings: dict):
        super().__init__()
        self.files = files
        self.output_dir = output_dir
        self.settings = settings
        self.signals = WorkerSignals()
        
    @Slot()
    def run(self):
        """Execute the downscaling."""
        try:
            total = len(self.files)
            results = []
            
            for i, file_path in enumerate(self.files, 1):
                # Emit progress
                self.signals.progress.emit((i, total, file_path.name))
                
                # Determine output filename
                use_transform = self.settings.get('use_filename_transform', False)
                if use_transform:
                    prefix = self.settings.get('filename_prefix', '')
                    suffix = self.settings.get('filename_suffix', '')
                    output_name = f"{prefix}{file_path.stem}{suffix}.png"
                else:
                    output_name = f"{file_path.stem}.png"
                
                output_path = self.output_dir / output_name
                
                # Downscale image
                try:
                    result_info = downscale_image(file_path, output_path, self.settings)
                    results.append(result_info)
                except Exception as e:
                    print(f"Error downscaling {file_path.name}: {e}")
                    traceback.print_exc()
                    
            self.signals.finished.emit(results)
            
        except Exception as e:
            self.signals.error.emit(f"{str(e)}\n\n{traceback.format_exc()}")