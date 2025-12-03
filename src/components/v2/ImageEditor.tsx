// V2 Image Editor - Universal image editing view
// Works for both quick-edit (single file, no lineage) and project mode (with lineage)
import { useState, useCallback, useEffect, useRef, WheelEvent, MouseEvent } from 'react';
import { invoke } from '@tauri-apps/api/core';
import { save } from '@tauri-apps/plugin-dialog';
import { ProcessingSettings, OutlineDetectionResult, ScaleDetectionResult, hexToRgba, rgbaToHex } from './types';

// Zoom levels for pixel-perfect rendering
const ZOOM_LEVELS = [1, 2, 3, 4, 5, 6, 8, 10, 12, 16];

function getNextZoomLevel(current: number, direction: 'in' | 'out'): number {
  if (direction === 'in') {
    return ZOOM_LEVELS.find(z => z > current) ?? ZOOM_LEVELS[ZOOM_LEVELS.length - 1];
  } else {
    return [...ZOOM_LEVELS].reverse().find(z => z < current) ?? ZOOM_LEVELS[0];
  }
}

// Pannable preview component
interface PannablePreviewProps {
  src: string | null;
  alt: string;
  zoom: number;
  onZoomChange: (zoom: number) => void;
  showGrid: boolean;
  loading?: boolean;
  /** Key that triggers pan reset - only reset when this changes (e.g., new image file) */
  resetKey?: string;
}

function PannablePreview({ src, alt, zoom, onZoomChange, showGrid, loading, resetKey }: PannablePreviewProps) {
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [isPanning, setIsPanning] = useState(false);
  const panStartRef = useRef({ x: 0, y: 0, panX: 0, panY: 0 });

  // Only reset pan when resetKey changes (new image), not on every src update
  useEffect(() => {
    setPan({ x: 0, y: 0 });
  }, [resetKey]);

  const handleWheel = useCallback((e: WheelEvent<HTMLDivElement>) => {
    e.preventDefault();
    const direction = e.deltaY < 0 ? 'in' : 'out';
    const newZoom = getNextZoomLevel(zoom, direction);
    if (newZoom !== zoom) onZoomChange(newZoom);
  }, [zoom, onZoomChange]);

  const handleMouseDown = useCallback((e: MouseEvent<HTMLDivElement>) => {
    if (e.button !== 0) return;
    e.preventDefault();
    setIsPanning(true);
    panStartRef.current = { x: e.clientX, y: e.clientY, panX: pan.x, panY: pan.y };
  }, [pan]);

  const handleMouseMove = useCallback((e: MouseEvent<HTMLDivElement>) => {
    if (!isPanning) return;
    setPan({
      x: panStartRef.current.panX + (e.clientX - panStartRef.current.x),
      y: panStartRef.current.panY + (e.clientY - panStartRef.current.y),
    });
  }, [isPanning]);

  const handleMouseUp = useCallback(() => setIsPanning(false), []);
  const handleMouseLeave = useCallback(() => setIsPanning(false), []);
  const handleDoubleClick = useCallback(() => setPan({ x: 0, y: 0 }), []);

  return (
    <div
      className={`preview-canvas ${showGrid ? 'show-grid' : ''} ${isPanning ? 'panning' : ''}`}
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
          <span>Loading...</span>
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
        <span className="no-image">No preview</span>
      )}
    </div>
  );
}

// Main props
interface ImageEditorProps {
  /** Full path to the image file */
  imagePath: string;
  /** Image filename */
  imageName: string;
  /** Original image as base64 data URL (loaded by parent) */
  originalImage: string | null;
  /** Whether this is a quick-edit (no project/lineage) */
  quickEdit: boolean;
  /** Workspace path for lineage (folder mode only) */
  workspacePath?: string;
  /** Called when user closes this editor */
  onClose: () => void;
  /** Called when image is saved (to refresh thumbnail) */
  onSaved?: () => void;
}

