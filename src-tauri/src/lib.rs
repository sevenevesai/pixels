mod error;
mod packer;
mod processor;
pub mod downscaler;
mod db;
mod state;

use std::path::PathBuf;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use tauri::{AppHandle, Emitter, Manager};
use serde::{Deserialize, Serialize};
use error::Result;
use packer::{PackerSettings, PackerResult};
use processor::{
    ProcessorSettings, ProcessorResult,
    AlphaSettings, MergeSettings, OutlineSettings, BackgroundSettings,
    MergeResult, OutlineDetectionResult, BackgroundDetectionResult,
};
use downscaler::{DownscalerSettings, DownscaleResult, ManualDownscaleSettings};
use db::{Database, Project, ProjectSettings};
use state::{WorkspaceManager, WorkspaceState};

#[tauri::command]
async fn pack_sprites_command(
    input_paths: Vec<String>,
    output_path: String,
    settings: PackerSettings,
) -> Result<PackerResult> {
    let paths: Vec<PathBuf> = input_paths.iter().map(PathBuf::from).collect();
    let output = PathBuf::from(output_path);

    tokio::task::spawn_blocking(move || {
        packer::pack_sprites(paths, output, settings)
    })
    .await
    .map_err(|e| error::PixelsError::Processing(format!("Task join error: {}", e)))?
}

#[tauri::command]
async fn process_image_command(
    input_path: String,
    output_path: String,
    settings: ProcessorSettings,
) -> Result<ProcessorResult> {
    let input = PathBuf::from(input_path);
    let output = PathBuf::from(output_path);

    tokio::task::spawn_blocking(move || {
        processor::process_image(input, output, settings)
    })
    .await
    .map_err(|e| error::PixelsError::Processing(format!("Task join error: {}", e)))?
}

#[tauri::command]
async fn downscale_image_command(
    input_path: String,
    output_path: String,
    settings: DownscalerSettings,
) -> Result<DownscaleResult> {
    let input = PathBuf::from(input_path);
    let output = PathBuf::from(output_path);

    tokio::task::spawn_blocking(move || {
        downscaler::downscale_image(input, output, settings)
    })
    .await
    .map_err(|e| error::PixelsError::Processing(format!("Task join error: {}", e)))?
}

/// Detect scale factor of an image without modifying it
#[tauri::command]
async fn detect_scale_command(
    input_path: String,
) -> Result<downscaler::ScaleDetectionResult> {
    let input = PathBuf::from(input_path);

    tokio::task::spawn_blocking(move || {
        downscaler::detect_scale(input)
    })
    .await
    .map_err(|e| error::PixelsError::Processing(format!("Task join error: {}", e)))?
}

// ============================================================================
// V2 INDIVIDUAL OPERATION COMMANDS
// ============================================================================

/// Load image and normalize alpha channel
#[tauri::command]
async fn normalize_alpha_command(
    input_path: String,
    output_path: String,
    settings: AlphaSettings,
) -> Result<()> {
    let input = PathBuf::from(input_path);
    let output = PathBuf::from(output_path);

    tokio::task::spawn_blocking(move || {
        let mut img = processor::load_image(&input)?;
        processor::normalize_alpha(&mut img, &settings);
        processor::save_image(&img, &output)
    })
    .await
    .map_err(|e| error::PixelsError::Processing(format!("Task join error: {}", e)))?
}

/// Load image and merge similar colors
#[tauri::command]
async fn merge_colors_command(
    input_path: String,
    output_path: String,
    settings: MergeSettings,
) -> Result<MergeResult> {
    let input = PathBuf::from(input_path);
    let output = PathBuf::from(output_path);

    tokio::task::spawn_blocking(move || {
        let mut img = processor::load_image(&input)?;
        let result = processor::merge_colors(&mut img, &settings);
        processor::save_image(&img, &output)?;
        Ok(result)
    })
    .await
    .map_err(|e| error::PixelsError::Processing(format!("Task join error: {}", e)))?
}

/// Load image and add outline
#[tauri::command]
async fn add_outline_command(
    input_path: String,
    output_path: String,
    settings: OutlineSettings,
) -> Result<()> {
    let input = PathBuf::from(input_path);
    let output = PathBuf::from(output_path);

    tokio::task::spawn_blocking(move || {
        let mut img = processor::load_image(&input)?;
        processor::add_outline(&mut img, &settings);
        processor::save_image(&img, &output)
    })
    .await
    .map_err(|e| error::PixelsError::Processing(format!("Task join error: {}", e)))?
}

