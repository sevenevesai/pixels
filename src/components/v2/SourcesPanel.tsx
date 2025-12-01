// V2 Sources Panel - Left Sidebar with Batch Operations
import { useState, useCallback, useRef } from 'react';
import { SourceImage } from './types';

type FilterMode = 'all' | 'pending' | 'processed' | 'error';
type SelectableFilterMode = 'pending' | 'processed' | 'error';

interface SourcesPanelProps {
  sources: SourceImage[];
  selectedIndices: Set<number>;
  focusedIndex: number | null;
  onFocus: (index: number) => void;
  onToggleSelect: (index: number) => void;
  onSelectAll: () => void;
  onDeselectAll: () => void;
  onSelectRange: (startIndex: number, endIndex: number) => void;
  onSelectFiltered: (filter: SelectableFilterMode) => void;
}

export function SourcesPanel({
  sources,
  selectedIndices,
  focusedIndex,
  onFocus,
  onToggleSelect,
  onSelectAll,
  onDeselectAll,
  onSelectRange,
  onSelectFiltered,
}: SourcesPanelProps) {
  const [filter, setFilter] = useState<FilterMode>('all');
  const lastClickedIndexRef = useRef<number | null>(null);

  // Count by status
  const processedCount = sources.filter(s => s.status === 'processed').length;
  const pendingCount = sources.filter(s => s.status === 'pending').length;
  const errorCount = sources.filter(s => s.status === 'error').length;

  // Filter sources
  const filteredSources = sources.map((source, index) => ({ source, index }))
    .filter(({ source }) => {
      if (filter === 'all') return true;
      return source.status === filter;
    });

  // Handle click with modifiers
  const handleItemClick = useCallback((index: number, e: React.MouseEvent) => {
    if (e.shiftKey && lastClickedIndexRef.current !== null) {
      // Shift+click: select range
      const start = Math.min(lastClickedIndexRef.current, index);
      const end = Math.max(lastClickedIndexRef.current, index);
      onSelectRange(start, end);
    } else if (e.ctrlKey || e.metaKey) {
      // Ctrl/Cmd+click: toggle selection
      onToggleSelect(index);
    } else {
      // Normal click: focus only
      onFocus(index);
    }
    lastClickedIndexRef.current = index;
  }, [onFocus, onToggleSelect, onSelectRange]);

  // Handle checkbox click (always toggle)
  const handleCheckboxClick = useCallback((index: number, e: React.MouseEvent) => {
    e.stopPropagation();
    onToggleSelect(index);
    lastClickedIndexRef.current = index;
  }, [onToggleSelect]);

  // Handle filter change
  const handleFilterChange = useCallback((e: React.ChangeEvent<HTMLSelectElement>) => {
    setFilter(e.target.value as FilterMode);
  }, []);

  // Select all visible (filtered)
  const handleSelectVisible = useCallback(() => {
    if (filter === 'all') {
      onSelectAll();
    } else {
      // filter is narrowed to SelectableFilterMode here
      onSelectFiltered(filter as SelectableFilterMode);
    }
  }, [filter, onSelectAll, onSelectFiltered]);

  return (
    <div className="sources-panel">
      <div className="sources-header">
        <span className="sources-title">SOURCES</span>
        <select
          className="sources-filter"
          value={filter}
          onChange={handleFilterChange}
        >
          <option value="all">All ({sources.length})</option>
          <option value="pending">Pending ({pendingCount})</option>
          <option value="processed">Processed ({processedCount})</option>
          {errorCount > 0 && (
            <option value="error">Errors ({errorCount})</option>
          )}
        </select>
      </div>

      {/* Selection info bar */}
      {selectedIndices.size > 0 && (
        <div className="sources-selection-bar">
          <span className="selection-count">{selectedIndices.size} selected</span>
          <button
            className="btn-tiny selection-clear"
            onClick={onDeselectAll}
            title="Clear selection"
          >
            ✕
          </button>
        </div>
      )}

      <div className="sources-list">
        {filteredSources.length === 0 ? (
          <div className="sources-empty">
            {filter === 'all' ? 'No images found' : `No ${filter} images`}
          </div>
        ) : (
          filteredSources.map(({ source, index }) => (
            <div
              key={source.fullPath}
              className={`source-item ${selectedIndices.has(index) ? 'selected' : ''} ${focusedIndex === index ? 'focused' : ''}`}
              onClick={(e) => handleItemClick(index, e)}
            >
              <div
                className="source-checkbox"
                onClick={(e) => handleCheckboxClick(index, e)}
              >
                {selectedIndices.has(index) ? '☑' : '☐'}
              </div>

              <div className="source-thumb">
                {source.thumbnail ? (
                  <img src={source.thumbnail} alt={source.name} draggable={false} />
                ) : (
                  <div className="no-thumb">?</div>
                )}
              </div>

              <div className="source-info">
                <div className="source-name" title={source.name}>
                  {source.name}
                </div>
                <div className="source-status">
                  <span className={`status-dot status-${source.status}`} />
                  {source.status}
                  {source.status === 'error' && source.error && (
                    <span className="error-hint" title={source.error}>!</span>
                  )}
                </div>
              </div>
            </div>
          ))
        )}
      </div>

      <div className="sources-footer">
        <button onClick={handleSelectVisible} className="btn-tiny">
          {filter === 'all' ? 'Select All' : `Select ${filter}`}
        </button>
        <button onClick={onDeselectAll} className="btn-tiny">
          Select None
        </button>
      </div>

      {/* Keyboard shortcuts hint */}
      <div className="sources-hint">
        Ctrl+click: toggle, Shift+click: range
      </div>
    </div>
  );
}
