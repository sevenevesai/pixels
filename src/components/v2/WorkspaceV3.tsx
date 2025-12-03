// V3 Workspace - Simplified image editor approach
// - Single image editing at a time (no batch preview)
// - Folder navigation in left panel (just thumbnails, no pre-loading)
// - Universal ImageEditor for both quick-edit and project mode
import { useState, useCallback } from 'react';
import { open } from '@tauri-apps/plugin-dialog';
import { readDir, readFile } from '@tauri-apps/plugin-fs';
import { invoke } from '@tauri-apps/api/core';
import { ImageEditor } from './ImageEditor';
import './Workspace.css';

interface FolderImage {
  name: string;
  fullPath: string;
  thumbnail?: string;
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
}

export function WorkspaceV3() {
  const [state, setState] = useState<WorkspaceState>({
    mode: null,
    currentImage: null,
    folderImages: [],
    loadingThumbnails: false,
  });

  // Open single image (quick-edit mode)
  const openImage = useCallback(async () => {
    try {
      const file = await open({
        multiple: false,
        filters: [{ name: 'Images', extensions: ['png', 'jpg', 'jpeg', 'bmp', 'webp'] }],
      });

      if (!file) return;

      const filePath = file as string;
      const fileName = filePath.replace(/\\/g, '/').split('/').pop() || '';
      const thumbnail = await loadThumbnail(filePath) || null;

      setState({
        mode: 'quick-edit',
        currentImage: { path: filePath, name: fileName, thumbnail },
        folderImages: [],
        loadingThumbnails: false,
      });
    } catch (err) {
      console.error('Failed to open image:', err);
    }
  }, []);

  // Open folder
  const openFolder = useCallback(async () => {
    try {
      const directory = await open({
        directory: true,
        multiple: false,
      });

      if (!directory) return;

      const folderPath = directory as string;

      setState({
        mode: folderPath,
        currentImage: null,
        folderImages: [],
        loadingThumbnails: true,
      });

      // Initialize .pixels folder for lineage tracking (non-blocking)
      invoke('init_workspace_command', { workspacePath: folderPath }).catch(err => {
        console.warn('Failed to init workspace state (non-critical):', err);
      });

      // Load thumbnails in background
      loadFolderThumbnails(folderPath, setState);
    } catch (err) {
      console.error('Failed to open folder:', err);
    }
  }, []);

  // Select image from folder
  const selectImage = useCallback(async (image: FolderImage) => {
    // Load full thumbnail if not loaded
    let thumbnail: string | null = image.thumbnail || null;
    if (!thumbnail) {
      thumbnail = await loadThumbnail(image.fullPath) || null;
    }

    setState(prev => ({
      ...prev,
      currentImage: { path: image.fullPath, name: image.name, thumbnail },
    }));
  }, []);

  // Close current image editor
  const closeEditor = useCallback(() => {
    setState(prev => ({
      ...prev,
      currentImage: null,
    }));
  }, []);

  // Close entire workspace
  const closeWorkspace = useCallback(() => {
    setState({
      mode: null,
      currentImage: null,
      folderImages: [],
      loadingThumbnails: false,
    });
  }, []);

  // Empty state - no workspace open
  if (state.mode === null) {
    return (
      <div className="workspace">
        <header className="workspace-header">
          <h1 className="workspace-title">Pixels Toolkit</h1>
          <div className="workspace-actions">
            <button onClick={openFolder} className="btn">Open Folder</button>
            <button onClick={openImage} className="btn">Open Image</button>
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

        <div className="workspace-empty">
          <div className="empty-content">
            <h2>No Workspace Open</h2>
            <p>Open a folder to work with multiple images, or open a single image for quick editing</p>
            <div className="empty-actions">
              <button onClick={openFolder} className="btn-primary">Open Folder</button>
              <button onClick={openImage} className="btn">Open Image</button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // Quick-edit mode (single image)
  if (state.mode === 'quick-edit' && state.currentImage) {
    return (
      <div className="workspace workspace-quick-edit">
        <header className="workspace-header">
          <h1 className="workspace-title">Pixels Toolkit</h1>
          <div className="workspace-actions">
            <button onClick={openFolder} className="btn">Open Folder</button>
            <button onClick={openImage} className="btn">Open Image</button>
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

        <ImageEditor
          imagePath={state.currentImage.path}
          imageName={state.currentImage.name}
          originalImage={state.currentImage.thumbnail}
          quickEdit={true}
          onClose={closeWorkspace}
        />
      </div>
    );
  }

  // Folder mode
  const folderPath = state.mode as string;
  const folderName = folderPath.replace(/\\/g, '/').split('/').pop() || folderPath;

  return (
    <div className="workspace workspace-folder">
      <header className="workspace-header">
        <h1 className="workspace-title">Pixels Toolkit</h1>
        <div className="workspace-actions">
          <button onClick={openFolder} className="btn">Open Folder</button>
          <button onClick={openImage} className="btn">Open Image</button>
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

      <div className="workspace-path-bar">
        <span className="workspace-label">FOLDER:</span>
        <span className="workspace-path" title={folderPath}>{folderName}</span>
        <span className="workspace-count">({state.folderImages.length} images)</span>
        <button className="btn-small" onClick={closeWorkspace}>Close</button>
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
              >
                {img.thumbnail ? (
                  <img src={img.thumbnail} alt={img.name} className="nav-thumb" />
                ) : (
                  <div className="nav-thumb-placeholder" />
                )}
                <span className="nav-name" title={img.name}>{img.name}</span>
              </button>
            ))}
            {state.folderImages.length === 0 && !state.loadingThumbnails && (
              <div className="folder-nav-empty">No images found</div>
            )}
          </div>
        </aside>

        {/* Main content - image editor or placeholder */}
        <main className="editor-area">
          {state.currentImage ? (
            <ImageEditor
              imagePath={state.currentImage.path}
              imageName={state.currentImage.name}
              originalImage={state.currentImage.thumbnail}
              quickEdit={false}
              workspacePath={folderPath}
              onClose={closeEditor}
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
    </div>
  );
}

// Helper: Load thumbnails for folder (doesn't block UI)
async function loadFolderThumbnails(
  folderPath: string,
  setState: React.Dispatch<React.SetStateAction<WorkspaceState>>
) {
  try {
    const entries = await readDir(folderPath);
    const pathSep = folderPath.includes('\\') ? '\\' : '/';
    const imageFiles: FolderImage[] = [];

    for (const entry of entries) {
      const name = entry.name.toLowerCase();
      if (
        !entry.isDirectory &&
        (name.endsWith('.png') || name.endsWith('.jpg') || name.endsWith('.jpeg') ||
         name.endsWith('.bmp') || name.endsWith('.webp'))
      ) {
        imageFiles.push({
          name: entry.name,
          fullPath: `${folderPath}${pathSep}${entry.name}`,
        });
      }
    }

    // Sort by name
    imageFiles.sort((a, b) => a.name.localeCompare(b.name));

    // Update state with file list immediately
    setState(prev => ({
      ...prev,
      folderImages: imageFiles,
    }));

    // Load thumbnails progressively (don't block)
    for (let i = 0; i < imageFiles.length; i++) {
      const img = imageFiles[i];
      try {
        const thumbnail = await loadThumbnail(img.fullPath);
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

    setState(prev => ({ ...prev, loadingThumbnails: false }));
  } catch (err) {
    console.error('Failed to load folder:', err);
    setState(prev => ({ ...prev, loadingThumbnails: false }));
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
  _folderPath: string,
  setState: React.Dispatch<React.SetStateAction<WorkspaceState>>
) {
  try {
    const newThumbnail = await loadThumbnail(filePath);
    if (newThumbnail) {
      setState(prev => ({
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