/// Detect if image already has an outline
#[tauri::command]
async fn detect_outline_command(input_path: String) -> Result<OutlineDetectionResult> {
    let input = PathBuf::from(input_path);

    tokio::task::spawn_blocking(move || {
        let img = processor::load_image(&input)?;
        Ok(processor::detect_outline(&img))
    })
    .await
    .map_err(|e| error::PixelsError::Processing(format!("Task join error: {}", e)))?
}

/// Detect if image has a solid-color background
#[tauri::command]
async fn detect_background_command(input_path: String) -> Result<BackgroundDetectionResult> {
    let input = PathBuf::from(input_path);

    tokio::task::spawn_blocking(move || {
        let img = processor::load_image(&input)?;
        Ok(processor::detect_background(&img))
    })
    .await
    .map_err(|e| error::PixelsError::Processing(format!("Task join error: {}", e)))?
}

/// Generate downscale-only preview with manual target dimensions
/// Returns PNG bytes for live preview without saving
#[tauri::command]
async fn downscale_preview_command(
    input_path: String,
    target_width: u32,
    target_height: u32,
    auto_trim: bool,
    background_settings: Option<BackgroundSettings>,
) -> Result<Vec<u8>> {
    let input = PathBuf::from(input_path);

    tokio::task::spawn_blocking(move || {
        let mut img = processor::load_image(&input)?;

        // Background removal before downscale (removes bg at full res)
        if let Some(bg) = background_settings {
            processor::remove_background(&mut img, &bg);
        }

        let settings = ManualDownscaleSettings {
            target_width,
            target_height,
            auto_trim,
        };

        let result = downscaler::downscale_manual_preview(&img, &settings);
        processor::encode_png(&result)
    })
    .await
    .map_err(|e| error::PixelsError::Processing(format!("Task join error: {}", e)))?
}

/// Settings for inline downscale during preview
#[derive(Debug, Clone, Deserialize)]
pub struct PreviewDownscaleSettings {
    /// Enable downscaling
    pub enabled: bool,
    /// Auto-trim transparent borders
    pub auto_trim: bool,
    /// Manual target width (if set, uses manual dimensions instead of auto-detect)
    pub target_width: Option<u32>,
    /// Manual target height (if set, uses manual dimensions instead of auto-detect)
    pub target_height: Option<u32>,
}

/// Generate preview PNG bytes without saving to disk
#[tauri::command]
async fn generate_preview_command(
    input_path: String,
    downscale_settings: Option<PreviewDownscaleSettings>,
    background_settings: Option<BackgroundSettings>,
    alpha_settings: Option<AlphaSettings>,
    merge_settings: Option<MergeSettings>,
    outline_settings: Option<OutlineSettings>,
) -> Result<Vec<u8>> {
    let input = PathBuf::from(input_path);

    tokio::task::spawn_blocking(move || {
        let mut img = processor::load_image(&input)?;

        // Background removal FIRST (before downscale so bg color doesn't
        // bleed into sprite edge pixels during downsampling)
        if let Some(settings) = background_settings {
            processor::remove_background(&mut img, &settings);
        }

        // Downscale (if enabled)
        if let Some(ds_settings) = downscale_settings {
            if ds_settings.enabled {
                if let (Some(target_w), Some(target_h)) = (ds_settings.target_width, ds_settings.target_height) {
                    if ds_settings.auto_trim {
                        img = downscaler::auto_trim_image(&img);
                    }
                    img = downscaler::downscale_to_dimensions(&img, target_w, target_h);
                } else {
                    if ds_settings.auto_trim {
                        img = downscaler::auto_trim_image(&img);
                    }
                    let grid_hint = downscaler::detect_grid_for_image(&img);
                    let (scale, phase_x, phase_y) = downscaler::find_optimal_scale_for_image(&img, grid_hint);
                    if scale > 1 {
                        img = downscaler::downsample_image(&img, scale, phase_x, phase_y);
                    }
                }
            }
        }

        // Post-processing
        if let Some(settings) = alpha_settings {
            processor::normalize_alpha(&mut img, &settings);
        }
        if let Some(settings) = merge_settings {
            processor::merge_colors(&mut img, &settings);
        }
        if let Some(settings) = outline_settings {
            processor::add_outline(&mut img, &settings);
        }

        processor::encode_png(&img)
    })
    .await
    .map_err(|e| error::PixelsError::Processing(format!("Task join error: {}", e)))?
}

