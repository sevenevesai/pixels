// V3 Workspace - Simplified image editor approach
// - Single image editing at a time (no batch preview)
// - Folder navigation in left panel (just thumbnails, no pre-loading)
// - Universal ImageEditor for both quick-edit and project mode
import { useState, useCallback, useEffect, useRef } from 'react';
import { open } from '@tauri-apps/plugin-dialog';
import { readFile, stat } from '@tauri-apps/plugin-fs';
import { invoke } from '@tauri-apps/api/core';
import { getCurrentWebview } from '@tauri-apps/api/webview';
import type { UnlistenFn } from '@tauri-apps/api/event';
import { check } from '@tauri-apps/plugin-updater';
import { relaunch } from '@tauri-apps/plugin-process';
import { ImageEditor } from './ImageEditor';
import { BulkProcessPanel } from './BulkProcessPanel';
import { FolderImage, IMAGE_EXTENSIONS, isImagePath, scanFolderImages } from './folderImages';
import { useOutlineColor } from './useOutlineColor';
import './Workspace.css';

// Update checker banner — checks on mount, shows banner if update available
function UpdateBanner() {
  const [updateAvailable, setUpdateAvailable] = useState<{ version: string; notes: string } | null>(null);
  const [installing, setInstalling] = useState(false);
  const [dismissed, setDismissed] = useState(false);

  useEffect(() => {
    let cancelled = false;

    async function checkForUpdate() {
      try {
        const update = await check();
        if (!cancelled && update?.available) {
          setUpdateAvailable({
            version: update.version,
            notes: update.body || '',
          });
        }
      } catch {
        // Silent fail — no network, no endpoint, etc.
      }
    }

    // Small delay so it doesn't block app startup
    const timer = setTimeout(checkForUpdate, 2000);
    return () => { cancelled = true; clearTimeout(timer); };
  }, []);

  if (!updateAvailable || dismissed) return null;

  const handleUpdate = async () => {
    setInstalling(true);
    try {
      const update = await check();
      if (update?.available) {
        await update.downloadAndInstall();
        await relaunch();
      }
    } catch (err) {
      console.error('Update failed:', err);
      setInstalling(false);
    }
  };

  return (
    <div className="update-banner">
      <span>Update available: v{updateAvailable.version}</span>
      <button onClick={handleUpdate} disabled={installing}>
        {installing ? 'Installing...' : 'Update Now'}
      </button>
      <button onClick={() => setDismissed(true)} className="dismiss">Later</button>
    </div>
  );
}

interface WorkspaceState {
  // null = nothing open, 'quick-edit' = single file, string = folder path
  mode: null | 'quick-edit' | string;
  // Current image being edited
  currentImage: { path: string; name: string; thumbnail: string | null } | null;
  // Folder images (if folder mode)
  folderImages: FolderImage[];
  // Loading state
  loadingThumbnails: boolean;
  scanning: boolean;
}

const EMPTY_WORKSPACE: WorkspaceState = {
  mode: null,
  currentImage: null,
  folderImages: [],
  loadingThumbnails: false,
  scanning: false,
};

