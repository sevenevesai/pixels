import { useState, useCallback, useEffect } from 'react';
import { invoke } from '@tauri-apps/api/core';
import { listen, UnlistenFn } from '@tauri-apps/api/event';
import { hexToRgba } from './types';

interface BulkProcessSettings {
  downscaleEnabled: boolean;
  backgroundEnabled: boolean;
  backgroundTolerance: number;
  alphaEnabled: boolean;
  alphaLowCutoff: number;
  alphaHighMin: number;
  mergeEnabled: boolean;
  mergeThreshold: number;
  outlineEnabled: boolean;
  outlineColor: string;
  outlineThickness: number;
}

const DEFAULT_BULK_SETTINGS: BulkProcessSettings = {
  downscaleEnabled: false,
  backgroundEnabled: false,
  backgroundTolerance: 30,
  alphaEnabled: true,
  alphaLowCutoff: 200,
  alphaHighMin: 200,
  mergeEnabled: true,
  mergeThreshold: 3.0,
  outlineEnabled: true,
  outlineColor: '#110602',
  outlineThickness: 1,
};

interface BatchProgressEvent {
  index: number;
  total: number;
  current_file: string;
  status: 'processing' | 'done' | 'error' | 'cancelled';
  error: string | null;
}

interface BatchCompleteEvent {
  processed: number;
  failed: number;
  cancelled: boolean;
}

interface BulkProcessPanelProps {
  paths: string[];
  workspacePath: string;
  onClose: () => void;
  onComplete: () => void;
}