/// Process and save image to disk (same pipeline as preview but saves to file)
#[tauri::command]
async fn process_and_save_command(
    input_path: String,
    output_path: String,
    downscale_settings: Option<PreviewDownscaleSettings>,
    background_settings: Option<BackgroundSettings>,
    alpha_settings: Option<AlphaSettings>,
    merge_settings: Option<MergeSettings>,
    outline_settings: Option<OutlineSettings>,
) -> Result<()> {
    let input = PathBuf::from(input_path);
    let output = PathBuf::from(output_path);

    tokio::task::spawn_blocking(move || {
        let mut img = processor::load_image(&input)?;

        // Background removal FIRST
        if let Some(settings) = background_settings {
            processor::remove_background(&mut img, &settings);
        }

        // Downscale (if enabled)
        if let Some(ds_settings) = downscale_settings {
            if ds_settings.enabled {
                if let (Some(target_w), Some(target_h)) = (ds_settings.target_width, ds_settings.target_height) {
                    if ds_settings.auto_trim {
                        img = downscaler::auto_trim_image(&img);
                    }
                    img = downscaler::downscale_to_dimensions(&img, target_w, target_h);
                } else {
                    if ds_settings.auto_trim {
                        img = downscaler::auto_trim_image(&img);
                    }
                    let grid_hint = downscaler::detect_grid_for_image(&img);
                    let (scale, phase_x, phase_y) = downscaler::find_optimal_scale_for_image(&img, grid_hint);
                    if scale > 1 {
                        img = downscaler::downsample_image(&img, scale, phase_x, phase_y);
                    }
                }
            }
        }

        // Post-processing
        if let Some(settings) = alpha_settings {
            processor::normalize_alpha(&mut img, &settings);
        }
        if let Some(settings) = merge_settings {
            processor::merge_colors(&mut img, &settings);
        }
        if let Some(settings) = outline_settings {
            processor::add_outline(&mut img, &settings);
        }

        processor::save_image(&img, &output)
    })
    .await
    .map_err(|e| error::PixelsError::Processing(format!("Task join error: {}", e)))?
}

// ============================================================================
// BATCH PROCESSING
// ============================================================================

#[derive(Clone, Serialize)]
struct BatchProgressEvent {
    index: usize,
    total: usize,
    current_file: String,
    status: String, // "processing", "done", "error", "cancelled"
    error: Option<String>,
}

#[derive(Clone, Serialize)]
struct BatchCompleteEvent {
    processed: usize,
    failed: usize,
    cancelled: bool,
}

