mod error;
mod packer;
mod processor;
pub mod downscaler;
mod db;
mod state;

use std::path::PathBuf;
use std::sync::Mutex;
use tauri::Manager;
use serde::Deserialize;
use error::Result;
use packer::{PackerSettings, PackerResult};
use processor::{
    ProcessorSettings, ProcessorResult,
    AlphaSettings, MergeSettings, OutlineSettings,
    MergeResult, OutlineDetectionResult,
};
use downscaler::{DownscalerSettings, DownscaleResult};
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

/// Settings for inline downscale during preview
#[derive(Debug, Clone, Deserialize)]
pub struct PreviewDownscaleSettings {
    /// Enable downscaling
    pub enabled: bool,
    /// Auto-trim transparent borders
    pub auto_trim: bool,
}

/// Generate preview PNG bytes without saving to disk
#[tauri::command]
async fn generate_preview_command(
    input_path: String,
    downscale_settings: Option<PreviewDownscaleSettings>,
    alpha_settings: Option<AlphaSettings>,
    merge_settings: Option<MergeSettings>,
    outline_settings: Option<OutlineSettings>,
) -> Result<Vec<u8>> {
    let input = PathBuf::from(input_path);

    tokio::task::spawn_blocking(move || {
        let mut img = processor::load_image(&input)?;

        // Downscale first (if enabled)
        if let Some(ds_settings) = downscale_settings {
            if ds_settings.enabled {
                // Use the downscaler's internal functions
                if ds_settings.auto_trim {
                    img = downscaler::auto_trim_image(&img);
                }
                // Detect and apply downscaling
                let grid_hint = downscaler::detect_grid_for_image(&img);
                let (scale, phase_x, phase_y) = downscaler::find_optimal_scale_for_image(&img, grid_hint);
                if scale > 1 {
                    img = downscaler::downsample_image(&img, scale, phase_x, phase_y);
                }
            }
        }

        // Apply post-processing operations in order (if settings provided)
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
        .setup(|app| {
            // Initialize database
            let app_dir = app.path().app_data_dir()
                .expect("Failed to get app data directory");

            std::fs::create_dir_all(&app_dir).expect("Failed to create app directory");

            let db_path = app_dir.join("pixels.db");
            let database = Database::new(db_path).expect("Failed to initialize database");

            app.manage(Mutex::new(database));

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
            generate_preview_command,
            // V2 workspace state
            init_workspace_command,
            load_workspace_command,
            save_workspace_command,
            get_source_state_command,
            add_version_command,
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
