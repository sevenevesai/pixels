// V2 One-Off Panel - Two-section layout: Downscale → Post-Process
import { useState, useCallback, useEffect, useRef, WheelEvent, MouseEvent } from 'react';
import { invoke } from '@tauri-apps/api/core';
import { save } from '@tauri-apps/plugin-dialog';
import { SourceImage, ProcessingSettings, OutlineDetectionResult, DownscaleState, rgbaToHex } from './types';

// Min/max zoom levels for scroll zoom (pixel-perfect increments)
const ZOOM_LEVELS = [1, 2, 3, 4, 5, 6, 8, 10, 12, 16];
const MIN_ZOOM = ZOOM_LEVELS[0];
const MAX_ZOOM = ZOOM_LEVELS[ZOOM_LEVELS.length - 1];

// Get next zoom level in direction
function getNextZoomLevel(current: number, direction: 'in' | 'out'): number {
  if (direction === 'in') {
    const next = ZOOM_LEVELS.find(z => z > current);
    return next ?? MAX_ZOOM;
  } else {
    const reversed = [...ZOOM_LEVELS].reverse();
    const next = reversed.find(z => z < current);
    return next ?? MIN_ZOOM;
  }
}

// Pannable, zoomable preview image component
interface PannablePreviewProps {
  src: string | null;
  alt: string;
  zoom: number;
  onZoomChange: (zoom: number) => void;
  showGrid: boolean;
  loading?: boolean;
  loadingText?: string;
  placeholder?: string;
}

function PannablePreview({
  src,
  alt,
  zoom,
  onZoomChange,
  showGrid,
  loading,
  loadingText = 'Generating...',
  placeholder = 'Preview'
}: PannablePreviewProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [isPanning, setIsPanning] = useState(false);
  const panStartRef = useRef({ x: 0, y: 0, panX: 0, panY: 0 });

  // Reset pan when image changes
  useEffect(() => {
    setPan({ x: 0, y: 0 });
  }, [src]);

  // Handle mouse wheel for zoom
  const handleWheel = useCallback((e: WheelEvent<HTMLDivElement>) => {
    e.preventDefault();
    const direction = e.deltaY < 0 ? 'in' : 'out';
    const newZoom = getNextZoomLevel(zoom, direction);
    if (newZoom !== zoom) {
      onZoomChange(newZoom);
    }
  }, [zoom, onZoomChange]);

  // Handle mouse down for pan start
  const handleMouseDown = useCallback((e: MouseEvent<HTMLDivElement>) => {
    if (e.button !== 0) return; // Only left click
    e.preventDefault();
    setIsPanning(true);
    panStartRef.current = {
      x: e.clientX,
      y: e.clientY,
      panX: pan.x,
      panY: pan.y,
    };
  }, [pan]);

  // Handle mouse move for panning
  const handleMouseMove = useCallback((e: MouseEvent<HTMLDivElement>) => {
    if (!isPanning) return;
    const dx = e.clientX - panStartRef.current.x;
    const dy = e.clientY - panStartRef.current.y;
    setPan({
      x: panStartRef.current.panX + dx,
      y: panStartRef.current.panY + dy,
    });
  }, [isPanning]);

  // Handle mouse up to stop panning
  const handleMouseUp = useCallback(() => {
    setIsPanning(false);
  }, []);

  // Handle mouse leave to stop panning
  const handleMouseLeave = useCallback(() => {
    setIsPanning(false);
  }, []);

  // Double-click to reset pan
  const handleDoubleClick = useCallback(() => {
    setPan({ x: 0, y: 0 });
  }, []);

  return (
    <div
      ref={containerRef}
      className={`oneoff-preview-image pannable ${showGrid ? 'show-grid' : ''} ${isPanning ? 'panning' : ''}`}
      onWheel={handleWheel}
      onMouseDown={handleMouseDown}
      onMouseMove={handleMouseMove}
      onMouseUp={handleMouseUp}
      onMouseLeave={handleMouseLeave}
      onDoubleClick={handleDoubleClick}
      title="Scroll to zoom, drag to pan, double-click to reset"
    >
      {loading ? (
        <div className="preview-loading">
          <div className="loading-spinner" />
          <span>{loadingText}</span>
        </div>
      ) : src ? (
        <img
          src={src}
          alt={alt}
          style={{
            transform: `translate(${pan.x}px, ${pan.y}px) scale(${zoom})`,
            cursor: isPanning ? 'grabbing' : 'grab',
          }}
          draggable={false}
        />
      ) : (
        <span className="no-image">{placeholder}</span>
      )}
    </div>
  );
}

