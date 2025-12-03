// V2 Types for Workspace UI

export interface SourceImage {
  /** Relative path from workspace root */
  relativePath: string;
  /** Full absolute path */
  fullPath: string;
  /** Filename only */
  name: string;
  /** Base64 thumbnail data URL */
  thumbnail?: string;
  /** Processing status */
  status: 'pending' | 'processing' | 'processed' | 'error';
  /** Error message if status is 'error' */
  error?: string;
  /** Detected image type */
  detectedType?: 'ai_upscaled' | 'native_pixel_art' | 'unknown';
  /** Detected upscale factor (if AI-upscaled) */
  detectedScale?: number;
  /** Current version ID in lineage */
  currentVersion?: string;
}

export interface ProcessingSettings {
  // Downscale (applied first) - for auto mode
  downscaleEnabled: boolean;
  downscaleAutoTrim: boolean;
  // Manual target dimensions (if set, overrides auto-detection)
  downscaleTargetWidth: number | null;
  downscaleTargetHeight: number | null;

  // Alpha normalization
  alphaEnabled: boolean;
  alphaLowCutoff: number;
  alphaHighMin: number;

  // Color merge
  mergeEnabled: boolean;
  mergeThreshold: number;

  // Outline
  outlineEnabled: boolean;
  outlineColor: string; // hex color
  outlineThickness: number;
}

/** State for the downscale step in one-off mode */
export interface DownscaleState {
  /** Original image dimensions */
  originalWidth: number;
  originalHeight: number;
  /** Auto-detected scale factor */
  detectedScale: number;
  /** Auto-detected target dimensions */
  detectedWidth: number;
  detectedHeight: number;
  /** User-adjusted target dimensions */
  targetWidth: number;
  targetHeight: number;
  /** Whether to auto-trim before downscaling */
  autoTrim: boolean;
  /** Whether downscale step is confirmed/locked */
  confirmed: boolean;
  /** Whether currently generating preview */
  previewLoading: boolean;
  /** Preview image data URL */
  previewData: string | null;
}

export const DEFAULT_SETTINGS: ProcessingSettings = {
  downscaleEnabled: true,  // Auto-enabled, will only apply if AI-upscaled detected
  downscaleAutoTrim: true,
  downscaleTargetWidth: null,  // null = use auto-detection
  downscaleTargetHeight: null, // null = use auto-detection

  alphaEnabled: true,
  alphaLowCutoff: 200,
  alphaHighMin: 200,

  mergeEnabled: true,
  mergeThreshold: 3.0,

  outlineEnabled: true,
  outlineColor: '#110602',
  outlineThickness: 1,
};

/** Result from detect_scale_command */
export interface ScaleDetectionResult {
  detected_scale: number;
  grid_detected: boolean;
  confidence: number;
  is_ai_upscaled: boolean;
  dimensions: [number, number];
  estimated_native_size: [number, number];
}

export type WorkspaceMode = 'folder' | 'single-file';

export interface WorkspaceState {
  /** Workspace mode - folder batch or single file quick process */
  mode: WorkspaceMode;
  /** Workspace root directory */
  workspacePath: string | null;
  /** All source images */
  sources: SourceImage[];
  /** Currently focused image index */
  focusedIndex: number | null;
  /** Selected image indices (for batch operations) */
  selectedIndices: Set<number>;
  /** Global processing settings */
  settings: ProcessingSettings;
  /** Sample image indices for preview row */
  sampleIndices: number[];
  /** Is currently processing */
  isProcessing: boolean;
  /** Processing progress message */
  progressMessage: string;
}

export interface OutlineDetectionResult {
  has_outline: boolean;
  outline_color: [number, number, number, number] | null;
  confidence: number;
  edge_pixel_count: number;
}

export interface MergeResult {
  unique_colors_before: number;
  unique_colors_after: number;
  clusters_created: number;
}

// Utility to convert hex to RGBA tuple
export function hexToRgba(hex: string): [number, number, number, number] {
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return [r, g, b, 255];
}

// Utility to convert RGBA tuple to hex
export function rgbaToHex(rgba: [number, number, number, number]): string {
  const [r, g, b] = rgba;
  return `#${r.toString(16).padStart(2, '0')}${g.toString(16).padStart(2, '0')}${b.toString(16).padStart(2, '0')}`;
}

// ============================================================================
// BACKEND STATE TYPES (match src-tauri/src/state.rs)
// ============================================================================

export type VersionType = 'original' | 'downscaled' | 'post_processed';
export type SourceType = 'ai_upscaled' | 'native_pixel_art' | 'unknown';

export interface PostProcessSettings {
  alpha_enabled: boolean;
  alpha_low_cutoff: number | null;
  alpha_high_min: number | null;
  merge_enabled: boolean;
  merge_threshold: number | null;
  outline_enabled: boolean;
  outline_color: [number, number, number, number] | null;
  outline_thickness: number | null;
}

export interface DownscaleSettings {
  detected_scale: number;
  auto_trim: boolean;
  pad_canvas: number | null;
}

export interface ImageVersion {
  id: string;
  version_type: VersionType;
  cache_path: string | null;
  parent: string | null;
  post_process_settings?: PostProcessSettings;
  downscale_settings?: DownscaleSettings;
  created: string;
}

export interface SourceState {
  hash: string;
  detected_type: SourceType;
  detected_scale: number | null;
  versions: ImageVersion[];
  current_version: string;
}

export interface GlobalSettings {
  merge_threshold: number;
  outline_color: [number, number, number, number];
  outline_thickness: number;
}

export type ExportNaming = 'same' | { suffix: string };

export interface ExportSettings {
  destination: string | null;
  naming: ExportNaming;
}

export interface BackendWorkspaceState {
  version: number;
  workspace: string;
  sources: Record<string, SourceState>;
  globalSettings: GlobalSettings;
  exportSettings: ExportSettings;
}
