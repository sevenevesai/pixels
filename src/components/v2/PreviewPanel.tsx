// V2 Preview Panel - Center Area with Live Preview
import { useState, useRef, useCallback, useEffect } from 'react';
import { SourceImage } from './types';

interface PreviewPanelProps {
  source: SourceImage | null;
  sources: SourceImage[];
  sampleIndices: number[];
  previewData: string | null;
  previewLoading: boolean;
  samplePreviews: Map<number, string>;
  samplePreviewsLoading: boolean;
  onSampleClick: (index: number) => void;
}

type ZoomLevel = '1x' | '2x' | '4x' | '8x' | 'fit';
type ViewMode = 'single' | 'split' | 'swap';

const ZOOM_LEVELS: ZoomLevel[] = ['1x', '2x', '4x', '8x', 'fit'];
const ZOOM_VALUES = { '1x': 1, '2x': 2, '4x': 4, '8x': 8, 'fit': null };

export function PreviewPanel({
  source,
  sources,
  sampleIndices,
  previewData,
  previewLoading,
  samplePreviews,
  samplePreviewsLoading,
  onSampleClick,
}: PreviewPanelProps) {
  const [zoom, setZoom] = useState<ZoomLevel>('4x');
  const [viewMode, setViewMode] = useState<ViewMode>('split');
  const [showGrid, setShowGrid] = useState(false);

  // Refs for synchronized scrolling
  const originalPaneRef = useRef<HTMLDivElement>(null);
  const previewPaneRef = useRef<HTMLDivElement>(null);
  const isScrollingSyncedRef = useRef(false);

  const zoomScale = ZOOM_VALUES[zoom];

  const imageStyle = zoomScale !== null
    ? { transform: `scale(${zoomScale})`, transformOrigin: 'center center' }
    : { maxWidth: '100%', maxHeight: '100%', objectFit: 'contain' as const };

  // Handle mouse wheel zoom
  const handleWheel = useCallback((e: React.WheelEvent) => {
    if (!e.ctrlKey && !e.metaKey) return;

    e.preventDefault();
    const currentIndex = ZOOM_LEVELS.indexOf(zoom);

    if (e.deltaY < 0 && currentIndex < ZOOM_LEVELS.length - 1) {
      // Zoom in (scroll up)
      setZoom(ZOOM_LEVELS[currentIndex + 1]);
    } else if (e.deltaY > 0 && currentIndex > 0) {
      // Zoom out (scroll down)
      setZoom(ZOOM_LEVELS[currentIndex - 1]);
    }
  }, [zoom]);

  // Synchronized scrolling handler
  const handleScroll = useCallback((source: 'original' | 'preview') => {
    if (isScrollingSyncedRef.current) return;

    isScrollingSyncedRef.current = true;

    const sourcePane = source === 'original' ? originalPaneRef.current : previewPaneRef.current;
    const targetPane = source === 'original' ? previewPaneRef.current : originalPaneRef.current;

    if (sourcePane && targetPane) {
      targetPane.scrollLeft = sourcePane.scrollLeft;
      targetPane.scrollTop = sourcePane.scrollTop;
    }

    // Reset flag after scroll event completes
    requestAnimationFrame(() => {
      isScrollingSyncedRef.current = false;
    });
  }, []);

  // Keyboard shortcuts for zoom
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;

      const currentIndex = ZOOM_LEVELS.indexOf(zoom);

      if (e.key === '+' || e.key === '=') {
        e.preventDefault();
        if (currentIndex < ZOOM_LEVELS.length - 1) {
          setZoom(ZOOM_LEVELS[currentIndex + 1]);
        }
      } else if (e.key === '-') {
        e.preventDefault();
        if (currentIndex > 0) {
          setZoom(ZOOM_LEVELS[currentIndex - 1]);
        }
      } else if (e.key === '0') {
        e.preventDefault();
        setZoom('fit');
      } else if (e.key === '1') {
        e.preventDefault();
        setZoom('1x');
      } else if (e.key === 'g') {
        e.preventDefault();
        setShowGrid(prev => !prev);
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [zoom]);

  return (
    <div className="preview-panel" onWheel={handleWheel}>
      {/* Preview Header */}
      <div className="preview-header">
        <span className="preview-title">PREVIEW</span>
        <div className="preview-controls">
          <button
            className={`btn-tiny ${viewMode === 'single' ? 'active' : ''}`}
            onClick={() => setViewMode('single')}
            title="Single view (preview only)"
          >
            ◻
          </button>
          <button
            className={`btn-tiny ${viewMode === 'split' ? 'active' : ''}`}
            onClick={() => setViewMode('split')}
            title="Split view (original | preview)"
          >
            ◫
          </button>
          <button
            className={`btn-tiny ${viewMode === 'swap' ? 'active' : ''}`}
            onClick={() => setViewMode('swap')}
            title="Swap sides"
          >
            ⇄
          </button>
          <span className="control-divider">|</span>
          {ZOOM_LEVELS.map(level => (
            <button
              key={level}
              className={`btn-tiny ${zoom === level ? 'active' : ''}`}
              onClick={() => setZoom(level)}
              title={level === 'fit' ? 'Fit to view' : `${level} zoom`}
            >
              {level === 'fit' ? '⊡' : level}
            </button>
          ))}
          <span className="control-divider">|</span>
          <button
            className={`btn-tiny ${showGrid ? 'active' : ''}`}
            onClick={() => setShowGrid(!showGrid)}
            title="Toggle transparency grid (G)"
          >
            ⊞
          </button>
        </div>
      </div>

      {/* Main Preview Area */}
      <div className="preview-main">
        {!source ? (
          <div className="preview-empty">
            <p>Select an image to preview</p>
            <p className="preview-hint">Use Ctrl+Scroll to zoom, G for grid</p>
          </div>
        ) : viewMode === 'single' ? (
          <div className="preview-single">
            <div className={`preview-image ${showGrid ? 'show-grid' : ''}`}>
              {previewLoading && (
                <div className="preview-loading">
                  <span className="loading-spinner" />
                  Generating preview...
                </div>
              )}
              {previewData ? (
                <img
                  src={previewData}
                  alt={`${source.name} preview`}
                  style={imageStyle}
                  draggable={false}
                />
              ) : source.thumbnail ? (
                <img
                  src={source.thumbnail}
                  alt={source.name}
                  style={imageStyle}
                  draggable={false}
                />
              ) : null}
            </div>
          </div>
        ) : (
          <div className={`preview-split ${viewMode === 'swap' ? 'swapped' : ''}`}>
            {/* Original Pane */}
            <div className="preview-pane">
              <div className="pane-label">Original</div>
              <div
                ref={originalPaneRef}
                className={`preview-image scrollable ${showGrid ? 'show-grid' : ''}`}
                onScroll={() => handleScroll('original')}
              >
                {source.thumbnail ? (
                  <img
                    src={source.thumbnail}
                    alt={`${source.name} original`}
                    style={imageStyle}
                    draggable={false}
                  />
                ) : (
                  <div className="no-image">No image</div>
                )}
              </div>
            </div>

            <div className="preview-divider" />

            {/* Preview Pane */}
            <div className="preview-pane">
              <div className="pane-label">
                Preview
                {previewLoading && <span className="loading-indicator"> ...</span>}
              </div>
              <div
                ref={previewPaneRef}
                className={`preview-image scrollable ${showGrid ? 'show-grid' : ''}`}
                onScroll={() => handleScroll('preview')}
              >
                {previewLoading && !previewData && (
                  <div className="preview-loading">
                    <span className="loading-spinner" />
                  </div>
                )}
                {previewData ? (
                  <img
                    src={previewData}
                    alt={`${source.name} preview`}
                    style={imageStyle}
                    draggable={false}
                  />
                ) : source.thumbnail && !previewLoading ? (
                  <>
                    <img
                      src={source.thumbnail}
                      alt={source.name}
                      style={{ ...imageStyle, opacity: 0.5 }}
                      draggable={false}
                    />
                    <div className="preview-overlay">
                      <span className="preview-badge">Generating...</span>
                    </div>
                  </>
                ) : null}
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Sample Row */}
      <div className="preview-samples">
        <div className="samples-header">
          <span className="samples-title">
            SAMPLE
            {samplePreviewsLoading && <span className="loading-indicator"> ...</span>}
          </span>
          <span className="samples-hint">Live preview of settings</span>
        </div>
        <div className="samples-row">
          {sampleIndices.map((idx) => {
            const sample = sources[idx];
            if (!sample) return null;

            // Use processed preview if available, otherwise original thumbnail
            const previewSrc = samplePreviews.get(idx) || sample.thumbnail;
            const hasPreview = samplePreviews.has(idx);

            return (
              <div
                key={idx}
                className={`sample-item ${source?.fullPath === sample.fullPath ? 'active' : ''} ${hasPreview ? 'has-preview' : ''}`}
                onClick={() => onSampleClick(idx)}
              >
                {previewSrc ? (
                  <img src={previewSrc} alt={sample.name} draggable={false} />
                ) : (
                  <div className="sample-placeholder">?</div>
                )}
                {samplePreviewsLoading && !hasPreview && (
                  <div className="sample-loading">
                    <span className="loading-spinner-small" />
                  </div>
                )}
                <div className="sample-status">
                  <span className={`status-dot status-${sample.status}`} />
                </div>
                <div className="sample-name">{sample.name.slice(0, 8)}</div>
              </div>
            );
          })}
          {sampleIndices.length === 0 && (
            <div className="samples-empty">No samples selected</div>
          )}
        </div>
      </div>
    </div>
  );
}
