//! Workspace State Management (V2)
//!
//! Manages the `.pixels/` folder structure for workspace state:
//! - `cache/` - Processed image versions
//! - `thumbnails/` - Quick-load previews
//! - `state.json` - Lineage tree and settings
//!
//! Key concepts:
//! - **Source**: Original image file from user's folder
//! - **Version**: A processed state of a source (original, downscaled, post-processed)
//! - **Lineage**: Tree of versions branching from original
//! - **Cache**: Stored processed images, keyed by content hash
//!
//! Note: Many functions in this module are infrastructure for Phase 2+
//! and will be used when the UI is wired up.

#![allow(dead_code)]

use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::path::{Path, PathBuf};
use std::fs;
use sha2::{Sha256, Digest};
use crate::error::{Result, PixelsError};

// ============================================================================
// VERSION TYPES
// ============================================================================

/// Type of processing that created this version
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(rename_all = "snake_case")]
pub enum VersionType {
    /// Original unprocessed image
    Original,
    /// Downscaled from AI-upscaled source
    Downscaled,
    /// Post-processed (alpha, merge, outline)
    PostProcessed,
}

/// Settings snapshot for a post-processed version
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PostProcessSettings {
    /// Whether alpha normalization was applied
    pub alpha_enabled: bool,
    pub alpha_low_cutoff: Option<u8>,
    pub alpha_high_min: Option<u8>,

    /// Whether color merge was applied
    pub merge_enabled: bool,
    pub merge_threshold: Option<f32>,

    /// Whether outline was applied
    pub outline_enabled: bool,
    pub outline_color: Option<(u8, u8, u8, u8)>,
    pub outline_thickness: Option<u32>,
}

/// Settings snapshot for a downscaled version
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DownscaleSettings {
    pub detected_scale: u32,
    pub auto_trim: bool,
    pub pad_canvas: Option<u32>,
}

/// A specific version of an image in the lineage tree
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ImageVersion {
    /// Unique ID for this version (e.g., "v1", "v2", "v3")
    pub id: String,
    /// Type of processing
    pub version_type: VersionType,
    /// Path to cached image (relative to .pixels/cache/)
    pub cache_path: Option<String>,
    /// Parent version ID (None for original)
    pub parent: Option<String>,
    /// Settings used to create this version
    #[serde(skip_serializing_if = "Option::is_none")]
    pub post_process_settings: Option<PostProcessSettings>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub downscale_settings: Option<DownscaleSettings>,
    /// Creation timestamp (ISO 8601)
    pub created: String,
}

// ============================================================================
// SOURCE TRACKING
// ============================================================================

/// Detected type of source image
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(rename_all = "snake_case")]
pub enum SourceType {
    /// AI-generated upscaled pixel art (needs downscaling)
    AiUpscaled,
    /// Native pixel art (no downscaling needed)
    NativePixelArt,
    /// Unknown/undetected
    Unknown,
}

/// State for a single source image
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SourceState {
    /// SHA-256 hash of original file content
    pub hash: String,
    /// Detected image type
    pub detected_type: SourceType,
    /// Detected upscale factor (if AI-upscaled)
    pub detected_scale: Option<u32>,
    /// All versions in lineage tree
    pub versions: Vec<ImageVersion>,
    /// Currently active version ID
    pub current_version: String,
}

impl SourceState {
    /// Create new source state for an original image
    pub fn new(hash: String) -> Self {
        let now = chrono::Utc::now().to_rfc3339();
        Self {
            hash,
            detected_type: SourceType::Unknown,
            detected_scale: None,
            versions: vec![ImageVersion {
                id: "v1".to_string(),
                version_type: VersionType::Original,
                cache_path: None,
                parent: None,
                post_process_settings: None,
                downscale_settings: None,
                created: now,
            }],
            current_version: "v1".to_string(),
        }
    }

    /// Get the next version ID
    pub fn next_version_id(&self) -> String {
        format!("v{}", self.versions.len() + 1)
    }

    /// Find a version by ID
    pub fn get_version(&self, id: &str) -> Option<&ImageVersion> {
        self.versions.iter().find(|v| v.id == id)
    }

    /// Add a new version
    pub fn add_version(&mut self, version: ImageVersion) {
        self.versions.push(version);
    }
}

