// V2 One-Off Panel - Streamlined single-file processing interface
import { useState, useCallback } from 'react';
import { save } from '@tauri-apps/plugin-dialog';
import { SourceImage, ProcessingSettings, OutlineDetectionResult, rgbaToHex } from './types';

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
        {/* Preview Area */}
        <div className="oneoff-preview">
          <div className="oneoff-preview-row">
            {/* Original */}
            <div className="oneoff-preview-pane">
              <span className="pane-label">Original</span>
              <div className={`oneoff-preview-image ${showGrid ? 'show-grid' : ''}`}>
                {originalThumbnail ? (
                  <img
                    src={originalThumbnail}
                    alt="Original"
                    style={{ transform: `scale(${zoom})` }}
                    draggable={false}
                  />
                ) : (
                  <span className="no-image">Loading...</span>
                )}
              </div>
              <span className="oneoff-dimensions">
                {source.name}
                {source.detectedType === 'ai_upscaled' && source.detectedScale && source.detectedScale > 1 && (
                  <span className="type-badge ai">AI {source.detectedScale}x</span>
                )}
              </span>
            </div>

            {/* Arrow */}
            <div className="oneoff-arrow">
              <span>&#10145;</span>
            </div>

            {/* Preview */}
            <div className="oneoff-preview-pane">
              <span className="pane-label">Preview</span>
              <div className={`oneoff-preview-image ${showGrid ? 'show-grid' : ''}`}>
                {previewLoading ? (
                  <div className="preview-loading">
                    <div className="loading-spinner" />
                    <span>Generating...</span>
                  </div>
                ) : previewData ? (
                  <img
                    src={previewData}
                    alt="Preview"
                    style={{ transform: `scale(${zoom})` }}
                    draggable={false}
                  />
                ) : (
                  <span className="no-image">Preview</span>
                )}
              </div>
              <span className="oneoff-dimensions">Processed</span>
            </div>
          </div>

          {/* Zoom Controls */}
          <div className="oneoff-zoom-controls">
            <button
              className={`btn-tiny ${zoom === 1 ? 'active' : ''}`}
              onClick={() => setZoom(1)}
            >
              1x
            </button>
            <button
              className={`btn-tiny ${zoom === 4 ? 'active' : ''}`}
              onClick={() => setZoom(4)}
            >
              4x
            </button>
            <button
              className={`btn-tiny ${zoom === 8 ? 'active' : ''}`}
              onClick={() => setZoom(8)}
            >
              8x
            </button>
            <span className="control-divider">|</span>
            <button
              className={`btn-tiny ${showGrid ? 'active' : ''}`}
              onClick={() => setShowGrid(!showGrid)}
            >
              Grid
            </button>
          </div>
        </div>

        {/* Settings Bar */}
        <div className="oneoff-settings">
          {/* Outline Warning */}
          {outlineWarning && settings.outlineEnabled && (
            <div className="oneoff-warning">
              <span className="warning-icon">&#9888;</span>
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
            {/* Downscale */}
            <div className="oneoff-setting">
              <label className="setting-toggle">
                <input
                  type="checkbox"
                  checked={settings.downscaleEnabled}
                  onChange={(e) => onUpdateSettings({ downscaleEnabled: e.target.checked })}
                  disabled={isProcessing}
                />
                <span>Downscale</span>
                {source.detectedType === 'ai_upscaled' && (
                  <span className="setting-badge ai-detected">AI</span>
                )}
              </label>
              {settings.downscaleEnabled && (
                <label className="setting-toggle small inline">
                  <input
                    type="checkbox"
                    checked={settings.downscaleAutoTrim}
                    onChange={(e) => onUpdateSettings({ downscaleAutoTrim: e.target.checked })}
                    disabled={isProcessing}
                  />
                  <span>Trim</span>
                </label>
              )}
            </div>

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
                  <span className="setting-warning">&#9888;</span>
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
    </div>
  );
}
