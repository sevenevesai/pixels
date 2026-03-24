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
- **Auto-updater**: `tauri-plugin-updater` checks `seveneves.ai/pixels/updates/latest.json`

### Core Features

1. **AI Downscaler** (`downscaler.rs`): Detects true pixel grid in AI-upscaled pixel art using edge consistency + Harmonic Product Spectrum analysis, downscales to native resolution

2. **Background Removal** (`processor.rs`): Auto-detects solid-color backgrounds (magenta, green, etc.) from edge pixels, flood-fills to transparent, cleans interior enclosed areas

3. **Post-Processor** (`processor.rs`):
   - Alpha normalization (quantize to 0 or 255)
   - LAB color clustering (merge similar colors)
   - Outline generation (frontier queue growing inward)

4. **Sprite Packer** (`packer.rs`): Combines sprites into sheet (in progress)

5. **Auto-Updater** (`WorkspaceV3.tsx`): Checks for updates on launch, shows banner with install/dismiss

### Backend Structure (`src-tauri/src/`)

| File | Purpose |
|------|---------|
| `lib.rs` | Tauri command handlers, app setup, plugin registration |
| `downscaler.rs` | Edge consistency + HPS grid detection, manual dimension downscale, phase-aware sampling |
| `processor.rs` | Background removal, color simplification, outline generation, outline/background detection |
| `packer.rs` | Sprite sheet packing |
| `db.rs` | SQLite database |
| `error.rs` | Custom error types |

### Frontend Structure (`src/`)

**Current UI (V3)** - `App.tsx` routes to `WorkspaceV3`:
- `src/components/v2/WorkspaceV3.tsx` - Main workspace container + UpdateBanner component
- `src/components/v2/ImageEditor.tsx` - Universal image editing component
- `src/components/v2/types.ts` - TypeScript interfaces (ProcessingSettings, detection results)
- `src/components/v2/Workspace.css` - All styles

**Legacy UIs** (can switch via `UI_VERSION` in App.tsx):
- V1: Tab-based (DownscaleTab, ProcessTab, PackTab)
- V2: Batch/samples UI (complex, deprecated)

### Key Tauri Commands

```typescript
// Downscaling
invoke('detect_scale_command', { inputPath }) // Returns ScaleDetectionResult
invoke('downscale_preview_command', { inputPath, targetWidth, targetHeight, autoTrim, backgroundSettings }) // Returns PNG bytes

// Background Detection
invoke('detect_background_command', { inputPath }) // Returns BackgroundDetectionResult

// Processing (pipeline: bg removal → downscale → alpha → merge → outline)
invoke('generate_preview_command', { inputPath, downscaleSettings, backgroundSettings, alphaSettings, mergeSettings, outlineSettings })
invoke('process_and_save_command', { inputPath, outputPath, downscaleSettings, backgroundSettings, alphaSettings, mergeSettings, outlineSettings })
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
- `UpdateBanner` component: checks for updates 2s after launch, shows green banner

**ImageEditor** (`ImageEditor.tsx`):
- Detects AI upscale on open (not pre-loaded)
- Step 1: Downscale (if AI detected) - dimension controls + Remove Background toggle
- Step 2: Post-Process - color merge, outline settings (+ Remove BG for non-upscaled images)
- Pan (drag) + scroll zoom on previews (pan preserved when adjusting dimensions)
- Save / Save As buttons
- Loading state shows original image with "Analyzing..." badge (interactive during detection)

**PannablePreview** (inline in ImageEditor.tsx):
- `resetKey` prop controls when pan resets (only on new image, not dimension changes)
- Scroll zoom, drag pan, double-click to reset view

### Two Modes

1. **Quick-edit** (Open Image): No project, no lineage, just edit → save
2. **Folder mode** (Open Folder): Thumbnail nav on left, click to edit, auto-backup on save

## Processing Pipeline Order

The full pipeline runs in this order:
1. **Background Removal** (if enabled) — flood-fill from edges + interior scan
2. **Downscale** (if AI upscaled) — trim → detect scale → phase-aware downsample
3. **Alpha Normalization** — quantize semi-transparent to binary
4. **Color Merge** — LAB Delta E76 greedy clustering
5. **Outline Generation** — frontier queue growing inward

Background removal runs BEFORE downscale to prevent background color bleeding into sprite edge pixels during downsampling.

## Algorithm Details

### Downscaler v5
- Edge consistency profiles: fraction of rows with any color change (threshold=2) at each column
- Harmonic Product Spectrum: aggregates FFT power across harmonics of each candidate period
- Autocorrelation reinforcement as secondary signal
- Divisor preference: among candidates >80% of max score, picks smallest (fundamental)
- Scale range: 4-20px
- Phase search via block variance minimization (coarse + fine)
- Manual override: `downscale_to_dimensions()` for exact target dimensions

### Background Removal
- **Detection** (`detect_background`): Samples all 4 edge borders, finds dominant color cluster (RGB distance ≤ 15), reports if >50% match
- **Removal** (`remove_background`): BFS flood-fill from edges (tolerance default 30), then interior scan removes ALL remaining matching pixels (catches enclosed areas), then edge cleanup pass (tolerance 20) for anti-aliasing
- Settings: `BackgroundSettings { tolerance: u8 }` (default 30, UI range 10-60)

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
  backgroundEnabled: false,   // Opt-in
  backgroundTolerance: 30,    // RGB distance
  alphaLowCutoff: 200,
  alphaHighMin: 200,
  mergeThreshold: 3.0,
  outlineColor: '#110602',    // (17, 6, 2)
  outlineThickness: 1,
  downscaleAutoTrim: true,
}
```

