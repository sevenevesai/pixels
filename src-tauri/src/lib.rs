mod error;
mod packer;
mod processor;
mod downscaler;
mod db;

use std::path::PathBuf;
use std::sync::Mutex;
use tauri::Manager;
use error::Result;
use packer::{PackerSettings, PackerResult};
use processor::ProcessorSettings;
use downscaler::{DownscalerSettings, DownscaleResult};
use db::{Database, Project, ProjectSettings};

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
) -> Result<()> {
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
            pack_sprites_command,
            process_image_command,
            downscale_image_command,
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