// ============================================================================
// WORKSPACE STATE
// ============================================================================

/// Global settings applied to new processing operations
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GlobalSettings {
    pub merge_threshold: f32,
    pub outline_color: (u8, u8, u8, u8),
    pub outline_thickness: u32,
}

impl Default for GlobalSettings {
    fn default() -> Self {
        Self {
            merge_threshold: 3.0,
            outline_color: (17, 6, 2, 255),
            outline_thickness: 1,
        }
    }
}

/// Export settings
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ExportSettings {
    pub destination: Option<String>,
    #[serde(default)]
    pub naming: ExportNaming,
}

impl Default for ExportSettings {
    fn default() -> Self {
        Self {
            destination: None,
            naming: ExportNaming::Same,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
#[serde(rename_all = "snake_case")]
pub enum ExportNaming {
    #[default]
    Same,
    Suffix(String),
}

/// Complete workspace state
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct WorkspaceState {
    /// Schema version for migrations
    pub version: u32,
    /// Workspace root directory
    pub workspace: String,
    /// Per-source state, keyed by relative path from workspace
    pub sources: HashMap<String, SourceState>,
    /// Global processing settings
    pub global_settings: GlobalSettings,
    /// Export settings
    pub export_settings: ExportSettings,
}

impl WorkspaceState {
    /// Create new empty workspace state
    pub fn new(workspace_path: &str) -> Self {
        Self {
            version: 1,
            workspace: workspace_path.to_string(),
            sources: HashMap::new(),
            global_settings: GlobalSettings::default(),
            export_settings: ExportSettings::default(),
        }
    }
}

// ============================================================================
// WORKSPACE MANAGER
// ============================================================================

/// Manages the .pixels folder and state for a workspace
pub struct WorkspaceManager {
    /// Root workspace directory (user's folder)
    workspace_root: PathBuf,
    /// .pixels directory path
    pixels_dir: PathBuf,
    /// Current state
    state: WorkspaceState,
}

impl WorkspaceManager {
    /// Open or create workspace state for a directory
    pub fn open(workspace_path: &Path) -> Result<Self> {
        let pixels_dir = workspace_path.join(".pixels");
        let state_path = pixels_dir.join("state.json");

        let state = if state_path.exists() {
            // Load existing state
            let content = fs::read_to_string(&state_path)?;
            serde_json::from_str(&content)?
        } else {
            // Create new state
            WorkspaceState::new(&workspace_path.to_string_lossy())
        };

        Ok(Self {
            workspace_root: workspace_path.to_path_buf(),
            pixels_dir,
            state,
        })
    }

    /// Create manager from existing state (for saving updates)
    pub fn from_state(workspace_path: &Path, state: WorkspaceState) -> Self {
        let pixels_dir = workspace_path.join(".pixels");
        Self {
            workspace_root: workspace_path.to_path_buf(),
            pixels_dir,
            state,
        }
    }

    /// Consume manager and return the state
    pub fn into_state(self) -> WorkspaceState {
        self.state
    }

    /// Get a reference to the current state
    pub fn state(&self) -> &WorkspaceState {
        &self.state
    }

    /// Initialize .pixels folder structure
    pub fn init(&self) -> Result<()> {
        fs::create_dir_all(self.pixels_dir.join("cache"))?;
        fs::create_dir_all(self.pixels_dir.join("thumbnails"))?;
        self.save()?;
        Ok(())
    }

    /// Save current state to disk
    pub fn save(&self) -> Result<()> {
        fs::create_dir_all(&self.pixels_dir)?;
        let state_path = self.pixels_dir.join("state.json");
        let content = serde_json::to_string_pretty(&self.state)?;
        fs::write(state_path, content)?;
        Ok(())
    }

    /// Get workspace root path
    pub fn workspace_root(&self) -> &Path {
        &self.workspace_root
    }

    /// Get .pixels directory path
    pub fn pixels_dir(&self) -> &Path {
        &self.pixels_dir
    }

    /// Get cache directory path
    pub fn cache_dir(&self) -> PathBuf {
        self.pixels_dir.join("cache")
    }

    /// Get thumbnails directory path
    pub fn thumbnails_dir(&self) -> PathBuf {
        self.pixels_dir.join("thumbnails")
    }

    /// Get or create source state for an image
    pub fn get_or_create_source(&mut self, relative_path: &str) -> Result<&mut SourceState> {
        if !self.state.sources.contains_key(relative_path) {
            // Calculate hash of original file
            let full_path = self.workspace_root.join(relative_path);
            let hash = hash_file(&full_path)?;
            self.state.sources.insert(
                relative_path.to_string(),
                SourceState::new(hash),
            );
        }
        Ok(self.state.sources.get_mut(relative_path).unwrap())
    }

    /// Get source state (read-only)
    pub fn get_source(&self, relative_path: &str) -> Option<&SourceState> {
        self.state.sources.get(relative_path)
    }

    /// Get all source paths
    pub fn source_paths(&self) -> Vec<&String> {
        self.state.sources.keys().collect()
    }

    /// Get global settings
    pub fn global_settings(&self) -> &GlobalSettings {
        &self.state.global_settings
    }

    /// Update global settings
    pub fn set_global_settings(&mut self, settings: GlobalSettings) {
        self.state.global_settings = settings;
    }

    /// Generate cache filename for a version
    pub fn cache_filename(&self, source_hash: &str, version_id: &str, suffix: &str) -> String {
        format!("{}_{}{}.png", &source_hash[..12], version_id, suffix)
    }

    /// Get full cache path for a cached file
    pub fn cache_path(&self, filename: &str) -> PathBuf {
        self.cache_dir().join(filename)
    }

    /// Get full thumbnail path for a source
    pub fn thumbnail_path(&self, relative_path: &str) -> PathBuf {
        // Use sanitized filename for thumbnail
        let safe_name = relative_path.replace(['/', '\\', ':'], "_");
        self.thumbnails_dir().join(format!("{}.png", safe_name))
    }
}

// ============================================================================
// UTILITY FUNCTIONS
// ============================================================================

/// Calculate SHA-256 hash of a file
pub fn hash_file(path: &Path) -> Result<String> {
    let content = fs::read(path)
        .map_err(|e| PixelsError::Io(e))?;
    let mut hasher = Sha256::new();
    hasher.update(&content);
    let result = hasher.finalize();
    Ok(format!("{:x}", result))
}

/// Calculate SHA-256 hash of image bytes
pub fn hash_bytes(data: &[u8]) -> String {
    let mut hasher = Sha256::new();
    hasher.update(data);
    let result = hasher.finalize();
    format!("{:x}", result)
}

/// Get current timestamp as ISO 8601 string
pub fn now_iso() -> String {
    chrono::Utc::now().to_rfc3339()
}

// ============================================================================
// TESTS
// ============================================================================

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_source_state_new() {
        let state = SourceState::new("abc123".to_string());
        assert_eq!(state.hash, "abc123");
        assert_eq!(state.current_version, "v1");
        assert_eq!(state.versions.len(), 1);
        assert_eq!(state.versions[0].version_type, VersionType::Original);
    }

    #[test]
    fn test_next_version_id() {
        let mut state = SourceState::new("abc123".to_string());
        assert_eq!(state.next_version_id(), "v2");

        state.versions.push(ImageVersion {
            id: "v2".to_string(),
            version_type: VersionType::Downscaled,
            cache_path: Some("test.png".to_string()),
            parent: Some("v1".to_string()),
            post_process_settings: None,
            downscale_settings: None,
            created: now_iso(),
        });

        assert_eq!(state.next_version_id(), "v3");
    }

    #[test]
    fn test_global_settings_default() {
        let settings = GlobalSettings::default();
        assert_eq!(settings.merge_threshold, 3.0);
        assert_eq!(settings.outline_color, (17, 6, 2, 255));
        assert_eq!(settings.outline_thickness, 1);
    }

    #[test]
    fn test_hash_bytes() {
        let hash1 = hash_bytes(b"hello");
        let hash2 = hash_bytes(b"hello");
        let hash3 = hash_bytes(b"world");

        assert_eq!(hash1, hash2);
        assert_ne!(hash1, hash3);
        assert_eq!(hash1.len(), 64); // SHA-256 produces 64 hex chars
    }
}