/// Batch process multiple images with shared settings.
/// Emits "batch-progress" events per file and "batch-complete" when done.
#[tauri::command]
async fn batch_process_command(
    app: AppHandle,
    paths: Vec<String>,
    workspace_path: Option<String>,
    downscale_enabled: bool,
    background_settings: Option<BackgroundSettings>,
    alpha_settings: Option<AlphaSettings>,
    merge_settings: Option<MergeSettings>,
    outline_settings: Option<OutlineSettings>,
) -> Result<()> {
    let cancel_flag = app.state::<Arc<AtomicBool>>();
    cancel_flag.store(false, Ordering::Relaxed);
    let cancel = cancel_flag.inner().clone();

    let total = paths.len();

    tokio::task::spawn_blocking(move || {
        let mut processed = 0usize;
        let mut failed = 0usize;
        // Track backup mappings: (original_path, backup_filename)
        let mut backup_manifest: Vec<(String, String)> = Vec::new();

        for (i, file_path) in paths.iter().enumerate() {
            if cancel.load(Ordering::Relaxed) {
                let _ = app.emit("batch-progress", BatchProgressEvent {
                    index: i,
                    total,
                    current_file: file_path.clone(),
                    status: "cancelled".into(),
                    error: None,
                });
                let _ = app.emit("batch-complete", BatchCompleteEvent {
                    processed,
                    failed,
                    cancelled: true,
                });
                // Write manifest even on cancel (so partial work can be reverted)
                if let Some(ref ws) = workspace_path {
                    write_batch_manifest(ws, &backup_manifest);
                }
                return Ok(());
            }

            let _ = app.emit("batch-progress", BatchProgressEvent {
                index: i,
                total,
                current_file: file_path.clone(),
                status: "processing".into(),
                error: None,
            });

            let input = PathBuf::from(file_path);

            // Backup original if workspace provided
            if let Some(ref ws) = workspace_path {
                let ws_path = PathBuf::from(ws);

                if let Ok(hash) = state::hash_file(&input) {
                    let backup_name = format!("{}_original.png", &hash[..16]);
                    let backup_path = ws_path.join(".pixels").join("cache").join(&backup_name);
                    if !backup_path.exists() {
                        let _ = std::fs::copy(&input, &backup_path);
                    }
                    backup_manifest.push((file_path.clone(), backup_name));
                }
            }

            // Process the image
            let result = (|| -> error::Result<()> {
                let mut img = processor::load_image(&input)?;

                // Background removal first
                if let Some(ref bg) = background_settings {
                    processor::remove_background(&mut img, bg);
                }

                // Downscale (auto-detect per image)
                if downscale_enabled {
                    img = downscaler::auto_trim_image(&img);
                    let grid_hint = downscaler::detect_grid_for_image(&img);
                    let (scale, phase_x, phase_y) =
                        downscaler::find_optimal_scale_for_image(&img, grid_hint);
                    if scale > 1 {
                        img = downscaler::downsample_image(&img, scale, phase_x, phase_y);
                    }
                }

                // Post-processing
                if let Some(ref alpha) = alpha_settings {
                    processor::normalize_alpha(&mut img, alpha);
                }
                if let Some(ref merge) = merge_settings {
                    processor::merge_colors(&mut img, merge);
                }
                if let Some(ref outline) = outline_settings {
                    processor::add_outline(&mut img, outline);
                }

                processor::save_image(&img, &input)
            })();

            match result {
                Ok(()) => {
                    processed += 1;
                    let _ = app.emit("batch-progress", BatchProgressEvent {
                        index: i,
                        total,
                        current_file: file_path.clone(),
                        status: "done".into(),
                        error: None,
                    });
                }
                Err(e) => {
                    failed += 1;
                    let _ = app.emit("batch-progress", BatchProgressEvent {
                        index: i,
                        total,
                        current_file: file_path.clone(),
                        status: "error".into(),
                        error: Some(e.to_string()),
                    });
                }
            }
        }

        // Write manifest so Revert All knows what to restore
        if let Some(ref ws) = workspace_path {
            write_batch_manifest(ws, &backup_manifest);
        }

        let _ = app.emit("batch-complete", BatchCompleteEvent {
            processed,
            failed,
            cancelled: false,
        });

        Ok(())
    })
    .await
    .map_err(|e| error::PixelsError::Processing(format!("Task join error: {}", e)))?
}

#[tauri::command]
async fn batch_cancel_command(app: AppHandle) -> Result<()> {
    let cancel_flag = app.state::<Arc<AtomicBool>>();
    cancel_flag.store(true, Ordering::Relaxed);
    Ok(())
}

fn write_batch_manifest(workspace_path: &str, entries: &[(String, String)]) {
    let manifest_path = PathBuf::from(workspace_path)
        .join(".pixels")
        .join("cache")
        .join("batch_manifest.json");

    let manifest: std::collections::HashMap<&str, &str> = entries
        .iter()
        .map(|(original, backup)| (original.as_str(), backup.as_str()))
        .collect();

    if let Ok(json) = serde_json::to_string_pretty(&manifest) {
        let _ = std::fs::write(manifest_path, json);
    }
}

#[derive(Clone, Serialize)]
struct BatchRevertResult {
    reverted: usize,
    failed: usize,
    errors: Vec<String>,
}

