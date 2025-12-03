// V2 Workspace State Hook
import { useState, useCallback, useEffect, useRef } from 'react';
import { invoke } from '@tauri-apps/api/core';
import { open } from '@tauri-apps/plugin-dialog';
import { readDir, readFile } from '@tauri-apps/plugin-fs';
import {
  WorkspaceState,
  SourceImage,
  ProcessingSettings,
  DEFAULT_SETTINGS,
  OutlineDetectionResult,
  ScaleDetectionResult,
  hexToRgba,
} from './types';

const INITIAL_STATE: WorkspaceState = {
  mode: 'folder',
  workspacePath: null,
  sources: [],
  focusedIndex: null,
  selectedIndices: new Set(),
  settings: DEFAULT_SETTINGS,
  sampleIndices: [],
  isProcessing: false,
  progressMessage: '',
};

// Debounce delay for preview generation (ms)
const PREVIEW_DEBOUNCE_MS = 300;
// Debounce delay for sample previews (slightly longer to reduce load)
const SAMPLE_PREVIEW_DEBOUNCE_MS = 500;

export function useWorkspace() {
  const [state, setState] = useState<WorkspaceState>(INITIAL_STATE);

  // Preview state (separate for performance)
  const [previewData, setPreviewData] = useState<string | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [outlineWarning, setOutlineWarning] = useState<OutlineDetectionResult | null>(null);

  // Sample previews state (map of index -> preview data URL)
  const [samplePreviews, setSamplePreviews] = useState<Map<number, string>>(new Map());
  const [samplePreviewsLoading, setSamplePreviewsLoading] = useState(false);

  // Debounce timer refs
  const previewTimerRef = useRef<number | null>(null);
  const samplePreviewTimerRef = useRef<number | null>(null);

  // Generate preview when settings or focused image changes
  const generatePreview = useCallback(async (
    source: SourceImage,
    settings: ProcessingSettings
  ) => {
    setPreviewLoading(true);
    try {
      const [r, g, b, a] = hexToRgba(settings.outlineColor);

      // Only apply downscale if enabled AND image is detected as AI-upscaled
      const downscaleSettings = (settings.downscaleEnabled && source.detectedType === 'ai_upscaled') ? {
        enabled: true,
        auto_trim: settings.downscaleAutoTrim,
        // Use manual dimensions if set, otherwise auto-detect
        target_width: settings.downscaleTargetWidth || undefined,
        target_height: settings.downscaleTargetHeight || undefined,
      } : null;

      const alphaSettings = settings.alphaEnabled ? {
        low_cutoff: settings.alphaLowCutoff,
        high_min: settings.alphaHighMin,
        high_max: 255,
      } : null;

      const mergeSettings = settings.mergeEnabled ? {
        threshold: settings.mergeThreshold,
      } : null;

      const outlineSettings = settings.outlineEnabled ? {
        color: [r, g, b, a],
        connectivity: 'four',
        thickness: settings.outlineThickness,
        edge_transparent_cutoff: 0,
      } : null;

      const pngBytes = await invoke<number[]>('generate_preview_command', {
        inputPath: source.fullPath,
        downscaleSettings,
        alphaSettings,
        mergeSettings,
        outlineSettings,
      });

      // Convert byte array to base64 data URL
      const uint8Array = new Uint8Array(pngBytes);
      const base64 = btoa(
        uint8Array.reduce((data, byte) => data + String.fromCharCode(byte), '')
      );
      setPreviewData(`data:image/png;base64,${base64}`);
    } catch (err) {
      console.error('Preview generation failed:', err);
      setPreviewData(null);
    } finally {
      setPreviewLoading(false);
    }
  }, []);

  // Debounced preview generation
  const requestPreview = useCallback((source: SourceImage, settings: ProcessingSettings) => {
    // Clear existing timer
    if (previewTimerRef.current) {
      clearTimeout(previewTimerRef.current);
    }

    // Set new timer
    previewTimerRef.current = window.setTimeout(() => {
      generatePreview(source, settings);
    }, PREVIEW_DEBOUNCE_MS);
  }, [generatePreview]);

  // Generate sample previews for all sample indices
  const generateSamplePreviews = useCallback(async (
    sources: SourceImage[],
    indices: number[],
    settings: ProcessingSettings
  ) => {
    if (indices.length === 0) return;

    setSamplePreviewsLoading(true);
    const newPreviews = new Map<number, string>();

    try {
      const [r, g, b, a] = hexToRgba(settings.outlineColor);

      const alphaSettings = settings.alphaEnabled ? {
        low_cutoff: settings.alphaLowCutoff,
        high_min: settings.alphaHighMin,
        high_max: 255,
      } : null;

      const mergeSettings = settings.mergeEnabled ? {
        threshold: settings.mergeThreshold,
      } : null;

      const outlineSettings = settings.outlineEnabled ? {
        color: [r, g, b, a],
        connectivity: 'four',
        thickness: settings.outlineThickness,
        edge_transparent_cutoff: 0,
      } : null;

      // Generate previews sequentially
      for (const idx of indices) {
        const source = sources[idx];
        if (!source) continue;

        try {
          // Only apply downscale if enabled AND image is detected as AI-upscaled
          const downscaleSettings = (settings.downscaleEnabled && source.detectedType === 'ai_upscaled') ? {
            enabled: true,
            auto_trim: settings.downscaleAutoTrim,
            // Use manual dimensions if set, otherwise auto-detect
            target_width: settings.downscaleTargetWidth || undefined,
            target_height: settings.downscaleTargetHeight || undefined,
          } : null;

          const pngBytes = await invoke<number[]>('generate_preview_command', {
            inputPath: source.fullPath,
            downscaleSettings,
            alphaSettings,
            mergeSettings,
            outlineSettings,
          });

          const uint8Array = new Uint8Array(pngBytes);
          const base64 = btoa(
            uint8Array.reduce((data, byte) => data + String.fromCharCode(byte), '')
          );
          newPreviews.set(idx, `data:image/png;base64,${base64}`);
        } catch (err) {
          console.error(`Sample preview failed for ${source.name}:`, err);
        }
      }

      setSamplePreviews(newPreviews);
    } catch (err) {
      console.error('Sample previews generation failed:', err);
    } finally {
      setSamplePreviewsLoading(false);
    }
  }, []);

  // Debounced sample preview generation
  const requestSamplePreviews = useCallback((
    sources: SourceImage[],
    indices: number[],
    settings: ProcessingSettings
  ) => {
    // Clear existing timer
    if (samplePreviewTimerRef.current) {
      clearTimeout(samplePreviewTimerRef.current);
    }

    // Set new timer
    samplePreviewTimerRef.current = window.setTimeout(() => {
      generateSamplePreviews(sources, indices, settings);
    }, SAMPLE_PREVIEW_DEBOUNCE_MS);
  }, [generateSamplePreviews]);

  // Detect outline on focused image
  const detectOutline = useCallback(async (sourcePath: string) => {
    try {
      const result = await invoke<OutlineDetectionResult>('detect_outline_command', {
        inputPath: sourcePath,
      });
      setOutlineWarning(result.has_outline ? result : null);
    } catch (err) {
      console.error('Outline detection failed:', err);
      setOutlineWarning(null);
    }
  }, []);

  // Clear outline warning
  const dismissOutlineWarning = useCallback(() => {
    setOutlineWarning(null);
  }, []);

  // Trigger preview when focused image or settings change
  useEffect(() => {
    if (state.focusedIndex !== null && state.sources[state.focusedIndex]) {
      const source = state.sources[state.focusedIndex];
      requestPreview(source, state.settings);

      // Also detect outline if outline is enabled
      if (state.settings.outlineEnabled) {
        detectOutline(source.fullPath);
      } else {
        setOutlineWarning(null);
      }
    } else {
      setPreviewData(null);
      setOutlineWarning(null);
    }

    // Cleanup timer on unmount
    return () => {
      if (previewTimerRef.current) {
        clearTimeout(previewTimerRef.current);
      }
    };
  }, [state.focusedIndex, state.settings, state.sources, requestPreview, detectOutline]);

  // Trigger sample previews when settings or sample indices change
  useEffect(() => {
    if (state.sampleIndices.length > 0 && state.sources.length > 0) {
      requestSamplePreviews(state.sources, state.sampleIndices, state.settings);
    } else {
      setSamplePreviews(new Map());
    }

    // Cleanup timer on unmount
    return () => {
      if (samplePreviewTimerRef.current) {
        clearTimeout(samplePreviewTimerRef.current);
      }
    };
  }, [state.settings, state.sampleIndices, state.sources, requestSamplePreviews]);

  // Open folder dialog and load workspace
  const openFolder = useCallback(async () => {
    try {
      const directory = await open({
        directory: true,
        multiple: false,
      });

      if (!directory) return;

      setState(prev => ({
        ...prev,
        mode: 'folder',
        workspacePath: directory as string,
        sources: [],
        focusedIndex: null,
        selectedIndices: new Set(),
        progressMessage: 'Loading images...',
      }));

      setPreviewData(null);
      setOutlineWarning(null);

      // Initialize workspace state folder
      try {
        await invoke('init_workspace_command', { workspacePath: directory });
      } catch (err) {
        console.warn('Failed to init workspace state:', err);
      }

      // Load images from folder
      await loadImagesFromFolder(directory as string, setState);
    } catch (err) {
      console.error('Failed to open folder:', err);
    }
  }, []);

  // Open single image file
  const openImage = useCallback(async () => {
    try {
      const file = await open({
        multiple: false,
        filters: [{
          name: 'Images',
          extensions: ['png', 'jpg', 'jpeg', 'bmp', 'webp'],
        }],
      });

      if (!file) return;

      const filePath = file as string;
      const pathParts = filePath.replace(/\\/g, '/').split('/');
      const fileName = pathParts.pop() || '';
      const folderPath = pathParts.join('/');

      // Load single image
      const thumbnail = await loadThumbnail(filePath);

      // Detect scale
      const scaleInfo = await detectScaleForImage(filePath);

      const source: SourceImage = {
        relativePath: fileName,
        fullPath: filePath,
        name: fileName,
        thumbnail,
        status: 'pending',
        detectedType: scaleInfo.type,
        detectedScale: scaleInfo.scale,
      };

      setState(prev => ({
        ...prev,
        mode: 'single-file',
        workspacePath: folderPath,
        sources: [source],
        focusedIndex: 0,
        selectedIndices: new Set([0]),
        sampleIndices: [0],
        progressMessage: '',
      }));
    } catch (err) {
      console.error('Failed to open image:', err);
    }
  }, []);

  // Refresh current workspace
  const refresh = useCallback(async () => {
    if (!state.workspacePath) return;
    setPreviewData(null);
    await loadImagesFromFolder(state.workspacePath, setState);
  }, [state.workspacePath]);

  // Set focused image
  const setFocused = useCallback((index: number | null) => {
    setState(prev => ({ ...prev, focusedIndex: index }));
  }, []);

  // Toggle image selection
  const toggleSelection = useCallback((index: number) => {
    setState(prev => {
      const newSelected = new Set(prev.selectedIndices);
      if (newSelected.has(index)) {
        newSelected.delete(index);
      } else {
        newSelected.add(index);
      }
      return { ...prev, selectedIndices: newSelected };
    });
  }, []);

  // Select all images
  const selectAll = useCallback(() => {
    setState(prev => ({
      ...prev,
      selectedIndices: new Set(prev.sources.map((_, i) => i)),
    }));
  }, []);

  // Deselect all images
  const deselectAll = useCallback(() => {
    setState(prev => ({ ...prev, selectedIndices: new Set() }));
  }, []);

  // Select range of images (for Shift+click)
  const selectRange = useCallback((startIndex: number, endIndex: number) => {
    setState(prev => {
      const newSelected = new Set(prev.selectedIndices);
      for (let i = startIndex; i <= endIndex; i++) {
        newSelected.add(i);
      }
      return { ...prev, selectedIndices: newSelected };
    });
  }, []);

  // Select images by filter status
  const selectFiltered = useCallback((filter: 'pending' | 'processed' | 'error') => {
    setState(prev => {
      const newSelected = new Set<number>();
      prev.sources.forEach((source, index) => {
        if (source.status === filter) {
          newSelected.add(index);
        }
      });
      return { ...prev, selectedIndices: newSelected };
    });
  }, []);

  // Update settings
  const updateSettings = useCallback((updates: Partial<ProcessingSettings>) => {
    setState(prev => ({
      ...prev,
      settings: { ...prev.settings, ...updates },
    }));
  }, []);

  // Process single image (apply to focused)
  const processImage = useCallback(async (index: number, skipWarning = false) => {
    const source = state.sources[index];
    if (!source || !state.workspacePath) return;

    // Check outline warning
    if (!skipWarning && outlineWarning && state.settings.outlineEnabled) {
      // Warning will be shown in UI, user needs to confirm
      return { needsConfirmation: true, warning: outlineWarning };
    }

    setState(prev => ({
      ...prev,
      isProcessing: true,
      progressMessage: `Processing ${source.name}...`,
    }));

    try {
      const settings = state.settings;
      const [r, g, b, a] = hexToRgba(settings.outlineColor);

      // Use the combined process command for efficiency
      await invoke('process_image_command', {
        inputPath: source.fullPath,
        outputPath: source.fullPath, // In-place
        settings: {
          alpha_low_cutoff: settings.alphaLowCutoff,
          alpha_high_min: settings.alphaHighMin,
          alpha_high_max: 255,
          enable_color_simplify: settings.mergeEnabled,
          lab_merge_threshold: settings.mergeThreshold,
          enable_outline: settings.outlineEnabled,
          outline_color: [r, g, b, a],
          edge_transparent_cutoff: 0,
          outline_connectivity: 'four',
          outline_thickness: settings.outlineThickness,
        },
      });

      // Reload thumbnail
      const newThumbnail = await loadThumbnail(source.fullPath);

      // Update source status
      setState(prev => {
        const newSources = [...prev.sources];
        newSources[index] = {
          ...newSources[index],
          status: 'processed',
          thumbnail: newThumbnail,
        };
        return {
          ...prev,
          sources: newSources,
          isProcessing: false,
          progressMessage: 'Done!',
        };
      });

      // Clear outline warning after processing
      setOutlineWarning(null);

      setTimeout(() => {
        setState(prev => ({ ...prev, progressMessage: '' }));
      }, 2000);

      return { success: true };
    } catch (err) {
      console.error('Processing failed:', err);
      setState(prev => {
        const newSources = [...prev.sources];
        newSources[index] = { ...newSources[index], status: 'error', error: String(err) };
        return {
          ...prev,
          sources: newSources,
          isProcessing: false,
          progressMessage: `Error: ${err}`,
        };
      });
      return { success: false, error: err };
    }
  }, [state.sources, state.workspacePath, state.settings, outlineWarning]);

  // Process all selected images
  const processAll = useCallback(async (skipWarning = false) => {
    const indices = Array.from(state.selectedIndices);
    if (indices.length === 0) return;

    setState(prev => ({ ...prev, isProcessing: true }));

    let processed = 0;
    let failed = 0;

    for (let i = 0; i < indices.length; i++) {
      const idx = indices[i];
      const source = state.sources[idx];
      if (!source) continue;

      setState(prev => ({
        ...prev,
        progressMessage: `Processing ${i + 1}/${indices.length}: ${source.name}`,
      }));

      const result = await processImage(idx, skipWarning);
      if (result?.success) {
        processed++;
      } else if (result?.needsConfirmation) {
        // Skip for now if needs confirmation
        continue;
      } else {
        failed++;
      }
    }

    setState(prev => ({
      ...prev,
      isProcessing: false,
      progressMessage: `Complete! ${processed} processed${failed > 0 ? `, ${failed} failed` : ''}`,
    }));

    setTimeout(() => {
      setState(prev => ({ ...prev, progressMessage: '' }));
    }, 3000);
  }, [state.selectedIndices, state.sources, processImage]);

  // Update sample indices
  const setSampleIndices = useCallback((indices: number[]) => {
    setState(prev => ({ ...prev, sampleIndices: indices }));
  }, []);

  // Save processed image to a specific path (for one-off mode)
  const saveAs = useCallback(async (outputPath: string) => {
    const source = state.sources[0];
    if (!source) return { success: false, error: 'No image loaded' };

    setState(prev => ({
      ...prev,
      isProcessing: true,
      progressMessage: 'Saving...',
    }));

    try {
      const settings = state.settings;
      const [r, g, b, a] = hexToRgba(settings.outlineColor);

      // Only apply downscale if enabled AND image is detected as AI-upscaled
      const downscaleSettings = (settings.downscaleEnabled && source.detectedType === 'ai_upscaled') ? {
        enabled: true,
        auto_trim: settings.downscaleAutoTrim,
        // Use manual dimensions if set, otherwise auto-detect
        target_width: settings.downscaleTargetWidth || undefined,
        target_height: settings.downscaleTargetHeight || undefined,
      } : null;

      const alphaSettings = settings.alphaEnabled ? {
        low_cutoff: settings.alphaLowCutoff,
        high_min: settings.alphaHighMin,
        high_max: 255,
      } : null;

      const mergeSettings = settings.mergeEnabled ? {
        threshold: settings.mergeThreshold,
      } : null;

      const outlineSettings = settings.outlineEnabled ? {
        color: [r, g, b, a],
        connectivity: 'four',
        thickness: settings.outlineThickness,
        edge_transparent_cutoff: 0,
      } : null;

      // Use the new process_and_save_command that includes downscaling
      await invoke('process_and_save_command', {
        inputPath: source.fullPath,
        outputPath: outputPath,
        downscaleSettings,
        alphaSettings,
        mergeSettings,
        outlineSettings,
      });

      setState(prev => ({
        ...prev,
        isProcessing: false,
        progressMessage: 'Saved!',
      }));

      setTimeout(() => {
        setState(prev => ({ ...prev, progressMessage: '' }));
      }, 2000);

      return { success: true };
    } catch (err) {
      console.error('Save failed:', err);
      setState(prev => ({
        ...prev,
        isProcessing: false,
        progressMessage: `Error: ${err}`,
      }));
      return { success: false, error: err };
    }
  }, [state.sources, state.settings]);

  // Close workspace and return to empty state
  const closeWorkspace = useCallback(() => {
    setState(INITIAL_STATE);
    setPreviewData(null);
    setOutlineWarning(null);
    setSamplePreviews(new Map());
  }, []);

  return {
    state,
    preview: {
      data: previewData,
      loading: previewLoading,
      outlineWarning,
      samplePreviews,
      samplePreviewsLoading,
    },
    actions: {
      openFolder,
      openImage,
      refresh,
      setFocused,
      toggleSelection,
      selectAll,
      deselectAll,
      selectRange,
      selectFiltered,
      updateSettings,
      processImage,
      processAll,
      setSampleIndices,
      dismissOutlineWarning,
      saveAs,
      closeWorkspace,
      regeneratePreview: () => {
        if (state.focusedIndex !== null && state.sources[state.focusedIndex]) {
          generatePreview(state.sources[state.focusedIndex], state.settings);
        }
      },
    },
  };
}

