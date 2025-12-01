# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Build & Development Commands

```bash
# Development (Tauri app with hot reload)
npm run tauri dev

# Build production app
npm run tauri build

# Frontend only
npm run dev          # Vite dev server on localhost:1420
npm run build        # TypeScript check + Vite build
```

## Architecture Overview

**Pixels Toolkit** is a desktop image processing tool for pixel art, built with:
- **Frontend**: React 19 + TypeScript + Vite
- **Backend**: Rust + Tauri 2
- **Database**: SQLite (project/settings persistence)

### Three Main Features

1. **AI Downscaler** (`downscaler.rs`): Detects true pixel grid in AI-generated upscaled pixel art using FFT analysis and block variance with phase search, then downscales to actual resolution

2. **Post-Processor** (`processor.rs`): Three-step pipeline:
   - Alpha normalization (quantize to 0 or 255)
   - LAB color space clustering (merge similar colors)
   - Outline generation (frontier queue growing inward)

3. **Sprite Packer** (`packer.rs`): Combines sprites into sheet with metadata export

### Backend Structure (`src-tauri/src/`)

| File | Purpose |
|------|---------|
| `lib.rs` | Tauri command handlers, app setup, database init |
| `downscaler.rs` | FFT grid detection, phase-aware downsampling |
| `processor.rs` | Color simplification, outline generation |
| `packer.rs` | Sprite sheet packing algorithm |
| `db.rs` | SQLite database, project/settings CRUD |
| `error.rs` | Custom error types with Tauri serialization |

### Frontend Structure (`src/`)

`App.tsx` contains the entire UI with three tab components:
- `DownscaleTab`: Input/output folder selection, image grid, downscale processing
- `ProcessTab`: Color merge settings, outline settings, batch processing
- `PackTab`: Sprite sheet generation (in progress)

### Data Flow

1. Frontend calls Tauri commands via `invoke()`
2. Commands in `lib.rs` delegate to processing modules
3. Heavy operations run in `tokio::task::spawn_blocking`
4. Results/errors serialized back to frontend

### Key Technical Details

- Dev mode uses `opt-level = 2` for performance (Cargo.toml)
- Settings persist per-project in SQLite
- Image processing uses `image`, `imageproc`, `rustfft`, `palette` crates
- Frontend reads files via `@tauri-apps/plugin-fs` for thumbnails

## Algorithm Details

### Downscaler v4 Algorithm

The downscaler detects the true pixel grid in AI-upscaled pixel art. Key insight: **smaller scales always have lower variance** (more averaging), so we can't just pick minimum variance.

**Solution (v4)**:
1. FFT grid detection on edge profiles (looks for periodic patterns in 6-20px range)
2. For each candidate scale 6-20, find best phase offset via block variance search
3. Find all "valid" scales where variance ≤ 2× minimum variance
4. Among valid scales, prefer the one closest to FFT hint (or largest if no hint)
5. Downsample using phase-aware center-pixel sampling

Settings are minimal: `auto_trim` (trim transparent borders) and `pad_canvas` (pad to multiple). Background removal was intentionally removed - images should already have transparent backgrounds.

### Post-Processor Algorithm (ported from Python)

**1. Opacity Normalization** (lines match `legacy/pyapp-1.3/core/image_processor.py:77-89`):
- Alpha < 200 → 0 (fully transparent)
- Alpha 200-255 → 255 (fully opaque)

**2. LAB Color Clustering** (matches Python lines 91-149):
- Collect unique colors with frequency counts
- Sort by frequency descending (most common first)
- Greedy first-fit assignment: each color joins nearest cluster within Delta E76 threshold
- Cluster centers are weighted averages updated incrementally
- Default threshold: 3.0 (lower = more aggressive merging)