export function BulkProcessPanel({ paths, workspacePath, onClose, onComplete }: BulkProcessPanelProps) {
  const [settings, setSettings] = useState<BulkProcessSettings>(DEFAULT_BULK_SETTINGS);
  const [isRunning, setIsRunning] = useState(false);
  const [progress, setProgress] = useState<{ index: number; total: number; currentFile: string } | null>(null);
  const [result, setResult] = useState<{ processed: number; failed: number; cancelled: boolean } | null>(null);
  const [errors, setErrors] = useState<Array<{ file: string; error: string }>>([]);
  const [showErrors, setShowErrors] = useState(false);
  const [canRevert, setCanRevert] = useState(false);
  const [reverting, setReverting] = useState(false);
  const [revertResult, setRevertResult] = useState<{ reverted: number; failed: number } | null>(null);

  // Check if manifest exists on mount (in case panel was re-opened after a previous batch)
  useEffect(() => {
    invoke<boolean>('batch_has_manifest_command', { workspacePath })
      .then(setCanRevert)
      .catch(() => setCanRevert(false));
  }, [workspacePath]);

  useEffect(() => {
    const unlisteners: UnlistenFn[] = [];

    listen<BatchProgressEvent>('batch-progress', (event) => {
      const { index, total, current_file, status, error } = event.payload;

      if (status === 'processing') {
        setProgress({ index, total, currentFile: current_file });
      } else if (status === 'error' && error) {
        setErrors(prev => [...prev, { file: current_file, error }]);
      }
    }).then(u => unlisteners.push(u));

    listen<BatchCompleteEvent>('batch-complete', (event) => {
      setIsRunning(false);
      setResult(event.payload);
      setProgress(null);
      setCanRevert(true);
      onComplete();
    }).then(u => unlisteners.push(u));

    return () => { unlisteners.forEach(u => u()); };
  }, [onComplete]);

  const handleStart = useCallback(async () => {
    setIsRunning(true);
    setResult(null);
    setRevertResult(null);
    setErrors([]);
    setProgress({ index: 0, total: paths.length, currentFile: '' });

    const [r, g, b, a] = hexToRgba(settings.outlineColor);

    const backgroundSettings = settings.backgroundEnabled
      ? { tolerance: settings.backgroundTolerance }
      : null;

    const alphaSettings = settings.alphaEnabled
      ? { low_cutoff: settings.alphaLowCutoff, high_min: settings.alphaHighMin, high_max: 255 }
      : null;

    const mergeSettings = settings.mergeEnabled
      ? { threshold: settings.mergeThreshold }
      : null;

    const outlineSettings = settings.outlineEnabled
      ? { color: [r, g, b, a], connectivity: 'four', thickness: settings.outlineThickness, edge_transparent_cutoff: 0 }
      : null;

    try {
      await invoke('batch_process_command', {
        paths,
        workspacePath,
        downscaleEnabled: settings.downscaleEnabled,
        backgroundSettings,
        alphaSettings,
        mergeSettings,
        outlineSettings,
      });
    } catch (err) {
      setIsRunning(false);
      setResult({ processed: 0, failed: paths.length, cancelled: false });
      console.error('Batch process failed:', err);
    }
  }, [paths, workspacePath, settings]);

  const handleCancel = useCallback(async () => {
    try {
      await invoke('batch_cancel_command');
    } catch (err) {
      console.error('Failed to cancel:', err);
    }
  }, []);

  const handleRevert = useCallback(async () => {
    setReverting(true);
    try {
      const result = await invoke<{ reverted: number; failed: number; errors: string[] }>(
        'batch_revert_command',
        { workspacePath }
      );
      setRevertResult({ reverted: result.reverted, failed: result.failed });
      setCanRevert(false);
      setResult(null);
      onComplete();
    } catch (err) {
      console.error('Revert failed:', err);
      setRevertResult({ reverted: 0, failed: 1 });
    } finally {
      setReverting(false);
    }
  }, [workspacePath, onComplete]);

  const updateSettings = useCallback((updates: Partial<BulkProcessSettings>) => {
    setSettings(prev => ({ ...prev, ...updates }));
  }, []);

  const progressPct = progress ? ((progress.index + 1) / progress.total * 100) : 0;
  const currentFileName = progress?.currentFile.replace(/\\/g, '/').split('/').pop() || '';

  return (
    <div className="bulk-panel">
      <div className="bulk-panel-header">
        <h3>Bulk Process</h3>
        <div className="bulk-header-actions">
          {canRevert && !isRunning && (
            <button className="btn-small btn-revert" onClick={handleRevert} disabled={reverting}>
              {reverting ? 'Reverting...' : 'Revert All'}
            </button>
          )}
          <button className="btn-small" onClick={onClose} disabled={isRunning}>Close</button>
        </div>
      </div>

      {revertResult && (
        <div className={`bulk-revert-result ${revertResult.failed > 0 ? 'partial' : ''}`}>
          {revertResult.failed === 0
            ? `Reverted ${revertResult.reverted} images to originals`
            : `Reverted ${revertResult.reverted}, failed ${revertResult.failed}`
          }
        </div>
      )}

      {!isRunning && !result && (
        <div className="bulk-panel-settings">
          <div className="bulk-section">
            <label className="bulk-toggle">
              <input
                type="checkbox"
                checked={settings.downscaleEnabled}
                onChange={e => updateSettings({ downscaleEnabled: e.target.checked })}
              />
              <span>Downscale (auto-detect per image)</span>
            </label>
            {settings.downscaleEnabled && (
              <p className="bulk-hint">Detects AI-upscaled images and downscales to native resolution. Non-AI images are skipped.</p>
            )}
          </div>

          <div className="bulk-section">
            <label className="bulk-toggle">
              <input
                type="checkbox"
                checked={settings.backgroundEnabled}
                onChange={e => updateSettings({ backgroundEnabled: e.target.checked })}
              />
              <span>Remove Background</span>
            </label>
            {settings.backgroundEnabled && (
              <div className="bulk-field">
                <label>Tolerance</label>
                <input
                  type="range"
                  min={10}
                  max={60}
                  value={settings.backgroundTolerance}
                  onChange={e => updateSettings({ backgroundTolerance: Number(e.target.value) })}
                />
                <span className="bulk-value">{settings.backgroundTolerance}</span>
              </div>
            )}
          </div>

          <div className="bulk-divider" />

          <div className="bulk-section">
            <label className="bulk-toggle">
              <input
                type="checkbox"
                checked={settings.alphaEnabled}
                onChange={e => updateSettings({ alphaEnabled: e.target.checked })}
              />
              <span>Alpha Normalize</span>
            </label>
          </div>

          <div className="bulk-section">
            <label className="bulk-toggle">
              <input
                type="checkbox"
                checked={settings.mergeEnabled}
                onChange={e => updateSettings({ mergeEnabled: e.target.checked })}
              />
              <span>Color Merge</span>
            </label>
            {settings.mergeEnabled && (
              <div className="bulk-field">
                <label>Threshold</label>
                <input
                  type="range"
                  min={1}
                  max={10}
                  step={0.5}
                  value={settings.mergeThreshold}
                  onChange={e => updateSettings({ mergeThreshold: Number(e.target.value) })}
                />
                <span className="bulk-value">{settings.mergeThreshold}</span>
              </div>
            )}
          </div>

          <div className="bulk-section">
            <label className="bulk-toggle">
              <input
                type="checkbox"
                checked={settings.outlineEnabled}
                onChange={e => updateSettings({ outlineEnabled: e.target.checked })}
              />
              <span>Outline</span>
            </label>
            {settings.outlineEnabled && (
              <div className="bulk-field">
                <label>Color</label>
                <input
                  type="color"
                  value={settings.outlineColor}
                  onChange={e => updateSettings({ outlineColor: e.target.value })}
                />
                <label>Thickness</label>
                <input
                  type="number"
                  min={1}
                  max={5}
                  value={settings.outlineThickness}
                  onChange={e => updateSettings({ outlineThickness: Number(e.target.value) })}
                />
              </div>
            )}
          </div>

          <div className="bulk-divider" />

          <div className="bulk-summary">
            Applying to <strong>{paths.length}</strong> image{paths.length !== 1 ? 's' : ''}
          </div>

          <button className="btn-primary bulk-start" onClick={handleStart}>
            Apply to All
          </button>
        </div>
      )}

      {isRunning && progress && (
        <div className="bulk-panel-progress">
          <div className="bulk-progress-bar">
            <div className="bulk-progress-fill" style={{ width: `${progressPct}%` }} />
          </div>
          <div className="bulk-progress-text">
            {progress.index + 1} / {progress.total}
          </div>
          <div className="bulk-progress-file" title={progress.currentFile}>
            {currentFileName}
          </div>
          <button className="btn-small" onClick={handleCancel}>Cancel</button>
        </div>
      )}

      {result && (
        <div className="bulk-panel-result">
          {result.cancelled ? (
            <div className="bulk-result-message">
              Cancelled — {result.processed} processed, {result.failed} failed
            </div>
          ) : result.failed === 0 ? (
            <div className="bulk-result-message bulk-result-success">
              Done — {result.processed} images processed
            </div>
          ) : (
            <div className="bulk-result-message bulk-result-partial">
              Done — {result.processed} processed, {result.failed} failed
            </div>
          )}

          {errors.length > 0 && (
            <div className="bulk-errors">
              <button className="btn-tiny" onClick={() => setShowErrors(v => !v)}>
                {showErrors ? 'Hide' : 'Show'} errors ({errors.length})
              </button>
              {showErrors && (
                <ul className="bulk-error-list">
                  {errors.map((e, i) => (
                    <li key={i}>
                      <strong>{e.file.replace(/\\/g, '/').split('/').pop()}</strong>: {e.error}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}

          <div className="bulk-result-actions">
            {canRevert && (
              <button className="btn btn-revert" onClick={handleRevert} disabled={reverting}>
                {reverting ? 'Reverting...' : 'Revert All'}
              </button>
            )}
            <button className="btn" onClick={onClose}>Close</button>
          </div>
        </div>
      )}
    </div>
  );
}
