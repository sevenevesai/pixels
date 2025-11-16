use rusqlite::{Connection, params};
use serde::{Deserialize, Serialize};
use std::path::PathBuf;
use std::sync::{Arc, Mutex};
use crate::error::Result;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Project {
    pub id: i64,
    pub name: String,
    pub path: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProjectSettings {
    pub downscale_folder: Option<String>,
    pub process_folder: Option<String>,
    pub pack_folder: Option<String>,
    pub downscale_output_folder: String,
    pub process_output_folder: String,
    pub pack_output_filename: String,
}

impl Default for ProjectSettings {
    fn default() -> Self {
        Self {
            downscale_folder: None,
            process_folder: None,
            pack_folder: None,
            downscale_output_folder: "downscaled".to_string(),
            process_output_folder: "processed".to_string(),
            pack_output_filename: "spritesheet.png".to_string(),
        }
    }
}

pub struct Database {
    conn: Arc<Mutex<Connection>>,
}

impl Database {
    pub fn new(db_path: PathBuf) -> Result<Self> {
        let conn = Connection::open(db_path)?;

        // Create tables
        conn.execute(
            "CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                path TEXT NOT NULL UNIQUE,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL
            )",
            [],
        )?;

        conn.execute(
            "CREATE TABLE IF NOT EXISTS project_settings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                key TEXT NOT NULL,
                value TEXT,
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE,
                UNIQUE(project_id, key)
            )",
            [],
        )?;

        conn.execute(
            "CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )",
            [],
        )?;

        Ok(Self {
            conn: Arc::new(Mutex::new(conn)),
        })
    }

    // Project operations

    pub fn add_project(&self, name: String, path: String) -> Result<Project> {
        let conn = self.conn.lock().unwrap();
        let now = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_secs() as i64;

        conn.execute(
            "INSERT INTO projects (name, path, created_at, updated_at) VALUES (?1, ?2, ?3, ?4)",
            params![name, path, now, now],
        )?;

        let id = conn.last_insert_rowid();

        Ok(Project {
            id,
            name,
            path,
        })
    }

    pub fn get_projects(&self) -> Result<Vec<Project>> {
        let conn = self.conn.lock().unwrap();
        let mut stmt = conn.prepare("SELECT id, name, path FROM projects ORDER BY updated_at DESC")?;

        let projects = stmt
            .query_map([], |row| {
                Ok(Project {
                    id: row.get(0)?,
                    name: row.get(1)?,
                    path: row.get(2)?,
                })
            })?
            .collect::<std::result::Result<Vec<_>, _>>()?;

        Ok(projects)
    }

    pub fn get_project_by_id(&self, id: i64) -> Result<Option<Project>> {
        let conn = self.conn.lock().unwrap();
        let mut stmt = conn.prepare("SELECT id, name, path FROM projects WHERE id = ?1")?;

        let mut rows = stmt.query(params![id])?;

        if let Some(row) = rows.next()? {
            Ok(Some(Project {
                id: row.get(0)?,
                name: row.get(1)?,
                path: row.get(2)?,
            }))
        } else {
            Ok(None)
        }
    }

    pub fn remove_project(&self, id: i64) -> Result<()> {
        let conn = self.conn.lock().unwrap();
        conn.execute("DELETE FROM projects WHERE id = ?1", params![id])?;
        Ok(())
    }

    pub fn update_project_timestamp(&self, id: i64) -> Result<()> {
        let conn = self.conn.lock().unwrap();
        let now = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_secs() as i64;

        conn.execute(
            "UPDATE projects SET updated_at = ?1 WHERE id = ?2",
            params![now, id],
        )?;

        Ok(())
    }

    // Project settings operations

    pub fn set_project_setting(&self, project_id: i64, key: &str, value: &str) -> Result<()> {
        let conn = self.conn.lock().unwrap();
        conn.execute(
            "INSERT OR REPLACE INTO project_settings (project_id, key, value) VALUES (?1, ?2, ?3)",
            params![project_id, key, value],
        )?;
        Ok(())
    }

    pub fn get_project_setting(&self, project_id: i64, key: &str) -> Result<Option<String>> {
        let conn = self.conn.lock().unwrap();
        let mut stmt = conn.prepare("SELECT value FROM project_settings WHERE project_id = ?1 AND key = ?2")?;

        let mut rows = stmt.query(params![project_id, key])?;

        if let Some(row) = rows.next()? {
            Ok(row.get(0)?)
        } else {
            Ok(None)
        }
    }

    pub fn get_project_settings(&self, project_id: i64) -> Result<ProjectSettings> {
        let mut settings = ProjectSettings::default();

        if let Some(val) = self.get_project_setting(project_id, "downscale_folder")? {
            settings.downscale_folder = Some(val);
        }
        if let Some(val) = self.get_project_setting(project_id, "process_folder")? {
            settings.process_folder = Some(val);
        }
        if let Some(val) = self.get_project_setting(project_id, "pack_folder")? {
            settings.pack_folder = Some(val);
        }
        if let Some(val) = self.get_project_setting(project_id, "downscale_output_folder")? {
            settings.downscale_output_folder = val;
        }
        if let Some(val) = self.get_project_setting(project_id, "process_output_folder")? {
            settings.process_output_folder = val;
        }
        if let Some(val) = self.get_project_setting(project_id, "pack_output_filename")? {
            settings.pack_output_filename = val;
        }

        Ok(settings)
    }

    // App settings operations

    pub fn set_app_setting(&self, key: &str, value: &str) -> Result<()> {
        let conn = self.conn.lock().unwrap();
        conn.execute(
            "INSERT OR REPLACE INTO app_settings (key, value) VALUES (?1, ?2)",
            params![key, value],
        )?;
        Ok(())
    }

    pub fn get_app_setting(&self, key: &str) -> Result<Option<String>> {
        let conn = self.conn.lock().unwrap();
        let mut stmt = conn.prepare("SELECT value FROM app_settings WHERE key = ?1")?;

        let mut rows = stmt.query(params![key])?;

        if let Some(row) = rows.next()? {
            Ok(row.get(0)?)
        } else {
            Ok(None)
        }
    }

    pub fn get_current_project_id(&self) -> Result<Option<i64>> {
        if let Some(id_str) = self.get_app_setting("current_project_id")? {
            Ok(id_str.parse().ok())
        } else {
            Ok(None)
        }
    }

    pub fn set_current_project_id(&self, id: Option<i64>) -> Result<()> {
        if let Some(id) = id {
            self.set_app_setting("current_project_id", &id.to_string())?;
            self.update_project_timestamp(id)?;
        } else {
            let conn = self.conn.lock().unwrap();
            conn.execute("DELETE FROM app_settings WHERE key = 'current_project_id'", [])?;
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;

    #[test]
    fn test_database_operations() {
        let temp_db = std::env::temp_dir().join("test_pixels.db");
        let _ = fs::remove_file(&temp_db);

        let db = Database::new(temp_db.clone()).unwrap();

        // Add project
        let project = db.add_project("Test Project".to_string(), "/path/to/project".to_string()).unwrap();
        assert_eq!(project.name, "Test Project");

        // Get projects
        let projects = db.get_projects().unwrap();
        assert_eq!(projects.len(), 1);

        // Set/get setting
        db.set_project_setting(project.id, "downscale_folder", "/test/folder").unwrap();
        let val = db.get_project_setting(project.id, "downscale_folder").unwrap();
        assert_eq!(val, Some("/test/folder".to_string()));

        // Clean up
        let _ = fs::remove_file(&temp_db);
    }
}