export function WorkspaceV3() {
  const [state, setState] = useState<WorkspaceState>(EMPTY_WORKSPACE);
  const [showBulkPanel, setShowBulkPanel] = useState(false);
  const [includeSubfolders, setIncludeSubfolders] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [bulkBusy, setBulkBusy] = useState(false);
  const busyRef = useRef(false);
  const openRequest = useRef(0);
  const folderRequest = useRef(0);
  const selectionRequest = useRef(0);
  const { outlineColor, setOutlineColor, error: colorError } = useOutlineColor();

  useEffect(() => () => {
    ++openRequest.current;
    ++folderRequest.current;
    ++selectionRequest.current;
  }, []);

  const onBulkBusyChange = useCallback((busy: boolean) => {
    busyRef.current = busy;
    setBulkBusy(busy);
  }, []);

  const loadFolder = useCallback(async (folderPath: string, recursive: boolean) => {
    const request = ++folderRequest.current;
    ++selectionRequest.current;
    const isCurrent = () => request === folderRequest.current;
    setError(null);
    setState({
      mode: folderPath,
      currentImage: null,
      folderImages: [],
      scanning: true,
      loadingThumbnails: true,
    });
    await loadFolderThumbnails(folderPath, recursive, isCurrent, setState, setError);
  }, []);

  // Dialogs and native drops share validation, workspace setup, and loading.
  const openPath = useCallback(async (path: string) => {
    if (busyRef.current) return;
    const request = ++openRequest.current;
    const isCurrent = () => request === openRequest.current && !busyRef.current;
    try {
      const info = await stat(path);
      if (!isCurrent()) return;
      if (info.isDirectory) {
        await invoke('init_workspace_command', { workspacePath: path });
        if (!isCurrent()) return;
        setShowBulkPanel(false);
        void loadFolder(path, includeSubfolders);
      } else {
        if (!info.isFile || !isImagePath(path)) {
          throw new Error('Choose a folder or a PNG, JPG, JPEG, BMP, or WebP image.');
        }
        const thumbnail = await loadThumbnail(path);
        if (!isCurrent()) return;
        if (!thumbnail) throw new Error(`Could not read image: ${path}`);
        ++folderRequest.current;
        ++selectionRequest.current;
        setError(null);
        setShowBulkPanel(false);
        setState({
          ...EMPTY_WORKSPACE,
          mode: 'quick-edit',
          currentImage: { path, name: path.replace(/\\/g, '/').split('/').pop() || path, thumbnail },
        });
      }
    } catch (err) {
      if (isCurrent()) setError(`Could not open: ${err}`);
    }
  }, [includeSubfolders, loadFolder]);

  // Open single image (quick-edit mode)
  const openImage = useCallback(async () => {
    if (busyRef.current) return;
    try {
      const file = await open({
        multiple: false,
        filters: [{ name: 'Images', extensions: IMAGE_EXTENSIONS }],
      });
      if (typeof file === 'string') await openPath(file);
    } catch (err) {
      setError(`Could not open image: ${err}`);
    }
  }, [openPath]);

  // Open folder
  const openFolder = useCallback(async () => {
    if (busyRef.current) return;
    try {
      const directory = await open({
        directory: true,
        multiple: false,
      });

      if (typeof directory === 'string') await openPath(directory);
    } catch (err) {
      setError(`Could not open folder: ${err}`);
    }
  }, [openPath]);

  useEffect(() => {
    let cancelled = false;
    let unlisten: UnlistenFn | undefined;
    async function subscribe() {
      try {
        const cleanup = await getCurrentWebview().onDragDropEvent(event => {
          if (cancelled) return;
          const { payload } = event;
          setDragging(payload.type === 'enter' || payload.type === 'over');
          if (payload.type !== 'drop') return;
          if (busyRef.current) {
            setError('Wait for the bulk operation to finish before opening another image or folder.');
          } else if (payload.paths.length !== 1) {
            setError('Drop one image or one folder at a time.');
          } else {
            void openPath(payload.paths[0]);
          }
        });
        if (cancelled) cleanup();
        else unlisten = cleanup;
      } catch (err) {
        if (!cancelled) setError(`Drag and drop is unavailable: ${err}`);
      }
    }
    void subscribe();
    return () => { cancelled = true; unlisten?.(); };
  }, [openPath]);

  // Select image from folder
  const selectImage = useCallback(async (image: FolderImage) => {
    if (busyRef.current) return;
    const request = ++selectionRequest.current;
    setShowBulkPanel(false);
    // Load full thumbnail if not loaded
    let thumbnail: string | null = image.thumbnail || null;
    if (!thumbnail) {
      thumbnail = await loadThumbnail(image.fullPath) || null;
    }

    if (request !== selectionRequest.current || busyRef.current) return;
    setState(prev => ({
      ...prev,
      currentImage: { path: image.fullPath, name: image.relativePath, thumbnail },
    }));
  }, []);

  // Close current image editor
  const closeEditor = useCallback(() => {
    ++selectionRequest.current;
    setState(prev => ({
      ...prev,
      currentImage: null,
    }));
  }, []);

  // Close entire workspace
  const closeWorkspace = useCallback(() => {
    if (busyRef.current) return;
    ++openRequest.current;
    ++folderRequest.current;
    ++selectionRequest.current;
    setShowBulkPanel(false);
    setError(null);
    setState(EMPTY_WORKSPACE);
  }, []);

  const folderPath = state.mode && state.mode !== 'quick-edit' ? state.mode : null;
  const folderName = folderPath?.replace(/\\/g, '/').split('/').pop() || folderPath;

  return (
    <div className={`workspace ${folderPath ? 'workspace-folder' : 'workspace-quick-edit'}`}>
      <UpdateBanner />
      {dragging && (
        <div className="workspace-drop-overlay" role="status">
          <div>{bulkBusy ? 'Bulk operation in progress' : 'Drop an image or folder to open'}</div>
        </div>
      )}
      {(error || colorError) && (
        <div className="workspace-error" role="alert">
          <span>{error || colorError}</span>
          {error && <button className="btn-small" onClick={() => setError(null)}>Dismiss</button>}
        </div>
      )}
      <header className="workspace-header">
        <h1 className="workspace-title">Pixels Toolkit</h1>
        <div className="workspace-actions">
          <button onClick={openFolder} className="btn" disabled={bulkBusy}>Open Folder</button>
          <button onClick={openImage} className="btn" disabled={bulkBusy}>Open Image</button>
        </div>
      </header>

      {state.mode === null ? (
        <div className="workspace-empty">
          <div className="empty-content">
            <h2>No Workspace Open</h2>
            <p>Drop an image or folder anywhere here, or choose one below</p>
            <div className="empty-actions">
              <button onClick={openFolder} className="btn-primary">Open Folder</button>
              <button onClick={openImage} className="btn">Open Image</button>
            </div>
          </div>
        </div>
      ) : !folderPath && state.currentImage ? (
        <ImageEditor
          key={state.currentImage.path}
          imagePath={state.currentImage.path}
          imageName={state.currentImage.name}
          originalImage={state.currentImage.thumbnail}
          quickEdit={true}
          onClose={closeWorkspace}
          outlineColor={outlineColor}
          onOutlineColorChange={setOutlineColor}
        />
      ) : folderPath ? (
        <>
          <div className="workspace-path-bar">
            <span className="workspace-label">FOLDER:</span>
            <span className="workspace-path" title={folderPath}>{folderName}</span>
            <span className="workspace-count">
              {state.scanning ? 'Scanning...' : `(${state.folderImages.length} images)`}
            </span>
            <label className="workspace-subfolders">
              <input
                type="checkbox"
                checked={includeSubfolders}
                disabled={bulkBusy}
                onChange={event => {
                  if (busyRef.current) return;
                  const recursive = event.target.checked;
                  ++openRequest.current;
                  setIncludeSubfolders(recursive);
                  setShowBulkPanel(false);
                  void loadFolder(folderPath, recursive);
                }}
              />
              Include subfolders
            </label>
            <button
              className="btn-small btn-primary"
              onClick={() => { ++selectionRequest.current; setShowBulkPanel(true); }}
              disabled={state.scanning || state.folderImages.length === 0 || bulkBusy}
            >
              Bulk Process
            </button>
            <button className="btn-small" onClick={closeWorkspace} disabled={bulkBusy}>Close</button>
          </div>

          <div className="workspace-main-v3">
            {/* Left panel - folder navigation */}
            <aside className="folder-nav">
              <div className="folder-nav-header">
                <span>Images</span>
                {state.loadingThumbnails && <span className="loading-dots">...</span>}
              </div>
              <div className="folder-nav-list">
                {state.folderImages.map((img) => (
                  <button
                    key={img.fullPath}
                    className={`folder-nav-item ${state.currentImage?.path === img.fullPath ? 'active' : ''}`}
                    onClick={() => selectImage(img)}
                    disabled={bulkBusy}
                  >
                    {img.thumbnail ? (
                      <img src={img.thumbnail} alt={img.name} className="nav-thumb" />
                    ) : (
                      <div className="nav-thumb-placeholder" />
                    )}
                    <span className="nav-name" title={img.relativePath}>{img.relativePath}</span>
                  </button>
                ))}
                {state.folderImages.length === 0 && !state.loadingThumbnails && (
                  <div className="folder-nav-empty">
                    {error ? 'Folder could not be loaded' : includeSubfolders
                      ? 'No images found'
                      : 'No images in this folder. Enable Include subfolders to search inside it.'}
                  </div>
                )}
              </div>
            </aside>

            {/* Main content - image editor, bulk panel, or placeholder */}
            <main className="editor-area">
              {showBulkPanel ? (
                <BulkProcessPanel
                  paths={state.folderImages.map(img => img.fullPath)}
                  workspacePath={folderPath}
                  includeSubfolders={includeSubfolders}
                  outlineColor={outlineColor}
                  onOutlineColorChange={setOutlineColor}
                  onBusyChange={onBulkBusyChange}
                  onClose={() => setShowBulkPanel(false)}
                  onComplete={() => {
                    // Refresh all thumbnails after bulk processing
                    void loadFolder(folderPath, includeSubfolders);
                  }}
                />
              ) : state.currentImage ? (
                <ImageEditor
                  key={state.currentImage.path}
                  imagePath={state.currentImage.path}
                  imageName={state.currentImage.name}
                  originalImage={state.currentImage.thumbnail}
                  quickEdit={false}
                  workspacePath={folderPath}
                  onClose={closeEditor}
                  outlineColor={outlineColor}
                  onOutlineColorChange={setOutlineColor}
                  onSaved={() => {
                    // Refresh thumbnail after save
                    if (state.currentImage) {
                      refreshThumbnail(state.currentImage.path, folderPath, setState);
                    }
                  }}
                />
              ) : (
                <div className="editor-placeholder">
                  <p>Select an image from the left panel to edit</p>
                </div>
              )}
            </main>
          </div>
        </>
      ) : null}
    </div>
  );
}

