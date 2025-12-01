// V2 Workspace - Main Container Component
import { useWorkspace } from './useWorkspace';
import { SourcesPanel } from './SourcesPanel';
import { PreviewPanel } from './PreviewPanel';
import { ProcessPanel } from './ProcessPanel';
import { OneOffPanel } from './OneOffPanel';
import './Workspace.css';

export function Workspace() {
  const { state, preview, actions } = useWorkspace();

  // Render One-Off Panel for single-file mode
  if (state.mode === 'single-file' && state.sources.length > 0) {
    return (
      <OneOffPanel
        source={state.sources[0]}
        settings={state.settings}
        onUpdateSettings={actions.updateSettings}
        previewData={preview.data}
        previewLoading={preview.loading}
        originalThumbnail={state.sources[0].thumbnail}
        outlineWarning={preview.outlineWarning}
        onDismissWarning={actions.dismissOutlineWarning}
        onSaveAs={actions.saveAs}
        onClose={actions.closeWorkspace}
        isProcessing={state.isProcessing}
        progressMessage={state.progressMessage}
      />
    );
  }

  return (
    <div className="workspace">
      {/* Header */}
      <header className="workspace-header">
        <h1 className="workspace-title">Pixels Toolkit</h1>
        <div className="workspace-actions">
          <button onClick={actions.openFolder} className="btn">
            Open Folder
          </button>
          <button onClick={actions.openImage} className="btn">
            Open Image
          </button>
        </div>
        <div className="header-right">
          <a
            href="https://www.paypal.com/donate/?hosted_button_id=XJUQUE78JATMN"
            target="_blank"
            rel="noopener noreferrer"
            className="donate-link"
          >
            Donate
          </a>
        </div>
      </header>

      {/* Workspace Path Bar */}
      {state.workspacePath && (
        <div className="workspace-path-bar">
          <span className="workspace-label">WORKSPACE:</span>
          <span className="workspace-path">{state.workspacePath}</span>
          <span className="workspace-count">({state.sources.length})</span>
          <div className="workspace-path-actions">
            <button onClick={actions.refresh} className="btn-small">
              Refresh
            </button>
            <button className="btn-small btn-export">
              Export
            </button>
          </div>
        </div>
      )}

      {/* Main Content */}
      {!state.workspacePath ? (
        <div className="workspace-empty">
          <div className="empty-content">
            <h2>No Workspace Open</h2>
            <p>Open a folder or image to begin processing</p>
            <div className="empty-actions">
              <button onClick={actions.openFolder} className="btn-primary">
                Open Folder
              </button>
              <button onClick={actions.openImage} className="btn">
                Open Image
              </button>
            </div>
          </div>
        </div>
      ) : (
        <div className="workspace-main">
          {/* Left Panel - Sources */}
          <SourcesPanel
            sources={state.sources}
            selectedIndices={state.selectedIndices}
            focusedIndex={state.focusedIndex}
            onFocus={actions.setFocused}
            onToggleSelect={actions.toggleSelection}
            onSelectAll={actions.selectAll}
            onDeselectAll={actions.deselectAll}
            onSelectRange={actions.selectRange}
            onSelectFiltered={actions.selectFiltered}
          />

          {/* Center Panel - Preview */}
          <PreviewPanel
            source={state.focusedIndex !== null ? state.sources[state.focusedIndex] : null}
            sources={state.sources}
            sampleIndices={state.sampleIndices}
            previewData={preview.data}
            previewLoading={preview.loading}
            samplePreviews={preview.samplePreviews}
            samplePreviewsLoading={preview.samplePreviewsLoading}
            onSampleClick={actions.setFocused}
          />

          {/* Right Panel - Process */}
          <ProcessPanel
            source={state.focusedIndex !== null ? state.sources[state.focusedIndex] : null}
            sources={state.sources}
            settings={state.settings}
            onUpdateSettings={actions.updateSettings}
            onApply={() => state.focusedIndex !== null && actions.processImage(state.focusedIndex, true)}
            onApplyAll={() => actions.processAll(true)}
            isProcessing={state.isProcessing}
            selectedCount={state.selectedIndices.size}
            outlineWarning={preview.outlineWarning}
            onDismissWarning={actions.dismissOutlineWarning}
            progressMessage={state.progressMessage}
          />
        </div>
      )}

      {/* Progress Message */}
      {state.progressMessage && state.mode === 'folder' && (
        <div className="workspace-progress">
          {state.progressMessage}
        </div>
      )}
    </div>
  );
}