interface DownscaleState {
  originalWidth: number;
  originalHeight: number;
  detectedScale: number;
  targetWidth: number;
  targetHeight: number;
  autoTrim: boolean;
  confirmed: boolean;
  previewData: string | null;
  previewLoading: boolean;
}

const DEFAULT_SETTINGS: ProcessingSettings = {
  downscaleEnabled: true,
  downscaleAutoTrim: true,
  downscaleTargetWidth: null,
  downscaleTargetHeight: null,
  alphaEnabled: true,
  alphaLowCutoff: 200,
  alphaHighMin: 200,
  mergeEnabled: true,
  mergeThreshold: 3.0,
  outlineEnabled: true,
  outlineColor: '#110602',
  outlineThickness: 1,
};

export function ImageEditor({
  imagePath,
  imageName,
  originalImage,
  quickEdit,
  workspacePath,
  onClose,
  onSaved,
}: ImageEditorProps) {
  // UI state
  const [zoom, setZoom] = useState(4);
  const [showGrid, setShowGrid] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  const [statusMessage, setStatusMessage] = useState('');

  // Detection state
  const [isAiUpscaled, setIsAiUpscaled] = useState<boolean | null>(null);
  const [detectionLoading, setDetectionLoading] = useState(true);

  // Downscale state (Step 1)
  const [downscaleState, setDownscaleState] = useState<DownscaleState>({
    originalWidth: 0,
    originalHeight: 0,
    detectedScale: 1,
    targetWidth: 0,
    targetHeight: 0,
    autoTrim: true,
    confirmed: false,
    previewData: null,
    previewLoading: false,
  });

  // Post-process settings (Step 2)
  const [settings, setSettings] = useState<ProcessingSettings>(DEFAULT_SETTINGS);

  // Preview state
  const [previewData, setPreviewData] = useState<string | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [outlineWarning, setOutlineWarning] = useState<OutlineDetectionResult | null>(null);

  // Debounce refs
  const downscaleTimerRef = useRef<number | null>(null);
  const previewTimerRef = useRef<number | null>(null);

  // Detect scale on mount
  useEffect(() => {
    let cancelled = false;

    async function detectScale() {
      setDetectionLoading(true);
      try {
        const result = await invoke<ScaleDetectionResult>('detect_scale_command', {
          inputPath: imagePath,
        });

        if (cancelled) return;

        const isUpscaled = result.is_ai_upscaled && result.detected_scale > 1;
        setIsAiUpscaled(isUpscaled);

        if (isUpscaled) {
          setDownscaleState({
            originalWidth: result.dimensions[0],
            originalHeight: result.dimensions[1],
            detectedScale: result.detected_scale,
            targetWidth: result.estimated_native_size[0],
            targetHeight: result.estimated_native_size[1],
            autoTrim: true,
            confirmed: false,
            previewData: null,
            previewLoading: false,
          });
        } else {
          // Not AI upscaled, skip downscale step
          setDownscaleState(prev => ({ ...prev, confirmed: true }));
        }
      } catch (err) {
        console.error('Scale detection failed:', err);
        setIsAiUpscaled(false);
        setDownscaleState(prev => ({ ...prev, confirmed: true }));
      } finally {
        if (!cancelled) setDetectionLoading(false);
      }
    }

    detectScale();
    return () => { cancelled = true; };
  }, [imagePath]);

  // Generate downscale preview (debounced)
  const generateDownscalePreview = useCallback(async () => {
    const { targetWidth, targetHeight, autoTrim } = downscaleState;
    if (targetWidth <= 0 || targetHeight <= 0) return;

    setDownscaleState(prev => ({ ...prev, previewLoading: true }));

    try {
      const pngBytes = await invoke<number[]>('downscale_preview_command', {
        inputPath: imagePath,
        targetWidth,
        targetHeight,
        autoTrim,
      });

      const uint8Array = new Uint8Array(pngBytes);
      const base64 = btoa(uint8Array.reduce((data, byte) => data + String.fromCharCode(byte), ''));

      setDownscaleState(prev => ({
        ...prev,
        previewData: `data:image/png;base64,${base64}`,
        previewLoading: false,
      }));
    } catch (err) {
      console.error('Downscale preview failed:', err);
      setDownscaleState(prev => ({ ...prev, previewLoading: false }));
    }
  }, [imagePath, downscaleState.targetWidth, downscaleState.targetHeight, downscaleState.autoTrim]);

  // Trigger downscale preview when dimensions change
  useEffect(() => {
    if (!downscaleState.confirmed && downscaleState.targetWidth > 0 && downscaleState.targetHeight > 0) {
      if (downscaleTimerRef.current) clearTimeout(downscaleTimerRef.current);
      downscaleTimerRef.current = window.setTimeout(generateDownscalePreview, 200);
    }
    return () => {
      if (downscaleTimerRef.current) clearTimeout(downscaleTimerRef.current);
    };
  }, [downscaleState.targetWidth, downscaleState.targetHeight, downscaleState.autoTrim, downscaleState.confirmed, generateDownscalePreview]);

  // Generate post-process preview (debounced)
  const generatePreview = useCallback(async () => {
    setPreviewLoading(true);
    try {
      const [r, g, b, a] = hexToRgba(settings.outlineColor);

      const downscaleSettings = (isAiUpscaled && settings.downscaleEnabled) ? {
        enabled: true,
        auto_trim: downscaleState.autoTrim,
        target_width: downscaleState.targetWidth || undefined,
        target_height: downscaleState.targetHeight || undefined,
      } : null;

      const alphaSettings = settings.alphaEnabled ? {
        low_cutoff: settings.alphaLowCutoff,
        high_min: settings.alphaHighMin,
        high_max: 255,
      } : null;

      const mergeSettings = settings.mergeEnabled ? {
        threshold: settings.mergeThreshold,
      } : null;

      const outlineSettings = settings.outlineEnabled ? {
        color: [r, g, b, a],
        connectivity: 'four',
        thickness: settings.outlineThickness,
        edge_transparent_cutoff: 0,
      } : null;

      const pngBytes = await invoke<number[]>('generate_preview_command', {
        inputPath: imagePath,
        downscaleSettings,
        alphaSettings,
        mergeSettings,
        outlineSettings,
      });

      const uint8Array = new Uint8Array(pngBytes);
      const base64 = btoa(uint8Array.reduce((data, byte) => data + String.fromCharCode(byte), ''));
      setPreviewData(`data:image/png;base64,${base64}`);
    } catch (err) {
      console.error('Preview generation failed:', err);
      setPreviewData(null);
    } finally {
      setPreviewLoading(false);
    }
  }, [imagePath, settings, isAiUpscaled, downscaleState]);

  // Trigger preview when settings change (only after downscale confirmed)
  useEffect(() => {
    if (downscaleState.confirmed) {
      if (previewTimerRef.current) clearTimeout(previewTimerRef.current);
      previewTimerRef.current = window.setTimeout(generatePreview, 300);
    }
    return () => {
      if (previewTimerRef.current) clearTimeout(previewTimerRef.current);
    };
  }, [settings, downscaleState.confirmed, generatePreview]);

  // Detect outline when outline is enabled
  useEffect(() => {
    if (settings.outlineEnabled && downscaleState.confirmed) {
      invoke<OutlineDetectionResult>('detect_outline_command', { inputPath: imagePath })
        .then(result => setOutlineWarning(result.has_outline ? result : null))
        .catch(() => setOutlineWarning(null));
    } else {
      setOutlineWarning(null);
    }
  }, [imagePath, settings.outlineEnabled, downscaleState.confirmed]);

  // Handlers
  const updateDimension = useCallback((dim: 'width' | 'height', value: number) => {
    setDownscaleState(prev => ({
      ...prev,
      [dim === 'width' ? 'targetWidth' : 'targetHeight']: value,
    }));
  }, []);

  const resetToDetected = useCallback(() => {
    setDownscaleState(prev => ({
      ...prev,
      targetWidth: Math.round(prev.originalWidth / prev.detectedScale),
      targetHeight: Math.round(prev.originalHeight / prev.detectedScale),
    }));
  }, []);

  const confirmDownscale = useCallback(() => {
    setSettings(prev => ({
      ...prev,
      downscaleEnabled: true,
      downscaleTargetWidth: downscaleState.targetWidth,
      downscaleTargetHeight: downscaleState.targetHeight,
      downscaleAutoTrim: downscaleState.autoTrim,
    }));
    setDownscaleState(prev => ({ ...prev, confirmed: true }));
  }, [downscaleState]);

  const skipDownscale = useCallback(() => {
    setSettings(prev => ({ ...prev, downscaleEnabled: false }));
    setDownscaleState(prev => ({ ...prev, confirmed: true }));
  }, []);

  const editDownscale = useCallback(() => {
    setDownscaleState(prev => ({ ...prev, confirmed: false }));
    setPreviewData(null);
  }, []);

  const updateSettings = useCallback((updates: Partial<ProcessingSettings>) => {
    setSettings(prev => ({ ...prev, ...updates }));
  }, []);

  // Save handlers
  const handleSave = useCallback(async (saveAs: boolean) => {
    let outputPath = imagePath;
    const isOverwriting = !saveAs;

    if (saveAs) {
      const lastDot = imagePath.lastIndexOf('.');
      const defaultPath = lastDot === -1
        ? `${imagePath}_processed`
        : `${imagePath.substring(0, lastDot)}_processed${imagePath.substring(lastDot)}`;

      const selected = await save({
        defaultPath,
        filters: [{ name: 'PNG Image', extensions: ['png'] }],
      });

      if (!selected) return;
      outputPath = selected;
    }

    setIsProcessing(true);
    setStatusMessage('Saving...');

    try {
      // Backup original before overwriting (in folder mode with workspace)
      if (isOverwriting && workspacePath && !quickEdit) {
        setStatusMessage('Backing up original...');
        const relativePath = imagePath.replace(workspacePath, '').replace(/^[\\\/]/, '');
        try {
          await invoke('backup_original_command', {
            workspacePath,
            relativePath,
          });
        } catch (err) {
          console.warn('Backup failed (non-critical):', err);
        }
      }

      setStatusMessage('Processing...');

      const [r, g, b, a] = hexToRgba(settings.outlineColor);

      const downscaleSettings = (isAiUpscaled && settings.downscaleEnabled) ? {
        enabled: true,
        auto_trim: settings.downscaleAutoTrim,
        target_width: settings.downscaleTargetWidth || undefined,
        target_height: settings.downscaleTargetHeight || undefined,
      } : null;

      const alphaSettings = settings.alphaEnabled ? {
        low_cutoff: settings.alphaLowCutoff,
        high_min: settings.alphaHighMin,
        high_max: 255,
      } : null;

      const mergeSettings = settings.mergeEnabled ? {
        threshold: settings.mergeThreshold,
      } : null;

      const outlineSettings = settings.outlineEnabled ? {
        color: [r, g, b, a],
        connectivity: 'four',
        thickness: settings.outlineThickness,
        edge_transparent_cutoff: 0,
      } : null;

      await invoke('process_and_save_command', {
        inputPath: imagePath,
        outputPath,
        downscaleSettings,
        alphaSettings,
        mergeSettings,
        outlineSettings,
      });

      // Record version in lineage (folder mode only)
      if (workspacePath && !quickEdit) {
        const relativePath = imagePath.replace(workspacePath, '').replace(/^[\\\/]/, '');
        try {
          await invoke('add_version_command', {
            workspacePath,
            relativePath,
            version: {
              id: `v${Date.now()}`, // Simple unique ID
              version_type: isAiUpscaled && settings.downscaleEnabled ? 'downscaled' : 'post_processed',
              cache_path: null, // Saved in place
              parent: 'v1', // Parent is original
              post_process_settings: {
                alpha_enabled: settings.alphaEnabled,
                alpha_low_cutoff: settings.alphaEnabled ? settings.alphaLowCutoff : null,
                alpha_high_min: settings.alphaEnabled ? settings.alphaHighMin : null,
                merge_enabled: settings.mergeEnabled,
                merge_threshold: settings.mergeEnabled ? settings.mergeThreshold : null,
                outline_enabled: settings.outlineEnabled,
                outline_color: settings.outlineEnabled ? [r, g, b, a] : null,
                outline_thickness: settings.outlineEnabled ? settings.outlineThickness : null,
              },
              downscale_settings: (isAiUpscaled && settings.downscaleEnabled) ? {
                detected_scale: downscaleState.detectedScale,
                auto_trim: settings.downscaleAutoTrim,
                pad_canvas: null,
              } : undefined,
              created: new Date().toISOString(),
            },
          });
        } catch (err) {
          console.warn('Failed to record version (non-critical):', err);
        }
      }

      setStatusMessage('Saved!');
      onSaved?.();
      setTimeout(() => setStatusMessage(''), 2000);
    } catch (err) {
      console.error('Save failed:', err);
      setStatusMessage(`Error: ${err}`);
    } finally {
      setIsProcessing(false);
    }
  }, [imagePath, settings, isAiUpscaled, workspacePath, quickEdit, downscaleState.detectedScale, onSaved]);

  // Render loading state - show original image with analysis overlay
  if (detectionLoading) {
    return (
      <div className="image-editor">
        <header className="editor-header">
          <div className="editor-title">
            <h2>{imageName}</h2>
            <span className="badge">Analyzing...</span>
          </div>
          <button onClick={onClose} className="btn-close">Close</button>
        </header>

        <div className="editor-content">
          <div className="step-header">
            <h3>Analyzing Image</h3>
            <p>Detecting pixel grid and scale factor...</p>
          </div>

          <div className="preview-row">
            <div className="preview-pane" style={{ maxWidth: '500px' }}>
              <span className="pane-label">Original</span>
              <PannablePreview
                src={originalImage}
                alt="Original"
                zoom={zoom}
                onZoomChange={setZoom}
                showGrid={showGrid}
                loading={!originalImage}
                resetKey={imagePath}
              />
            </div>
          </div>

          <div className="controls-row" style={{ justifyContent: 'center' }}>
            <div className="zoom-controls">
              <span className="zoom-label">{zoom}x</span>
              <button className={zoom === 1 ? 'active' : ''} onClick={() => setZoom(1)}>1x</button>
              <button className={zoom === 4 ? 'active' : ''} onClick={() => setZoom(4)}>4x</button>
              <button className={zoom === 8 ? 'active' : ''} onClick={() => setZoom(8)}>8x</button>
              <span className="divider">|</span>
              <button className={showGrid ? 'active' : ''} onClick={() => setShowGrid(!showGrid)}>Grid</button>
            </div>
          </div>

          <div className="analysis-status">
            <div className="loading-spinner" />
            <span>Detecting AI upscaling pattern...</span>
          </div>
        </div>
      </div>
    );
  }

  // Render downscale step (if needed and not confirmed)
  if (isAiUpscaled && !downscaleState.confirmed) {
    return (
      <div className="image-editor">
        <header className="editor-header">
          <div className="editor-title">
            <h2>{imageName}</h2>
            <span className="badge ai">AI Upscaled {downscaleState.detectedScale}x</span>
          </div>
          <button onClick={onClose} className="btn-close">Close</button>
        </header>

        <div className="editor-content">
          <div className="step-header">
            <h3>Step 1: Downscale</h3>
            <p>Reduce to native pixel art resolution</p>
          </div>

          <div className="preview-row">
            <div className="preview-pane">
              <span className="pane-label">Original ({downscaleState.originalWidth} x {downscaleState.originalHeight})</span>
              <PannablePreview
                src={originalImage}
                alt="Original"
                zoom={Math.min(zoom, 2)}
                onZoomChange={setZoom}
                showGrid={showGrid}
                loading={!originalImage}
                resetKey={imagePath}
              />
            </div>

            <div className="preview-arrow">→</div>

            <div className="preview-pane">
              <span className="pane-label">Target ({downscaleState.targetWidth} x {downscaleState.targetHeight})</span>
              <PannablePreview
                src={downscaleState.previewData}
                alt="Downscaled"
                zoom={zoom}
                onZoomChange={setZoom}
                showGrid={showGrid}
                loading={downscaleState.previewLoading}
                resetKey={imagePath}
              />
            </div>
          </div>

          <div className="controls-row">
            <div className="dimension-controls">
              <div className="dimension-input">
                <label>Width</label>
                <div className="input-group">
                  <button onClick={() => updateDimension('width', downscaleState.targetWidth - 1)} disabled={downscaleState.targetWidth <= 1}>-</button>
                  <input type="number" value={downscaleState.targetWidth} onChange={e => updateDimension('width', parseInt(e.target.value) || 0)} />
                  <button onClick={() => updateDimension('width', downscaleState.targetWidth + 1)}>+</button>
                </div>
              </div>
              <span className="dimension-x">×</span>
              <div className="dimension-input">
                <label>Height</label>
                <div className="input-group">
                  <button onClick={() => updateDimension('height', downscaleState.targetHeight - 1)} disabled={downscaleState.targetHeight <= 1}>-</button>
                  <input type="number" value={downscaleState.targetHeight} onChange={e => updateDimension('height', parseInt(e.target.value) || 0)} />
                  <button onClick={() => updateDimension('height', downscaleState.targetHeight + 1)}>+</button>
                </div>
              </div>
              <button className="btn-small" onClick={resetToDetected}>Reset</button>
            </div>

            <div className="zoom-controls">
              <span className="zoom-label">{zoom}x</span>
              <button className={zoom === 1 ? 'active' : ''} onClick={() => setZoom(1)}>1x</button>
              <button className={zoom === 4 ? 'active' : ''} onClick={() => setZoom(4)}>4x</button>
              <button className={zoom === 8 ? 'active' : ''} onClick={() => setZoom(8)}>8x</button>
              <span className="divider">|</span>
              <button className={showGrid ? 'active' : ''} onClick={() => setShowGrid(!showGrid)}>Grid</button>
            </div>
          </div>

          <label className="checkbox-label">
            <input
              type="checkbox"
              checked={downscaleState.autoTrim}
              onChange={e => setDownscaleState(prev => ({ ...prev, autoTrim: e.target.checked }))}
            />
            Auto-trim transparent borders
          </label>
        </div>

        <footer className="editor-footer">
          <button className="btn" onClick={skipDownscale}>Skip (Keep Original)</button>
          <button className="btn-primary" onClick={confirmDownscale}>Confirm & Continue →</button>
        </footer>
      </div>
    );
  }

  // Render post-process step
  return (
    <div className="image-editor">
      <header className="editor-header">
        <div className="editor-title">
          <h2>{imageName}</h2>
          {isAiUpscaled && settings.downscaleEnabled && (
            <span className="badge">
              {settings.downscaleTargetWidth} x {settings.downscaleTargetHeight}
            </span>
          )}
        </div>
        <button onClick={onClose} className="btn-close">Close</button>
      </header>

      <div className="editor-content">
        {isAiUpscaled && (
          <div className="step-nav">
            <button className="btn-small" onClick={editDownscale}>← Edit Downscale</button>
          </div>
        )}

        <div className="preview-row">
          <div className="preview-pane">
            <span className="pane-label">{isAiUpscaled && settings.downscaleEnabled ? 'Downscaled' : 'Original'}</span>
            <PannablePreview
              src={isAiUpscaled && settings.downscaleEnabled ? downscaleState.previewData : originalImage}
              alt="Source"
              zoom={zoom}
              onZoomChange={setZoom}
              showGrid={showGrid}
              loading={!originalImage}
              resetKey={imagePath}
            />
          </div>

          <div className="preview-arrow">→</div>

          <div className="preview-pane">
            <span className="pane-label">Preview</span>
            <PannablePreview
              src={previewData}
              alt="Preview"
              zoom={zoom}
              onZoomChange={setZoom}
              showGrid={showGrid}
              loading={previewLoading}
              resetKey={imagePath}
            />
          </div>
        </div>

        <div className="controls-row">
          <div className="zoom-controls">
            <span className="zoom-label">{zoom}x</span>
            <button className={zoom === 1 ? 'active' : ''} onClick={() => setZoom(1)}>1x</button>
            <button className={zoom === 4 ? 'active' : ''} onClick={() => setZoom(4)}>4x</button>
            <button className={zoom === 8 ? 'active' : ''} onClick={() => setZoom(8)}>8x</button>
            <span className="divider">|</span>
            <button className={showGrid ? 'active' : ''} onClick={() => setShowGrid(!showGrid)}>Grid</button>
          </div>
        </div>

        {/* Settings */}
        <div className="settings-panel">
          {outlineWarning && settings.outlineEnabled && (
            <div className="warning-banner">
              <span>⚠ Existing outline detected ({(outlineWarning.confidence * 100).toFixed(0)}% confidence)</span>
              {outlineWarning.outline_color && (
                <span className="color-swatch" style={{ backgroundColor: rgbaToHex(outlineWarning.outline_color) }} />
              )}
              <button onClick={() => setOutlineWarning(null)}>Dismiss</button>
            </div>
          )}

          <div className="settings-row">
            <label className="setting">
              <input
                type="checkbox"
                checked={settings.mergeEnabled}
                onChange={e => updateSettings({ mergeEnabled: e.target.checked })}
              />
              <span>Color Merge</span>
              {settings.mergeEnabled && (
                <div className="setting-control">
                  <input
                    type="range"
                    min="1"
                    max="15"
                    step="0.5"
                    value={settings.mergeThreshold}
                    onChange={e => updateSettings({ mergeThreshold: parseFloat(e.target.value) })}
                  />
                  <span>{settings.mergeThreshold.toFixed(1)}</span>
                </div>
              )}
            </label>

            <label className="setting">
              <input
                type="checkbox"
                checked={settings.outlineEnabled}
                onChange={e => updateSettings({ outlineEnabled: e.target.checked })}
              />
              <span>Outline</span>
              {outlineWarning && settings.outlineEnabled && <span className="warning-icon">⚠</span>}
              {settings.outlineEnabled && (
                <>
                  <input
                    type="color"
                    value={settings.outlineColor}
                    onChange={e => updateSettings({ outlineColor: e.target.value })}
                  />
                  <div className="setting-control">
                    <input
                      type="range"
                      min="1"
                      max="5"
                      step="1"
                      value={settings.outlineThickness}
                      onChange={e => updateSettings({ outlineThickness: parseInt(e.target.value) })}
                    />
                    <span>{settings.outlineThickness}px</span>
                  </div>
                </>
              )}
            </label>
          </div>
        </div>
      </div>

      <footer className="editor-footer">
        {statusMessage && (
          <span className="status-message">
            {isProcessing && <span className="loading-spinner-small" />}
            {statusMessage}
          </span>
        )}
        <div className="footer-actions">
          {quickEdit ? (
            <>
              <button className="btn" onClick={() => handleSave(true)} disabled={isProcessing}>Save As...</button>
              <button className="btn-primary" onClick={() => handleSave(false)} disabled={isProcessing}>Save</button>
            </>
          ) : (
            <>
              <button className="btn" onClick={() => handleSave(true)} disabled={isProcessing}>Save As...</button>
              <button className="btn-primary" onClick={() => handleSave(false)} disabled={isProcessing}>Save</button>
            </>
          )}
        </div>
      </footer>
    </div>
  );
}