// Helper: Load thumbnails for folder (doesn't block UI)
async function loadFolderThumbnails(
  folderPath: string,
  includeSubfolders: boolean,
  isCurrent: () => boolean,
  setState: React.Dispatch<React.SetStateAction<WorkspaceState>>,
  setError: (error: string) => void,
) {
  try {
    const imageFiles = await scanFolderImages(folderPath, includeSubfolders, isCurrent);
    if (!isCurrent()) return;

    // Update state with file list immediately
    setState(prev => ({
      ...prev,
      folderImages: imageFiles,
      scanning: false,
    }));

    // Load thumbnails progressively (don't block)
    for (let i = 0; i < imageFiles.length; i++) {
      if (!isCurrent()) return;
      const img = imageFiles[i];
      try {
        const thumbnail = await loadThumbnail(img.fullPath);
        if (!isCurrent()) return;
        if (thumbnail) {
          setState(prev => ({
            ...prev,
            folderImages: prev.folderImages.map(f =>
              f.fullPath === img.fullPath ? { ...f, thumbnail } : f
            ),
          }));
        }
      } catch {
        // Ignore thumbnail load failures
      }
    }

    if (isCurrent()) setState(prev => ({ ...prev, loadingThumbnails: false }));
  } catch (err) {
    if (!isCurrent()) return;
    setError(String(err));
    setState(prev => ({ ...prev, scanning: false, loadingThumbnails: false }));
  }
}