/// Revert all images from the last batch operation using the manifest
#[tauri::command]
async fn batch_revert_command(workspace_path: String) -> Result<BatchRevertResult> {
    let ws = workspace_path.clone();

    tokio::task::spawn_blocking(move || {
        let cache_dir = PathBuf::from(&ws).join(".pixels").join("cache");
        let manifest_path = cache_dir.join("batch_manifest.json");

        if !manifest_path.exists() {
            return Err(error::PixelsError::Processing(
                "No batch manifest found. Nothing to revert.".into(),
            ));
        }

        let manifest_content = std::fs::read_to_string(&manifest_path)?;
        let manifest: std::collections::HashMap<String, String> =
            serde_json::from_str(&manifest_content)?;

        let mut reverted = 0usize;
        let mut failed = 0usize;
        let mut errors: Vec<String> = Vec::new();

        for (original_path, backup_name) in &manifest {
            let backup_path = cache_dir.join(backup_name);

            if !backup_path.exists() {
                failed += 1;
                errors.push(format!("Backup missing for {}", original_path));
                continue;
            }

            match std::fs::copy(&backup_path, original_path) {
                Ok(_) => reverted += 1,
                Err(e) => {
                    failed += 1;
                    errors.push(format!("{}: {}", original_path, e));
                }
            }
        }

        // Remove manifest after revert (it's consumed)
        let _ = std::fs::remove_file(&manifest_path);

        Ok(BatchRevertResult { reverted, failed, errors })
    })
    .await
    .map_err(|e| error::PixelsError::Processing(format!("Task join error: {}", e)))?
}

/// Check if a batch manifest exists (to show/hide the Revert button)
#[tauri::command]
async fn batch_has_manifest_command(workspace_path: String) -> Result<bool> {
    let manifest_path = PathBuf::from(&workspace_path)
        .join(".pixels")
        .join("cache")
        .join("batch_manifest.json");
    Ok(manifest_path.exists())
}

// ============================================================================
// WORKSPACE STATE COMMANDS
// ============================================================================

/// Initialize workspace state for a folder
#[tauri::command]
async fn init_workspace_command(workspace_path: String) -> Result<()> {
    let path = PathBuf::from(workspace_path);

    tokio::task::spawn_blocking(move || {
        let manager = WorkspaceManager::open(&path)?;
        manager.init()
    })
    .await
    .map_err(|e| error::PixelsError::Processing(format!("Task join error: {}", e)))?
}

/// Load workspace state
#[tauri::command]
async fn load_workspace_command(workspace_path: String) -> Result<WorkspaceState> {
    let path = PathBuf::from(workspace_path);

    tokio::task::spawn_blocking(move || {
        let manager = WorkspaceManager::open(&path)?;
        Ok(manager.into_state())
    })
    .await
    .map_err(|e| error::PixelsError::Processing(format!("Task join error: {}", e)))?
}

/// Save workspace state
#[tauri::command]
async fn save_workspace_command(
    workspace_path: String,
    state: WorkspaceState,
) -> Result<()> {
    let path = PathBuf::from(workspace_path);

    tokio::task::spawn_blocking(move || {
        let manager = WorkspaceManager::from_state(&path, state);
        manager.save()
    })
    .await
    .map_err(|e| error::PixelsError::Processing(format!("Task join error: {}", e)))?
}

/// Get source state for a specific image (or create if new)
#[tauri::command]
async fn get_source_state_command(
    workspace_path: String,
    relative_path: String,
) -> Result<state::SourceState> {
    let path = PathBuf::from(workspace_path);

    tokio::task::spawn_blocking(move || {
        let mut manager = WorkspaceManager::open(&path)?;
        let source = manager.get_or_create_source(&relative_path)?;
        Ok(source.clone())
    })
    .await
    .map_err(|e| error::PixelsError::Processing(format!("Task join error: {}", e)))?
}

/// Add a new version to a source's lineage
#[tauri::command]
async fn add_version_command(
    workspace_path: String,
    relative_path: String,
    version: state::ImageVersion,
) -> Result<()> {
    let path = PathBuf::from(workspace_path);

    tokio::task::spawn_blocking(move || {
        let mut manager = WorkspaceManager::open(&path)?;
        let source = manager.get_or_create_source(&relative_path)?;
        source.add_version(version);
        manager.save()
    })
    .await
    .map_err(|e| error::PixelsError::Processing(format!("Task join error: {}", e)))?
}