// Helper: Load images from folder
async function loadImagesFromFolder(
  folderPath: string,
  setState: React.Dispatch<React.SetStateAction<WorkspaceState>>
) {
  try {
    const entries = await readDir(folderPath);
    const sources: SourceImage[] = [];
    const pathSep = folderPath.includes('\\') ? '\\' : '/';

    for (const entry of entries) {
      const name = entry.name.toLowerCase();
      if (
        !entry.isDirectory &&
        (name.endsWith('.png') ||
          name.endsWith('.jpg') ||
          name.endsWith('.jpeg') ||
          name.endsWith('.bmp') ||
          name.endsWith('.webp'))
      ) {
        const fullPath = `${folderPath}${pathSep}${entry.name}`;
        const thumbnail = await loadThumbnail(fullPath);

        sources.push({
          relativePath: entry.name,
          fullPath,
          name: entry.name,
          thumbnail,
          status: 'pending',
          detectedType: 'unknown',
        });
      }
    }

    // Sort by name
    sources.sort((a, b) => a.name.localeCompare(b.name));

    // Auto-select first 4 for sample preview
    const sampleIndices = sources.slice(0, 4).map((_, i) => i);

    setState(prev => ({
      ...prev,
      sources,
      selectedIndices: new Set(sources.map((_, i) => i)), // Select all by default
      sampleIndices,
      progressMessage: 'Detecting image types...',
      focusedIndex: sources.length > 0 ? 0 : null,
    }));

    // Detect scale for each image (in background)
    detectScalesForSources(sources, setState);
  } catch (err) {
    console.error('Failed to load images:', err);
    setState(prev => ({
      ...prev,
      sources: [],
      progressMessage: 'Failed to load images',
    }));
  }
}

