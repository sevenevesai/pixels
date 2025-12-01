// V2 Process Panel - Right Sidebar with Settings and Lineage
import { SourceImage, ProcessingSettings, OutlineDetectionResult, rgbaToHex } from './types';

interface ProcessPanelProps {
  source: SourceImage | null;
  sources: SourceImage[];
  settings: ProcessingSettings;
  onUpdateSettings: (updates: Partial<ProcessingSettings>) => void;
  onApply: () => void;
  onApplyAll: () => void;
  isProcessing: boolean;
  selectedCount: number;
  outlineWarning: OutlineDetectionResult | null;
  onDismissWarning: () => void;
  progressMessage: string;
}

export function ProcessPanel({
  source,
  sources,
  settings,
  onUpdateSettings,
  onApply,
  onApplyAll,
  isProcessing,
  selectedCount,
  outlineWarning,
  onDismissWarning,
  progressMessage,
}: ProcessPanelProps) {
  // Batch stats
  const processedCount = sources.filter(s => s.status === 'processed').length;
  const pendingCount = sources.filter(s => s.status === 'pending').length;
  const errorCount = sources.filter(s => s.status === 'error').length;
  const totalCount = sources.length;

  return (
    <div className="process-panel">
      {/* Source Info */}
      <div className="process-section">
        <div className="section-title">SOURCE</div>
        {source ? (
          <div className="source-details">
            <div className="detail-row">
              <span className="detail-label">File:</span>
              <span className="detail-value" title={source.name}>{source.name}</span>
            </div>
            <div className="detail-row">
              <span className="detail-label">Type:</span>
              <span className="detail-value">
                {source.detectedType === 'ai_upscaled' ? 'AI Upscaled' :
                 source.detectedType === 'native_pixel_art' ? 'Native' : 'Unknown'}
                {source.detectedScale && source.detectedScale > 1 && ` (${source.detectedScale}x)`}
              </span>
            </div>
            <div className="detail-row">
              <span className="detail-label">Status:</span>
              <span className={`detail-value status-${source.status}`}>
                {source.status}
              </span>
            </div>
          </div>
        ) : (
          <div className="no-source">No image selected</div>
        )}
      </div>

      {/* Batch Status */}
      {totalCount > 0 && (
        <div className="process-section batch-status">
          <div className="section-title">BATCH STATUS</div>
          <div className="batch-stats">
            <div className="batch-stat">
              <span className="batch-stat-value">{processedCount}</span>
              <span className="batch-stat-label status-processed">processed</span>
            </div>
            <div className="batch-stat">
              <span className="batch-stat-value">{pendingCount}</span>
              <span className="batch-stat-label status-pending">pending</span>
            </div>
            {errorCount > 0 && (
              <div className="batch-stat">
                <span className="batch-stat-value">{errorCount}</span>
                <span className="batch-stat-label status-error">errors</span>
              </div>
            )}
          </div>
          {/* Progress bar */}
          <div className="batch-progress">
            <div
              className="batch-progress-bar"
              style={{ width: `${(processedCount / totalCount) * 100}%` }}
            />
          </div>
          <div className="batch-progress-text">
            {processedCount}/{totalCount} complete
          </div>
        </div>
      )}

      {/* Lineage */}
      <div className="process-section">
        <div className="section-title">LINEAGE</div>
        <div className="lineage-tree">
          <div className={`lineage-node ${source?.status === 'pending' ? 'current' : ''}`}>
            <span className="lineage-icon">○</span>
            <span className="lineage-label">Original</span>
            {source?.status === 'pending' && <span className="lineage-current">←</span>}
          </div>
          {source?.status === 'processed' && (
            <div className="lineage-node current">
              <span className="lineage-connector">│</span>
              <span className="lineage-icon">●</span>
              <span className="lineage-label">Processed</span>
              <span className="lineage-current">←</span>
            </div>
          )}
          {source?.status === 'error' && (
            <div className="lineage-node error">
              <span className="lineage-connector">│</span>
              <span className="lineage-icon">✕</span>
              <span className="lineage-label">Error</span>
            </div>
          )}
        </div>
        <button className="btn-tiny lineage-btn" disabled title="Coming soon">
          + Branch
        </button>
      </div>

      <hr className="section-divider" />

      {/* Outline Warning */}
      {outlineWarning && settings.outlineEnabled && (
        <div className="warning-box">
          <div className="warning-header">
            <span className="warning-icon">⚠️</span>
            <span className="warning-title">Outline Detected</span>
          </div>
          <div className="warning-content">
            <p>This image appears to already have an outline.</p>
            <p className="warning-detail">
              Confidence: {(outlineWarning.confidence * 100).toFixed(0)}%
              {outlineWarning.outline_color && (
                <>
                  <br />
                  Color: <span
                    className="color-swatch"
                    style={{ backgroundColor: rgbaToHex(outlineWarning.outline_color) }}
                  />
                  {rgbaToHex(outlineWarning.outline_color)}
                </>
              )}
            </p>
            <p className="warning-hint">
              Applying another outline may cause artifacts. Consider disabling outline or proceeding with caution.
            </p>
          </div>
          <button className="btn-tiny" onClick={onDismissWarning}>
            Dismiss
          </button>
        </div>
      )}

      {/* Settings */}
      <div className="process-section">
        <div className="section-title">SETTINGS</div>

        {/* Downscale */}
        <div className="setting-group">
          <label className="setting-toggle">
            <input
              type="checkbox"
              checked={settings.downscaleEnabled}
              onChange={(e) => onUpdateSettings({ downscaleEnabled: e.target.checked })}
              disabled={isProcessing}
            />
            <span>Downscale</span>
            {source?.detectedType === 'ai_upscaled' && (
              <span className="setting-badge ai-detected">AI</span>
            )}
          </label>
          {settings.downscaleEnabled && (
            <div className="setting-control">
              <label className="setting-toggle small">
                <input
                  type="checkbox"
                  checked={settings.downscaleAutoTrim}
                  onChange={(e) => onUpdateSettings({ downscaleAutoTrim: e.target.checked })}
                  disabled={isProcessing}
                />
                <span>Auto-trim borders</span>
              </label>
            </div>
          )}
          {settings.downscaleEnabled && source?.detectedType !== 'ai_upscaled' && (
            <div className="setting-hint">
              Downscaling only applies to AI-upscaled images
            </div>
          )}
        </div>

        {/* Color Merge */}
        <div className="setting-group">
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
            <div className="setting-control">
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
        <div className="setting-group">
          <label className="setting-toggle">
            <input
              type="checkbox"
              checked={settings.outlineEnabled}
              onChange={(e) => onUpdateSettings({ outlineEnabled: e.target.checked })}
              disabled={isProcessing}
            />
            <span>Outline</span>
            {outlineWarning && settings.outlineEnabled && (
              <span className="setting-warning">⚠️</span>
            )}
          </label>
          {settings.outlineEnabled && (
            <>
              <div className="setting-control color-control">
                <input
                  type="color"
                  value={settings.outlineColor}
                  onChange={(e) => onUpdateSettings({ outlineColor: e.target.value })}
                  disabled={isProcessing}
                />
                <span className="color-hex">{settings.outlineColor}</span>
              </div>
              <div className="setting-control">
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

      {/* Actions */}
      <div className="process-actions">
        {/* Processing indicator */}
        {isProcessing && progressMessage && (
          <div className="processing-status">
            <span className="loading-spinner-small" />
            <span className="processing-message">{progressMessage}</span>
          </div>
        )}

        <button
          className="btn-apply"
          onClick={onApply}
          disabled={!source || isProcessing}
        >
          {isProcessing ? 'Processing...' : '▶ Apply'}
        </button>
        <button
          className="btn-apply-all"
          onClick={onApplyAll}
          disabled={selectedCount === 0 || isProcessing}
        >
          {isProcessing ? 'Processing...' : `▶ Apply to All (${selectedCount})`}
        </button>

        {/* Quick action hints */}
        {!isProcessing && selectedCount > 0 && pendingCount > 0 && (
          <div className="actions-hint">
            {pendingCount} images ready to process
          </div>
        )}
      </div>
    </div>
  );
}