/// Backup original image to .pixels/cache before overwriting
/// Returns the cache path where the backup was saved
#[tauri::command]
async fn backup_original_command(
    workspace_path: String,
    relative_path: String,
) -> Result<String> {
    let ws_path = PathBuf::from(&workspace_path);
    let rel_path = relative_path.clone();

    tokio::task::spawn_blocking(move || {
        let manager = WorkspaceManager::open(&ws_path)?;
        let source_file = ws_path.join(&rel_path);

        // Generate backup filename using hash
        let hash = state::hash_file(&source_file)?;
        let backup_name = format!("{}_original.png", &hash[..16]);
        let backup_path = manager.cache_dir().join(&backup_name);

        // Only backup if not already backed up
        if !backup_path.exists() {
            std::fs::copy(&source_file, &backup_path)?;
        }

        Ok(backup_name)
    })
    .await
    .map_err(|e| error::PixelsError::Processing(format!("Task join error: {}", e)))?
}

// Database/Project commands

#[tauri::command]
fn get_projects(db: tauri::State<Mutex<Database>>) -> Result<Vec<Project>> {
    db.lock().unwrap().get_projects()
}

#[tauri::command]
fn add_project(db: tauri::State<Mutex<Database>>, name: String, path: String) -> Result<Project> {
    db.lock().unwrap().add_project(name, path)
}

#[tauri::command]
fn remove_project(db: tauri::State<Mutex<Database>>, id: i64) -> Result<()> {
    db.lock().unwrap().remove_project(id)
}

#[tauri::command]
fn get_current_project_id(db: tauri::State<Mutex<Database>>) -> Result<Option<i64>> {
    db.lock().unwrap().get_current_project_id()
}

#[tauri::command]
fn set_current_project_id(db: tauri::State<Mutex<Database>>, id: Option<i64>) -> Result<()> {
    db.lock().unwrap().set_current_project_id(id)
}

#[tauri::command]
fn get_project_settings(db: tauri::State<Mutex<Database>>, project_id: i64) -> Result<ProjectSettings> {
    db.lock().unwrap().get_project_settings(project_id)
}

#[tauri::command]
fn get_project_setting(
    db: tauri::State<Mutex<Database>>,
    project_id: i64,
    key: String,
) -> Result<Option<String>> {
    db.lock().unwrap().get_project_setting(project_id, &key)
}

#[tauri::command]
fn set_project_setting(
    db: tauri::State<Mutex<Database>>,
    project_id: i64,
    key: String,
    value: String,
) -> Result<()> {
    db.lock().unwrap().set_project_setting(project_id, &key, &value)
}

#[tauri::command]
fn get_app_setting(db: tauri::State<Mutex<Database>>, key: String) -> Result<Option<String>> {
    db.lock().unwrap().get_app_setting(&key)
}

#[tauri::command]
fn set_app_setting(db: tauri::State<Mutex<Database>>, key: String, value: String) -> Result<()> {
    db.lock().unwrap().set_app_setting(&key, &value)
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_fs::init())
        .plugin(tauri_plugin_updater::Builder::new().build())
        .plugin(tauri_plugin_process::init())
        .setup(|app| {
            // Initialize database
            let app_dir = app.path().app_data_dir()
                .expect("Failed to get app data directory");

            std::fs::create_dir_all(&app_dir).expect("Failed to create app directory");

            let db_path = app_dir.join("pixels.db");
            let database = Database::new(db_path).expect("Failed to initialize database");

            app.manage(Mutex::new(database));
            app.manage(Arc::new(AtomicBool::new(false)));

            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            // Legacy v1 commands
            pack_sprites_command,
            process_image_command,
            downscale_image_command,
            detect_scale_command,
            // V2 individual operations
            normalize_alpha_command,
            merge_colors_command,
            add_outline_command,
            detect_outline_command,
            detect_background_command,
            downscale_preview_command,
            generate_preview_command,
            process_and_save_command,
            // Batch processing
            batch_process_command,
            batch_cancel_command,
            batch_revert_command,
            batch_has_manifest_command,
            // V2 workspace state
            init_workspace_command,
            load_workspace_command,
            save_workspace_command,
            get_source_state_command,
            add_version_command,
            backup_original_command,
            // Database/project commands
            get_projects,
            add_project,
            remove_project,
            get_current_project_id,
            set_current_project_id,
            get_project_settings,
            get_project_setting,
            set_project_setting,
            get_app_setting,
            set_app_setting,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