// Helper: Load thumbnail as base64
async function loadThumbnail(filePath: string): Promise<string | undefined> {
  try {
    const fileData = await readFile(filePath);
    const base64 = btoa(
      new Uint8Array(fileData).reduce((data, byte) => data + String.fromCharCode(byte), '')
    );

    const name = filePath.toLowerCase();
    let mimeType = 'image/png';
    if (name.endsWith('.jpg') || name.endsWith('.jpeg')) mimeType = 'image/jpeg';
    else if (name.endsWith('.webp')) mimeType = 'image/webp';
    else if (name.endsWith('.bmp')) mimeType = 'image/bmp';

    return `data:${mimeType};base64,${base64}`;
  } catch {
    return undefined;
  }
}

// Helper: Refresh a single thumbnail after save
async function refreshThumbnail(
  filePath: string,
  folderPath: string,
  setState: React.Dispatch<React.SetStateAction<WorkspaceState>>
) {
  try {
    const newThumbnail = await loadThumbnail(filePath);
    if (newThumbnail) {
      setState(prev => prev.mode !== folderPath ? prev : ({
        ...prev,
        // Update in folder images list
        folderImages: prev.folderImages.map(f =>
          f.fullPath === filePath ? { ...f, thumbnail: newThumbnail } : f
        ),
        // Update current image if it's the same file
        currentImage: prev.currentImage?.path === filePath
          ? { ...prev.currentImage, thumbnail: newThumbnail }
          : prev.currentImage,
      }));
    }
  } catch (err) {
    console.warn('Failed to refresh thumbnail:', err);
  }
}
