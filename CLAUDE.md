# CLAUDE.md

This file provides guidance to Claude Code when working with this repository.

## Build & Development Commands

```bash
npm run tauri dev      # Development with hot reload
npm run tauri build    # Production build
npm run dev            # Frontend only (Vite on localhost:1420)
npm run build          # TypeScript check + Vite build
```

## Architecture Overview

**Pixels Toolkit** - Desktop image processing tool for pixel art.
- **Frontend**: React 19 + TypeScript + Vite
- **Backend**: Rust + Tauri 2
- **Database**: SQLite (project/settings persistence)

### Core Features

1. **AI Downscaler** (`downscaler.rs`): Detects true pixel grid in AI-upscaled pixel art using FFT + block variance, downscales to native resolution

2. **Post-Processor** (`processor.rs`):
   - Alpha normalization (quantize to 0 or 255)
   - LAB color clustering (merge similar colors)
   - Outline generation (frontier queue growing inward)

3. **Sprite Packer** (`packer.rs`): Combines sprites into sheet (in progress)

### Backend Structure (`src-tauri/src/`)

| File | Purpose |
|------|---------|
| `lib.rs` | Tauri command handlers, app setup |
| `downscaler.rs` | FFT grid detection, manual dimension downscale, phase-aware sampling |
| `processor.rs` | Color simplification, outline generation, outline detection |
| `packer.rs` | Sprite sheet packing |
| `db.rs` | SQLite database |
| `error.rs` | Custom error types |

### Frontend Structure (`src/`)

**Current UI (V3)** - `App.tsx` routes to `WorkspaceV3`:
- `src/components/v2/WorkspaceV3.tsx` - Main workspace container
- `src/components/v2/ImageEditor.tsx` - Universal image editing component
- `src/components/v2/Workspace.css` - All styles

**Legacy UIs** (can switch via `UI_VERSION` in App.tsx):
- V1: Tab-based (DownscaleTab, ProcessTab, PackTab)
- V2: Batch/samples UI (complex, deprecated)

### Key Tauri Commands

```typescript
// Downscaling
invoke('detect_scale_command', { inputPath }) // Returns ScaleDetectionResult
invoke('downscale_preview_command', { inputPath, targetWidth, targetHeight, autoTrim }) // Returns PNG bytes

// Processing
invoke('generate_preview_command', { inputPath, downscaleSettings, alphaSettings, mergeSettings, outlineSettings })
invoke('process_and_save_command', { inputPath, outputPath, downscaleSettings, alphaSettings, mergeSettings, outlineSettings })
invoke('detect_outline_command', { inputPath }) // Returns OutlineDetectionResult

// Workspace/Lineage
invoke('init_workspace_command', { workspacePath }) // Creates .pixels/ folder structure
invoke('backup_original_command', { workspacePath, relativePath }) // Backs up file to .pixels/cache/
```

## V3 UI Architecture

The V3 UI treats the app as an **image editor** (not a pipeline/export tool):

### Design Principles
- **Single image focus**: Edit one image at a time, no batch preview pre-loading
- **Two-step workflow**: Downscale (if AI) → Post-Process
- **Save = overwrite original** (with automatic backup to `.pixels/cache/`)
- **Pixel-level control**: Width/height adjustable by 1px for edge cases

### Components

**WorkspaceV3** (`WorkspaceV3.tsx`):
- Empty state: Open Folder / Open Image buttons
- Quick-edit mode: Single image, no folder navigation
- Folder mode: Left panel thumbnails + right editor area
- Thumbnails load progressively (no blocking)

**ImageEditor** (`ImageEditor.tsx`):
- Detects AI upscale on open (not pre-loaded)
- Step 1: Downscale (if AI detected) - pixel-level dimension controls
- Step 2: Post-Process - color merge, outline settings
- Pan (drag) + scroll zoom on previews (pan preserved when adjusting dimensions)
- Save / Save As buttons
- Loading state shows original image with "Analyzing..." badge (interactive during detection)

**PannablePreview** (inline in ImageEditor.tsx):
- `resetKey` prop controls when pan resets (only on new image, not dimension changes)
- Scroll zoom, drag pan, double-click to reset view

### Two Modes

1. **Quick-edit** (Open Image): No project, no lineage, just edit → save
2. **Folder mode** (Open Folder): Thumbnail nav on left, click to edit, auto-backup on save

## Algorithm Details

### Downscaler v4
- FFT grid detection (6-20px range)
- Phase-aware block variance search
- Valid scales: variance ≤ 2× minimum
- Prefer scale closest to FFT hint
- Manual override: `downscale_to_dimensions()` for exact target dimensions
- **Optimizations**: FFT-guided scale search (hint ±2 first), block sampling (max 400 blocks)

### Post-Processor
- **Alpha**: < 200 → 0, ≥ 200 → 255
- **Color merge**: LAB Delta E76, greedy clustering, threshold 3.0
- **Outline**: Frontier queue growing inward, color #110602, 4-way connectivity

### Outline Detection
- Scans edge pixels (opaque adjacent to transparent)
- If >80% same color → has_outline: true
- Returns detected color for UI warning

## Default Settings

```typescript
{
  alphaLowCutoff: 200,
  alphaHighMin: 200,
  mergeThreshold: 3.0,
  outlineColor: '#110602',  // (17, 6, 2)
  outlineThickness: 1,
  downscaleAutoTrim: true,
}
```

## Session Handover Notes

### Current State (Dec 2024)
- V3 UI is active (`UI_VERSION = 'v3'` in App.tsx)
- ImageEditor has two-step workflow with pixel-level dimension controls
- Pan/zoom on preview canvases works (scroll zoom, drag pan, double-click reset)
- Pan position preserved when adjusting width/height (uses `resetKey` prop)
- Folder mode loads thumbnails progressively without blocking
- No scale detection until image is opened
- Backup-on-save implemented for folder mode (`.pixels/cache/`)

### What's Working
- Single image open → detect → downscale step → post-process → save
- Folder open → thumbnail list → click to edit
- Manual downscale dimension adjustment (+/- 1px)
- Live preview with debounced updates
- Outline detection warning
- Responsive loading UI (shows interactive preview during "Analyzing...")
- Auto-backup before overwriting in folder mode

### Not Yet Implemented
- Full lineage/version history tracking (backend infrastructure exists, UI not connected)
- Bulk operations (deferred intentionally)
- Drag-and-drop file opening

### Key Files Modified (Dec 2024 Session)
- `src/components/v2/ImageEditor.tsx` - Added `resetKey` to PannablePreview, loading state UI, `workspacePath`/`onSaved` props
- `src/components/v2/WorkspaceV3.tsx` - Added workspace init, backup-on-save, thumbnail refresh after save
- `src/components/v2/Workspace.css` - Added `.analysis-status` styles
- `src-tauri/src/downscaler.rs` - FFT-guided scale search, block sampling optimization
- `src-tauri/src/lib.rs` - Added `backup_original_command`

### Architecture Decisions Made
1. **No batch preview**: Folder just shows thumbnails, processing on demand
2. **Editor-style UX**: Save/Save As like image editor, not export pipeline
3. **Lineage infrastructure ready**: Backend commands exist, full UI deferred
4. **Pixel-level control**: Users can adjust downscale by 1px for edge cases
5. **Pan preservation**: `resetKey` pattern separates image changes from preview updates