// Helper: Detect scales for all sources (runs in background)
async function detectScalesForSources(
  sources: SourceImage[],
  setState: React.Dispatch<React.SetStateAction<WorkspaceState>>
) {
  for (let i = 0; i < sources.length; i++) {
    const source = sources[i];
    try {
      const result = await invoke<ScaleDetectionResult>('detect_scale_command', {
        inputPath: source.fullPath,
      });

      setState(prev => {
        const newSources = [...prev.sources];
        if (newSources[i]) {
          newSources[i] = {
            ...newSources[i],
            detectedType: result.is_ai_upscaled ? 'ai_upscaled' : 'native_pixel_art',
            detectedScale: result.detected_scale,
          };
        }
        return {
          ...prev,
          sources: newSources,
          progressMessage: i === sources.length - 1 ? '' : `Detecting... ${i + 1}/${sources.length}`,
        };
      });
    } catch (err) {
      console.warn(`Scale detection failed for ${source.name}:`, err);
    }
  }
}

// Helper: Detect scale for a single image
async function detectScaleForImage(fullPath: string): Promise<{ type: SourceImage['detectedType']; scale: number }> {
  try {
    const result = await invoke<ScaleDetectionResult>('detect_scale_command', {
      inputPath: fullPath,
    });
    return {
      type: result.is_ai_upscaled ? 'ai_upscaled' : 'native_pixel_art',
      scale: result.detected_scale,
    };
  } catch {
    return { type: 'unknown', scale: 1 };
  }
}

// Helper: Load thumbnail as base64
async function loadThumbnail(filePath: string): Promise<string | undefined> {
  try {
    const fileData = await readFile(filePath);
    const base64 = btoa(
      new Uint8Array(fileData).reduce(
        (data, byte) => data + String.fromCharCode(byte),
        ''
      )
    );

    const name = filePath.toLowerCase();
    let mimeType = 'image/png';
    if (name.endsWith('.jpg') || name.endsWith('.jpeg')) {
      mimeType = 'image/jpeg';
    } else if (name.endsWith('.webp')) {
      mimeType = 'image/webp';
    } else if (name.endsWith('.bmp')) {
      mimeType = 'image/bmp';
    }

    return `data:${mimeType};base64,${base64}`;
  } catch {
    return undefined;
  }
}