interface OneOffPanelProps {
  source: SourceImage;
  settings: ProcessingSettings;
  onUpdateSettings: (updates: Partial<ProcessingSettings>) => void;
  previewData: string | null;
  previewLoading: boolean;
  originalThumbnail?: string;
  outlineWarning: OutlineDetectionResult | null;
  onDismissWarning: () => void;
  onSaveAs: (outputPath: string) => Promise<{ success: boolean; error?: unknown }>;
  onClose: () => void;
  isProcessing: boolean;
  progressMessage: string;
}

// Debounce delay for downscale preview
const DOWNSCALE_PREVIEW_DEBOUNCE_MS = 200;

export function OneOffPanel({
  source,
  settings,
  onUpdateSettings,
  previewData,
  previewLoading,
  originalThumbnail,
  outlineWarning,
  onDismissWarning,
  onSaveAs,
  onClose,
  isProcessing,
  progressMessage,
}: OneOffPanelProps) {
  const [zoom, setZoom] = useState(4);
  const [showGrid, setShowGrid] = useState(false);

  // Downscale state
  const [downscaleState, setDownscaleState] = useState<DownscaleState>(() => ({
    originalWidth: source.detectedScale ? Math.round((source.detectedScale || 1) * (source.detectedScale || 1)) : 0,
    originalHeight: 0,
    detectedScale: source.detectedScale || 1,
    detectedWidth: 0,
    detectedHeight: 0,
    targetWidth: 0,
    targetHeight: 0,
    autoTrim: true,
    confirmed: source.detectedType !== 'ai_upscaled', // Auto-confirm if not AI upscaled
    previewLoading: false,
    previewData: null,
  }));

  const downscalePreviewTimerRef = useRef<number | null>(null);

  // Initialize downscale state from source detection
  useEffect(() => {
    if (source.detectedType === 'ai_upscaled' && source.detectedScale && source.detectedScale > 1) {
      // Get dimensions from ScaleDetectionResult (stored when image was opened)
      // We need to invoke detect_scale_command to get the full info
      invoke<{
        detected_scale: number;
        dimensions: [number, number];
        estimated_native_size: [number, number];
      }>('detect_scale_command', { inputPath: source.fullPath })
        .then(result => {
          setDownscaleState(prev => ({
            ...prev,
            originalWidth: result.dimensions[0],
            originalHeight: result.dimensions[1],
            detectedScale: result.detected_scale,
            detectedWidth: result.estimated_native_size[0],
            detectedHeight: result.estimated_native_size[1],
            targetWidth: result.estimated_native_size[0],
            targetHeight: result.estimated_native_size[1],
            confirmed: false, // Need confirmation for AI upscaled
          }));
        })
        .catch(err => console.error('Failed to get scale detection:', err));
    } else {
      // Native pixel art - mark as confirmed (skip downscale)
      setDownscaleState(prev => ({
        ...prev,
        confirmed: true,
      }));
    }
  }, [source.fullPath, source.detectedType, source.detectedScale]);

  // Generate downscale preview
  const generateDownscalePreview = useCallback(async (width: number, height: number, autoTrim: boolean) => {
    if (width <= 0 || height <= 0) return;

    setDownscaleState(prev => ({ ...prev, previewLoading: true }));

    try {
      const pngBytes = await invoke<number[]>('downscale_preview_command', {
        inputPath: source.fullPath,
        targetWidth: width,
        targetHeight: height,
        autoTrim,
      });

      const uint8Array = new Uint8Array(pngBytes);
      const base64 = btoa(
        uint8Array.reduce((data, byte) => data + String.fromCharCode(byte), '')
      );

      setDownscaleState(prev => ({
        ...prev,
        previewData: `data:image/png;base64,${base64}`,
        previewLoading: false,
      }));
    } catch (err) {
      console.error('Downscale preview failed:', err);
      setDownscaleState(prev => ({ ...prev, previewLoading: false }));
    }
  }, [source.fullPath]);

  // Debounced downscale preview
  const requestDownscalePreview = useCallback((width: number, height: number, autoTrim: boolean) => {
    if (downscalePreviewTimerRef.current) {
      clearTimeout(downscalePreviewTimerRef.current);
    }

    downscalePreviewTimerRef.current = window.setTimeout(() => {
      generateDownscalePreview(width, height, autoTrim);
    }, DOWNSCALE_PREVIEW_DEBOUNCE_MS);
  }, [generateDownscalePreview]);

  // Update downscale dimensions and trigger preview
  const updateDownscaleDimension = useCallback((dimension: 'width' | 'height', value: number) => {
    setDownscaleState(prev => {
      const newState = dimension === 'width'
        ? { ...prev, targetWidth: value }
        : { ...prev, targetHeight: value };

      // Trigger preview
      requestDownscalePreview(newState.targetWidth, newState.targetHeight, newState.autoTrim);

      return newState;
    });
  }, [requestDownscalePreview]);

  // Update auto-trim and trigger preview
  const updateAutoTrim = useCallback((autoTrim: boolean) => {
    setDownscaleState(prev => {
      requestDownscalePreview(prev.targetWidth, prev.targetHeight, autoTrim);
      return { ...prev, autoTrim };
    });
  }, [requestDownscalePreview]);

  // Confirm downscale step
  const confirmDownscale = useCallback(() => {
    // Update settings with confirmed dimensions
    onUpdateSettings({
      downscaleEnabled: true,
      downscaleAutoTrim: downscaleState.autoTrim,
      downscaleTargetWidth: downscaleState.targetWidth,
      downscaleTargetHeight: downscaleState.targetHeight,
    });

    setDownscaleState(prev => ({ ...prev, confirmed: true }));
  }, [downscaleState, onUpdateSettings]);

  // Skip downscale (use original)
  const skipDownscale = useCallback(() => {
    onUpdateSettings({
      downscaleEnabled: false,
      downscaleTargetWidth: null,
      downscaleTargetHeight: null,
    });

    setDownscaleState(prev => ({ ...prev, confirmed: true }));
  }, [onUpdateSettings]);

  // Go back to downscale step
  const editDownscale = useCallback(() => {
    setDownscaleState(prev => ({ ...prev, confirmed: false }));
  }, []);

  // Reset to detected dimensions
  const resetToDetected = useCallback(() => {
    setDownscaleState(prev => {
      requestDownscalePreview(prev.detectedWidth, prev.detectedHeight, prev.autoTrim);
      return {
        ...prev,
        targetWidth: prev.detectedWidth,
        targetHeight: prev.detectedHeight,
      };
    });
  }, [requestDownscalePreview]);

  // Generate default output path with _processed suffix
  const getDefaultOutputPath = useCallback(() => {
    const lastDot = source.fullPath.lastIndexOf('.');
    if (lastDot === -1) {
      return `${source.fullPath}_processed`;
    }
    return `${source.fullPath.substring(0, lastDot)}_processed${source.fullPath.substring(lastDot)}`;
  }, [source.fullPath]);

  // Handle Save button
  const handleSave = useCallback(async () => {
    const defaultPath = getDefaultOutputPath();
    const outputPath = await save({
      defaultPath,
      filters: [{
        name: 'PNG Image',
        extensions: ['png'],
      }],
    });

    if (outputPath) {
      await onSaveAs(outputPath);
    }
  }, [getDefaultOutputPath, onSaveAs]);

  // Handle Save & Close button
  const handleSaveAndClose = useCallback(async () => {
    const defaultPath = getDefaultOutputPath();
    const outputPath = await save({
      defaultPath,
      filters: [{
        name: 'PNG Image',
        extensions: ['png'],
      }],
    });

    if (outputPath) {
      const result = await onSaveAs(outputPath);
      if (result.success) {
        setTimeout(onClose, 500); // Brief delay to show success message
      }
    }
  }, [getDefaultOutputPath, onSaveAs, onClose]);

  // Trigger initial downscale preview when dimensions are set
  useEffect(() => {
    if (downscaleState.targetWidth > 0 && downscaleState.targetHeight > 0 && !downscaleState.confirmed) {
      requestDownscalePreview(downscaleState.targetWidth, downscaleState.targetHeight, downscaleState.autoTrim);
    }

    return () => {
      if (downscalePreviewTimerRef.current) {
        clearTimeout(downscalePreviewTimerRef.current);
      }
    };
  }, [downscaleState.targetWidth, downscaleState.targetHeight, downscaleState.confirmed, downscaleState.autoTrim, requestDownscalePreview]);

  const needsDownscale = source.detectedType === 'ai_upscaled' && source.detectedScale && source.detectedScale > 1;

  return (
    <div className="oneoff-panel">
      {/* Header */}
      <header className="oneoff-header">
        <h1 className="oneoff-title">Pixels Toolkit - Quick Process</h1>
        <button onClick={onClose} className="btn-close" title="Close">
          Close
        </button>
      </header>

      {/* Main Content */}
      <div className="oneoff-content">
        {/* Step 1: Downscale (if needed and not confirmed) */}
        {needsDownscale && !downscaleState.confirmed && (
          <div className="oneoff-section downscale-section">
            <div className="section-header">
              <h2 className="section-title-large">Step 1: Downscale</h2>
              <span className="section-badge ai">AI Upscaled {source.detectedScale}x Detected</span>
            </div>

            <div className="oneoff-preview-row">
              {/* Original */}
              <div className="oneoff-preview-pane">
                <span className="pane-label">Original</span>
                <PannablePreview
                  src={originalThumbnail || null}
                  alt="Original"
                  zoom={Math.min(zoom, 2)} // Cap zoom for large original
                  onZoomChange={setZoom}
                  showGrid={showGrid}
                  loading={!originalThumbnail}
                  loadingText="Loading..."
                  placeholder="Loading..."
                />
                <span className="oneoff-dimensions">
                  {downscaleState.originalWidth} × {downscaleState.originalHeight}
                </span>
              </div>

              {/* Arrow */}
              <div className="oneoff-arrow">
                <span>➡</span>
              </div>

              {/* Downscaled Preview */}
              <div className="oneoff-preview-pane">
                <span className="pane-label">Downscaled Preview</span>
                <PannablePreview
                  src={downscaleState.previewData}
                  alt="Downscaled Preview"
                  zoom={zoom}
                  onZoomChange={setZoom}
                  showGrid={showGrid}
                  loading={downscaleState.previewLoading}
                />
                <span className="oneoff-dimensions">
                  {downscaleState.targetWidth} × {downscaleState.targetHeight}
                </span>
              </div>
            </div>

            {/* Dimension Controls */}
            <div className="downscale-controls">
              <div className="dimension-inputs">
                <div className="dimension-input">
                  <label>Width</label>
                  <div className="input-with-buttons">
                    <button
                      className="btn-tiny"
                      onClick={() => updateDownscaleDimension('width', downscaleState.targetWidth - 1)}
                      disabled={downscaleState.targetWidth <= 1}
                    >-</button>
                    <input
                      type="number"
                      value={downscaleState.targetWidth}
                      onChange={(e) => updateDownscaleDimension('width', parseInt(e.target.value) || 0)}
                      min={1}
                    />
                    <button
                      className="btn-tiny"
                      onClick={() => updateDownscaleDimension('width', downscaleState.targetWidth + 1)}
                    >+</button>
                  </div>
                </div>

                <span className="dimension-x">×</span>

                <div className="dimension-input">
                  <label>Height</label>
                  <div className="input-with-buttons">
                    <button
                      className="btn-tiny"
                      onClick={() => updateDownscaleDimension('height', downscaleState.targetHeight - 1)}
                      disabled={downscaleState.targetHeight <= 1}
                    >-</button>
                    <input
                      type="number"
                      value={downscaleState.targetHeight}
                      onChange={(e) => updateDownscaleDimension('height', parseInt(e.target.value) || 0)}
                      min={1}
                    />
                    <button
                      className="btn-tiny"
                      onClick={() => updateDownscaleDimension('height', downscaleState.targetHeight + 1)}
                    >+</button>
                  </div>
                </div>

                <button
                  className="btn-tiny reset-btn"
                  onClick={resetToDetected}
                  title="Reset to auto-detected dimensions"
                >
                  Reset
                </button>
              </div>

              <div className="downscale-options">
                <label className="setting-toggle small">
                  <input
                    type="checkbox"
                    checked={downscaleState.autoTrim}
                    onChange={(e) => updateAutoTrim(e.target.checked)}
                  />
                  <span>Auto-trim transparent borders</span>
                </label>
              </div>

              {/* Zoom Controls */}
              <div className="oneoff-zoom-controls">
                <span className="zoom-label">{zoom}x</span>
                <button className={`btn-tiny ${zoom === 1 ? 'active' : ''}`} onClick={() => setZoom(1)}>1x</button>
                <button className={`btn-tiny ${zoom === 4 ? 'active' : ''}`} onClick={() => setZoom(4)}>4x</button>
                <button className={`btn-tiny ${zoom === 8 ? 'active' : ''}`} onClick={() => setZoom(8)}>8x</button>
                <span className="control-divider">|</span>
                <button className={`btn-tiny ${showGrid ? 'active' : ''}`} onClick={() => setShowGrid(!showGrid)}>Grid</button>
                <span className="zoom-hint">(scroll to zoom, drag to pan)</span>
              </div>
            </div>

            {/* Downscale Actions */}
            <div className="section-actions">
              <button className="btn" onClick={skipDownscale}>
                Skip (Keep Original Size)
              </button>
              <button
                className="btn-primary"
                onClick={confirmDownscale}
                disabled={downscaleState.targetWidth <= 0 || downscaleState.targetHeight <= 0}
              >
                Confirm Dimensions →
              </button>
            </div>
          </div>
        )}

        {/* Step 2: Post-Process (or only step if no downscale needed) */}
        {(downscaleState.confirmed || !needsDownscale) && (
          <div className="oneoff-section postprocess-section">
            <div className="section-header">
              <h2 className="section-title-large">
                {needsDownscale ? 'Step 2: Post-Process' : 'Process Settings'}
              </h2>
              {needsDownscale && downscaleState.confirmed && settings.downscaleEnabled && (
                <button className="btn-tiny" onClick={editDownscale}>
                  ← Edit Downscale
                </button>
              )}
            </div>

            {/* Preview Row */}
            <div className="oneoff-preview-row">
              {/* Source (after downscale if applicable) */}
              <div className="oneoff-preview-pane">
                <span className="pane-label">
                  {settings.downscaleEnabled ? 'After Downscale' : 'Original'}
                </span>
                <PannablePreview
                  src={settings.downscaleEnabled && downscaleState.previewData
                    ? downscaleState.previewData
                    : originalThumbnail || null}
                  alt={settings.downscaleEnabled ? 'Downscaled' : 'Original'}
                  zoom={zoom}
                  onZoomChange={setZoom}
                  showGrid={showGrid}
                  loading={!originalThumbnail}
                  loadingText="Loading..."
                />
                <span className="oneoff-dimensions">
                  {settings.downscaleEnabled && settings.downscaleTargetWidth && settings.downscaleTargetHeight
                    ? `${settings.downscaleTargetWidth} × ${settings.downscaleTargetHeight}`
                    : source.name}
                </span>
              </div>

              {/* Arrow */}
              <div className="oneoff-arrow">
                <span>➡</span>
              </div>

              {/* Processed Preview */}
              <div className="oneoff-preview-pane">
                <span className="pane-label">Processed</span>
                <PannablePreview
                  src={previewData}
                  alt="Preview"
                  zoom={zoom}
                  onZoomChange={setZoom}
                  showGrid={showGrid}
                  loading={previewLoading}
                />
                <span className="oneoff-dimensions">Final Output</span>
              </div>
            </div>

            {/* Zoom Controls */}
            <div className="oneoff-zoom-controls">
              <span className="zoom-label">{zoom}x</span>
              <button className={`btn-tiny ${zoom === 1 ? 'active' : ''}`} onClick={() => setZoom(1)}>1x</button>
              <button className={`btn-tiny ${zoom === 4 ? 'active' : ''}`} onClick={() => setZoom(4)}>4x</button>
              <button className={`btn-tiny ${zoom === 8 ? 'active' : ''}`} onClick={() => setZoom(8)}>8x</button>
              <span className="control-divider">|</span>
              <button className={`btn-tiny ${showGrid ? 'active' : ''}`} onClick={() => setShowGrid(!showGrid)}>Grid</button>
              <span className="zoom-hint">(scroll to zoom, drag to pan)</span>
            </div>

            {/* Settings Bar */}
            <div className="oneoff-settings">
              {/* Outline Warning */}
              {outlineWarning && settings.outlineEnabled && (
                <div className="oneoff-warning">
                  <span className="warning-icon">⚠</span>
                  <span>Outline detected (confidence: {(outlineWarning.confidence * 100).toFixed(0)}%)</span>
                  {outlineWarning.outline_color && (
                    <span
                      className="color-swatch"
                      style={{ backgroundColor: rgbaToHex(outlineWarning.outline_color) }}
                    />
                  )}
                  <button className="btn-tiny" onClick={onDismissWarning}>
                    Dismiss
                  </button>
                </div>
              )}

              {/* Settings Controls */}
              <div className="oneoff-settings-row">
                {/* Color Merge */}
                <div className="oneoff-setting">
                  <label className="setting-toggle">
                    <input
                      type="checkbox"
                      checked={settings.mergeEnabled}
                      onChange={(e) => onUpdateSettings({ mergeEnabled: e.target.checked })}
                      disabled={isProcessing}
                    />
                    <span>Color Merge</span>
                  </label>
                  {settings.mergeEnabled && (
                    <div className="setting-control inline">
                      <input
                        type="range"
                        min="1"
                        max="15"
                        step="0.5"
                        value={settings.mergeThreshold}
                        onChange={(e) => onUpdateSettings({ mergeThreshold: parseFloat(e.target.value) })}
                        disabled={isProcessing}
                      />
                      <span className="setting-value">{settings.mergeThreshold.toFixed(1)}</span>
                    </div>
                  )}
                </div>

                {/* Outline */}
                <div className="oneoff-setting">
                  <label className="setting-toggle">
                    <input
                      type="checkbox"
                      checked={settings.outlineEnabled}
                      onChange={(e) => onUpdateSettings({ outlineEnabled: e.target.checked })}
                      disabled={isProcessing}
                    />
                    <span>Outline</span>
                    {outlineWarning && settings.outlineEnabled && (
                      <span className="setting-warning">⚠</span>
                    )}
                  </label>
                  {settings.outlineEnabled && (
                    <>
                      <div className="setting-control inline color-control">
                        <input
                          type="color"
                          value={settings.outlineColor}
                          onChange={(e) => onUpdateSettings({ outlineColor: e.target.value })}
                          disabled={isProcessing}
                        />
                        <span className="color-hex">{settings.outlineColor}</span>
                      </div>
                      <div className="setting-control inline">
                        <input
                          type="range"
                          min="1"
                          max="5"
                          step="1"
                          value={settings.outlineThickness}
                          onChange={(e) => onUpdateSettings({ outlineThickness: parseInt(e.target.value) })}
                          disabled={isProcessing}
                        />
                        <span className="setting-value">{settings.outlineThickness}px</span>
                      </div>
                    </>
                  )}
                </div>
              </div>
            </div>

            {/* Footer with Save buttons */}
            <div className="oneoff-footer">
              {/* Progress message */}
              {progressMessage && (
                <div className="oneoff-progress">
                  {isProcessing && <span className="loading-spinner-small" />}
                  <span>{progressMessage}</span>
                </div>
              )}

              <div className="oneoff-actions">
                <button
                  className="btn"
                  onClick={handleSave}
                  disabled={isProcessing || !previewData}
                >
                  Save
                </button>
                <button
                  className="btn-primary"
                  onClick={handleSaveAndClose}
                  disabled={isProcessing || !previewData}
                >
                  Save & Close
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