## Auto-Updater

- Plugin: `tauri-plugin-updater` + `tauri-plugin-process`
- Endpoint: `https://seveneves.ai/pixels/updates/latest.json`
- Signing: minisign keypair (`src-tauri/.tauri-private-key` — gitignored, stored in GitHub Secrets)
- Public key: embedded in `tauri.conf.json`
- CI: GitHub Actions builds + signs on tag push (`v*`), creates draft release
- Update flow: app checks endpoint → compares version → downloads + verifies signature → installs + relaunches

### Release Process
1. Bump version in `tauri.conf.json` + `Cargo.toml` + `package.json`
2. Commit and push tag: `git tag v1.x.0 && git push origin main v1.x.0`
3. CI builds all platforms, signs, creates draft GitHub Release
4. Download artifacts: `gh release download v1.x.0 --pattern "*.sig" --pattern "*.tar.gz" --pattern "*.nsis.zip" --pattern "*.msi.zip" --pattern "latest.json" -D public_html/pixels/updates/`
5. Download installers: `gh release download v1.x.0 --pattern "*.msi" --pattern "*.dmg" --pattern "*.AppImage" --pattern "*.deb" -D public_html/pixels/downloads/`
6. Update `sevenevesai/public_html/pixels/releases/releases.json` with new version entry
7. Update download links in `sevenevesai/public_html/pixels/index.html`
8. Deploy: `scp` changed files to `seveneves:~/public_html/pixels/`
9. Publish GitHub Release from draft

## Session Handover Notes

### Current State (v1.1.0 — Mar 2026)
- V3 UI is active (`UI_VERSION = 'v3'` in App.tsx)
- Downscaler v5 algorithm (edge consistency + HPS) replaces v4 (FFT + block variance)
- Background removal feature added (auto-detect + flood-fill + interior removal)
- Auto-updater configured and working (checks seveneves.ai on launch)
- CI pipeline builds + signs for all platforms on tag push
- Website updated: landing page v1.1.0 links, release notes page, update endpoint

### What's Working
- Full pipeline: bg removal → downscale → alpha → merge → outline
- Background removal in Step 1 (downscale step) for AI-upscaled images
- Background removal in Step 2 (post-process) for non-upscaled images
- Auto-updater with green banner + install/dismiss buttons
- Signed builds via GitHub Actions
- Release notes page at seveneves.ai/pixels/releases/
- Cross-platform: Windows (MSI/NSIS), macOS (DMG x3), Linux (AppImage/deb)

### Not Yet Implemented
- Full lineage/version history tracking (backend infrastructure exists, UI not connected)
- Bulk operations (deferred intentionally)
- Drag-and-drop file opening
- Manual background color picker (override auto-detection)

### Key Files Modified (Mar 2026 Session)
- `src-tauri/src/downscaler.rs` - Complete rewrite: v5 algorithm (edge consistency + HPS + autocorrelation)
- `src-tauri/src/processor.rs` - Added BackgroundSettings, BackgroundDetectionResult, detect_background(), remove_background()
- `src-tauri/src/lib.rs` - Added detect_background_command, background_settings param to preview/save commands, registered updater + process plugins
- `src-tauri/tauri.conf.json` - Added updater config (endpoint, pubkey), createUpdaterArtifacts
- `src-tauri/Cargo.toml` - Added tauri-plugin-updater, tauri-plugin-process, bumped to v1.1.0
- `src/components/v2/ImageEditor.tsx` - Background removal toggle in Step 1 + Step 2, updated preview/save to pass backgroundSettings
- `src/components/v2/WorkspaceV3.tsx` - Added UpdateBanner component with check/install/dismiss
- `src/components/v2/types.ts` - Added BackgroundDetectionResult, backgroundEnabled/backgroundTolerance to ProcessingSettings
- `src/components/v2/Workspace.css` - Added .update-banner, .info-banner styles
- `.github/workflows/build.yml` - Added TAURI_SIGNING_PRIVATE_KEY, NSIS bundle, updated tauri-action env
- `.gitignore` - Added src-tauri/.tauri-private-key

### Architecture Decisions Made
1. **No batch preview**: Folder just shows thumbnails, processing on demand
2. **Editor-style UX**: Save/Save As like image editor, not export pipeline
3. **Lineage infrastructure ready**: Backend commands exist, full UI deferred
4. **Pixel-level control**: Users can adjust downscale by 1px for edge cases
5. **Pan preservation**: `resetKey` pattern separates image changes from preview updates
6. **BG removal before downscale**: Prevents background color bleeding into sprite edges during sampling
7. **BG removal UI placement**: In Step 1 for upscaled images, Step 2 for non-upscaled
8. **Auto-updater hosted on own domain**: latest.json on seveneves.ai, binaries on GitHub CDN
9. **Signing without password**: Key stored in GitHub Secrets, no TAURI_SIGNING_PRIVATE_KEY_PASSWORD env var