**3. Outline Generation** (matches Python lines 151-202):
- Uses **frontier queue** algorithm, NOT mask-based dilation
- Find all border pixels (opaque pixels adjacent to transparent)
- Grow inward: add neighbors of frontier that are opaque and not yet in mask
- Repeat for thickness iterations
- Default color: `(17, 6, 2, 255)` - dark brown (#110602)

### Optimal Default Settings

From testing the legacy Python app, these defaults work best:
- `alpha_low_cutoff: 200`, `alpha_high_min: 200`
- `lab_merge_threshold: 3.0`
- `outline_color: (17, 6, 2, 255)`
- `outline_connectivity: four` (4-way neighbors)
- `outline_thickness: 1`

## Legacy Code Reference

The `legacy/` folder contains the original Python implementation (`pyapp-1.3/`). Key files:
- `core/image_processor.py` - Post-processing algorithms (ported to `processor.rs`)
- `settings_manager.py` - Default settings values

## Testing

Test images are in `downscale_tests/`:
- `input/` - Source images for testing
- `output/` - Rust algorithm output
- `expected/` - Expected results
- `scripts/` - Python reference implementations (e.g., `block_uniformity.py` for v4 algorithm)

---

# V2 UI/UX REDESIGN SPECIFICATION

## Overview

The v2 redesign addresses usability issues with the current tab-based UI. The goal is a unified workspace that supports both quick one-off processing and bulk project workflows with live preview and iterative processing.

## Core Design Principles

1. **Simplicity first** - Optimize for the 80% use case, hide complexity for advanced users
2. **App-managed state** - Internal folder structure serves the app, user sees clean UI
3. **Branch-based lineage** - Any processed image can spawn new versions from its parent
4. **Two modes, one interface** - Quick one-off and project batch feel like the same tool
5. **Preview-driven confidence** - See results before committing to batch operations

## User Personas

### Persona 1: "Alex" - AI Pixel Art Generator
- Uses AI tools (Midjourney, Stable Diffusion, PixelLab) to generate pixel art
- Generates 20-100 images per session
- Needs: Downscale to true resolution, clean up colors, add consistent outlines
- Workflow: Bulk processing, occasionally tweak individual problem images

### Persona 2: "Jordan" - Traditional Pixel Artist
- Creates pixel art manually in Aseprite/Photoshop
- Wants batch operations for polish passes (add outlines, unify palette)
- Workflow: Import existing sprites → apply outline pass → possibly re-color outlines for variants

### Persona 3: "Sam" - Game Dev (Non-Artist)
- Programmer sourcing art from multiple places (AI, purchases, commissions)
- Needs visual consistency across diverse assets
- Workflow: Dump assets → make them cohesive → export and move on

### Persona 4: "River" - Asset Pack Creator
- Creates and sells sprite packs
- Needs multiple variants per sprite (different outline styles, color depths)
- Workflow: Create master → generate variants → export all with systematic naming

## Architectural Decisions

### Decision 1: Decompose Post-Processing into Separate Operations

**Decision**: Decompose the monolithic `process_image` into independent operations.

**Rationale**: Iterative processing (applying post-process multiple times) requires selective operations. Users may want to apply just outline, or just merge, not always both.

**New Operations**:
```rust
normalize_alpha(image, settings) -> image
merge_colors(image, threshold) -> image
add_outline(image, color, thickness, connectivity) -> image
```

Each operation must be safe to re-apply or detect when re-application would cause issues.

### Decision 2: Outline Detection and Warning

**Decision**: Detect existing outlines before applying new ones. Warn user if outline detected.

**Rationale**: Applying outline to already-outlined image creates double-outline artifacts. Detection prevents accidental corruption.

**Implementation**:
- Before `add_outline`, scan edge pixels
- If edge pixels match a solid color pattern (potential existing outline), warn
- User can proceed anyway or skip
- Architecture should support future "replace outline" feature

### Decision 3: Color Merge is Re-applicable

**Decision**: Allow color merge to be applied multiple times without warning.

**Rationale**: Progressive simplification is a valid use case ("merge more"). Re-merging already-merged images may have minimal effect but won't corrupt.

### Decision 4: Hidden Internal State Management

**Decision**: App manages processing state in hidden `.pixels/` folder structure.

**Structure**:
```
.pixels/                          # Hidden app data folder
├── cache/                        # Processed versions
│   ├── {hash}_ds.png            # Downscaled version
│   ├── {hash}_pp_v1.png         # Post-processed v1
│   ├── {hash}_pp_v2.png         # Post-processed v2 (branch)
│   └── ...
├── thumbnails/                   # Quick-load previews
└── state.json                    # Lineage tree, settings per version
```

**Rationale**: Users see only source images and exported outputs. History/lineage is preserved without cluttering their folders. Supports rollback and branching without explicit file management.

### Decision 5: Working State vs Export Separation

**Decision**: Separate "working/preview" from "export to disk".

**Rationale**: Users can iterate freely without cluttering folders. When ready, explicit export to chosen location with naming control.

**Flow**:
1. Import/open images (source files remain untouched)
2. Apply operations (results stored in `.pixels/cache/`)
3. Preview and iterate
4. Export when satisfied (writes to user-specified destination)

## UI Layout Specification

### Main Workspace Layout

```
┌──────────────────────────────────────────────────────────────────────────┐
│ Pixels Toolkit                    [Open Folder] [Open Image]    [⚙] [?] │
├──────────────────────────────────────────────────────────────────────────┤
│ WORKSPACE: C:/Game/Sprites (47)                    [↻ Refresh] [Export] │
├────────────────┬─────────────────────────────────────┬───────────────────┤
│ SOURCES        │ PREVIEW                             │ PROCESS           │
│                │                                     │                   │
│ [Filter ▼ All] │ ┌───────────────┐ ┌───────────────┐│ ┌───────────────┐ │
│                │ │               │ │               ││ │ SOURCE        │ │
│ ┌────────────┐ │ │   Original    │ │   Current     ││ │ wizard.png    │ │
│ │ wizard  ●  │ │ │   (parent)    │ │   (preview)   ││ │ 512×512 (AI)  │ │
│ │ knight  ●  │ │ └───────────────┘ └───────────────┘│ │ → 64×64       │ │
│ │ tree    ○  │ │      [Split] [Swap] [1:1] [4x] [8x]│ └───────────────┘ │
│ │ chest   ●  │ │                                     │                   │
│ │ ...        │ │ ─────────────────────────────────── │ ┌───────────────┐ │
│ └────────────┘ │ SAMPLE                  [Edit Sample]│ │ LINEAGE       │ │
│                │ ┌──┐ ┌──┐ ┌──┐ ┌──┐               │ │ ○ Original    │ │
│ ● = processed  │ │● │ │● │ │○ │ │● │               │ │ ○ Downscaled  │ │
│ ○ = pending    │ └──┘ └──┘ └──┘ └──┘               │ │ ● Current ←   │ │
│                │  wiz  kni  tree ches               │ │ [+ Branch]    │ │
│ [Select All]   │                                     │ └───────────────┘ │
│ [Select None]  │                                     │                   │
│                │                                     │ ┌───────────────┐ │
│                │                                     │ │ SETTINGS      │ │
│                │                                     │ │               │ │
│                │                                     │ │ Color Merge   │ │
│                │                                     │ │ [■] [━━●━━] 3 │ │
│                │                                     │ │               │ │
│                │                                     │ │ Outline       │ │
│                │                                     │ │ [■] #110602   │ │
│                │                                     │ │ [━●━━━━━] 1px │ │
│                │                                     │ └───────────────┘ │
│                │                                     │                   │
│                │                                     │ [▶ Apply]         │
│                │                                     │ [▶ Apply to All]  │
└────────────────┴─────────────────────────────────────┴───────────────────┘
```

### Panel Descriptions

**Sources Panel (Left)**:
- List of source images in workspace
- Status indicator: `●` processed, `○` pending
- Click to focus in preview
- Multi-select for batch operations (Ctrl+click, Shift+click)
- Filter dropdown: All / Pending / Processed

**Preview Panel (Center)**:
- Dual pane: Original/parent vs Current settings preview
- Comparison controls: Split view, Swap sides, Zoom levels
- Integer scaling for pixel art (1:1, 4x, 8x, fit)
- Pixel grid overlay toggle
- Sample row: 4-6 images showing live thumbnails as settings change
- Click sample to make it main preview
- `[Edit Sample]` to choose which images appear in sample

**Process Panel (Right)**:
- Source info: Filename, dimensions, detected type (AI-upscaled vs native)
- Lineage tree: Visual representation of this image's version history
  - Click any node to view that version
  - `[+ Branch]` creates new version from selected node
- Settings: Toggle-able operations with controls
  - Each operation (merge, outline) has enable checkbox
  - Settings only shown when operation enabled
- Actions:
  - `[Apply]` - Process focused image with current settings
  - `[Apply to All]` - Process all selected/pending images

### One-Off Mode Layout

When opening a single image file (not folder):

```
┌──────────────────────────────────────────────────────────────────────┐
│ Pixels Toolkit - Quick Process                             [✕ Close] │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│   ┌────────────────────┐       ┌────────────────────┐               │
│   │                    │       │                    │               │
│   │     Original       │  ───► │     Preview        │               │
│   │     512×512        │       │      64×64         │               │
│   │                    │       │                    │               │
│   └────────────────────┘       └────────────────────┘               │
│                        [1:1] [4x] [8x] [Grid]                        │
│                                                                      │
│   ───────────────────────────────────────────────────────────────── │
│   Color Merge: [■] [━━━●━━━] 3.0    Outline: [■] #110602 [━●━] 1px  │
│   ───────────────────────────────────────────────────────────────── │
│                                                                      │
│   Save as: [wizard_processed.png    ] [Browse]                       │
│                                                                      │
│                            [Save] [Save & Close]                     │
└──────────────────────────────────────────────────────────────────────┘
```

- Compact, focused interface
- No project overhead
- Default save: same folder, `_processed` suffix
- Live preview as settings change

### Export Dialog

```
┌─────────────────────────────────────────────────────────────┐
│ EXPORT                                               [✕]    │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Export: ○ All processed (47)                               │
│          ● Selected only (12)                               │
│          ○ Pending only (0)                                 │
│                                                             │
│  ─────────────────────────────────────────────────────────  │
│                                                             │
│  Destination: [C:/Game/Sprites/final      ] [Browse]        │
│                                                             │
│  Naming: ● Same as source (overwrite if exists)             │
│          ○ Add suffix: [_processed    ]                     │
│                                                             │
│                                    [Cancel]  [Export 12]    │
└─────────────────────────────────────────────────────────────┘
```

## Key Workflows

### Workflow 1: Bulk AI Art Processing (Alex)

1. `[Open Folder]` → select folder with AI-generated images
2. App auto-detects which images need downscaling
3. Sample preview shows 4-6 representative images
4. Adjust settings, watch samples update live
5. `[Apply to All]` → batch processes everything
6. `[Export]` → choose destination, export all

### Workflow 2: Edge Case Handling (Tree Problem)

1. Processing batch of 50 sprites
2. Notice tree looks wrong in sample preview
3. Click tree in sources list
4. Lineage shows: Original → Downscaled → Current (bad)
5. Click "Downscaled" in lineage
6. Click `[+ Branch]`
7. Adjust settings (disable outline for tree)
8. `[Apply]` → creates new branch just for tree
9. Other 49 sprites remain unchanged

### Workflow 3: Quick One-Off Test (Alex)

1. Download new AI-generated image
2. Drag onto app (or `[Open Image]`)
3. One-off mode opens
4. See preview instantly, tweak if needed
5. `[Save & Close]`

### Workflow 4: Iterative Refinement (Jordan)

1. Open folder of existing pixel art (no downscaling needed)
2. Apply outline pass to batch
3. Later, select specific sprites
4. Click current version in lineage
5. `[+ Branch]` → change outline color
6. Apply → now has two variants (original outline, new outline)
7. Export both or just preferred one

## Migration: What Changes

| Current (v1) | New (v2) |
|--------------|----------|
| 3 separate tabs (Downscale, Process, Pack) | Unified workspace, pipeline is automatic |
| Input folder + Output folder per tab | One workspace, one export destination |
| No preview of results | Live dual-pane preview + sample thumbnails |
| No lineage/history | Branch-based versioning with visual tree |
| Bulk-only focus | Both one-off and bulk feel natural |
| Settings → Process → Discover results | Settings → See live → Confident batch |
| Monolithic post-process pipeline | Decomposed, selective operations |
| Files written during "process" | Files written only during "export" |

## Implementation Phases

### Phase 1: Backend Refactoring

**Goal**: Decompose processor, add state management infrastructure.

**Tasks**:
1. Split `processor.rs` into separate operations:
   - `normalize_alpha(image, settings) -> image`
   - `merge_colors(image, threshold) -> image`
   - `add_outline(image, color, thickness, connectivity) -> image`
2. Add outline detection function (for warnings)
3. Create new Tauri commands for individual operations
4. Design and implement `state.json` schema for lineage tracking
5. Implement `.pixels/` folder management (create, read, write)
6. Add image hashing for cache keys

**Files to modify**: `processor.rs`, `lib.rs`
**New files**: `state.rs` (lineage/state management)

### Phase 2: New UI Shell

**Goal**: Build new layout structure without full functionality.

**Tasks**:
1. Create new component structure:
   - `Workspace.tsx` - main container
   - `SourcesPanel.tsx` - left sidebar
   - `PreviewPanel.tsx` - center area
   - `ProcessPanel.tsx` - right sidebar
2. Implement basic layout with CSS Grid/Flexbox
3. Source list with mock data
4. Settings controls (non-functional initially)
5. Remove old tab-based UI

**Files to modify**: `App.tsx`, `App.css`
**New files**: Component files in `src/components/`

### Phase 3: Core Functionality

**Goal**: Wire up preview and processing.

**Tasks**:
1. Implement source loading from folder
2. Wire settings controls to state
3. Implement single-image preview (before/after)
4. Implement `[Apply]` for single image
5. Implement lineage display (read from state)
6. Implement `[+ Branch]` functionality

### Phase 4: Live Preview

**Goal**: Settings changes reflect immediately in preview.

**Tasks**:
1. Debounced preview generation on settings change
2. Sample thumbnails row with live updates
3. Sample selection/editing
4. Preview zoom and comparison modes

### Phase 5: Batch Operations

**Goal**: Apply to All and batch selection.

**Tasks**:
1. Multi-select in sources panel
2. `[Apply to All]` with progress indicator
3. Per-image override detection (for edge cases)
4. Batch status tracking

### Phase 6: One-Off Mode

**Goal**: Streamlined single-file interface.

**Tasks**:
1. Detect single-file open vs folder open
2. One-off layout component
3. Direct save (bypass export dialog)
4. Auto-detect and auto-apply downscaling

### Phase 7: Export System

**Goal**: Explicit export with controls.

**Tasks**:
1. Export dialog component
2. Destination selection
3. Naming options
4. Batch export with progress

### Phase 8: Polish

**Goal**: Edge cases, UX refinement.

**Tasks**:
1. Auto-detection of AI-upscaled vs native pixel art
2. Keyboard shortcuts
3. Drag-and-drop support
4. Error handling and user feedback
5. Dark mode consistency
6. Performance optimization for large batches

## State Schema (state.json)

```json
{
  "version": 1,
  "workspace": "C:/Game/Sprites",
  "sources": {
    "wizard.png": {
      "hash": "abc123",
      "detected_type": "ai_upscaled",
      "detected_scale": 8,
      "versions": [
        {
          "id": "v1",
          "type": "original",
          "cache_path": null,
          "parent": null,
          "created": "2024-01-15T10:30:00Z"
        },
        {
          "id": "v2",
          "type": "downscaled",
          "cache_path": "cache/abc123_ds.png",
          "parent": "v1",
          "settings": { "auto_trim": true },
          "created": "2024-01-15T10:31:00Z"
        },
        {
          "id": "v3",
          "type": "post_processed",
          "cache_path": "cache/abc123_pp_v1.png",
          "parent": "v2",
          "settings": {
            "merge_enabled": true,
            "merge_threshold": 3.0,
            "outline_enabled": true,
            "outline_color": [17, 6, 2, 255],
            "outline_thickness": 1
          },
          "created": "2024-01-15T10:32:00Z"
        }
      ],
      "current_version": "v3"
    }
  },
  "global_settings": {
    "merge_threshold": 3.0,
    "outline_color": [17, 6, 2, 255],
    "outline_thickness": 1
  },
  "export_settings": {
    "destination": "C:/Game/Sprites/final",
    "naming": "same"
  }
}
```

## Critical Implementation Notes

### Outline Detection Algorithm

Before applying outline, detect if image already has outline:
1. Find all edge pixels (opaque pixels adjacent to transparent)
2. Check if edge pixels are uniform or near-uniform color
3. If >80% of edge pixels are same color (within small Delta E), likely has outline
4. Return: `{ has_outline: bool, outline_color: Option<RGBA> }`

### Preview Performance

Live preview must be fast:
- Debounce settings changes (100-200ms)
- Process at reduced resolution for preview if image is large
- Cache intermediate results (downscaled version doesn't change when adjusting outline)
- Use web workers or Tauri background threads

### Thumbnail Generation

For sample row:
- Generate thumbnails at fixed size (e.g., 64x64)
- Store in `.pixels/thumbnails/`
- Update only when settings change (debounced)
- Show loading state during generation

## Future Considerations (Not in v2)

These features should be architecturally possible but not implemented yet:

1. **Presets/Recipes** - Named setting combinations ("Bold", "Minimal", "Standard")
2. **Variant batch export** - Export multiple variants per source with naming scheme
3. **Target palette merging** - Merge colors to specific target palette
4. **Outline replacement** - Detect and replace existing outline color
5. **Auto-detection confidence** - Show confidence score for AI-upscaled detection
6. **Sprite sheet packing** - Integrate Pack functionality into workflow
