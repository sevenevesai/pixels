"""
Project management - lightweight system for storing project directories and per-project settings.
"""
from pathlib import Path
from typing import List, Optional, Dict
from PySide6.QtCore import QSettings


class Project:
    """Represents a single project."""
    
    def __init__(self, name: str, path: Path):
        self.name = name
        self.path = path
        
    def to_dict(self) -> dict:
        return {
            'name': self.name,
            'path': str(self.path)
        }
    
    @staticmethod
    def from_dict(data: dict) -> 'Project':
        return Project(data['name'], Path(data['path']))


class ProjectManager:
    """Manages projects and their settings."""
    
    def __init__(self, settings: QSettings):
        self.settings = settings
        self.current_project: Optional[Project] = None
        
    def get_projects(self) -> List[Project]:
        """Get all saved projects."""
        projects_data = self.settings.value("projects/list", [])
        if not projects_data:
            return []
        
        projects = []
        for data in projects_data:
            try:
                projects.append(Project.from_dict(data))
            except Exception as e:
                print(f"Error loading project: {e}")
        
        return projects
    
    def add_project(self, name: str, path: Path) -> Project:
        """Add a new project."""
        # Check if project with this path already exists
        existing = self.get_projects()
        for proj in existing:
            if proj.path == path:
                # Update name if different
                if proj.name != name:
                    proj.name = name
                    self.save_projects(existing)
                return proj
        
        # Create new project
        project = Project(name, path)
        existing.append(project)
        self.save_projects(existing)
        
        return project
    
    def remove_project(self, project: Project):
        """Remove a project."""
        projects = self.get_projects()
        projects = [p for p in projects if p.path != project.path]
        self.save_projects(projects)
        
        # Clear current if it was removed
        if self.current_project and self.current_project.path == project.path:
            self.current_project = None
    
    def save_projects(self, projects: List[Project]):
        """Save projects list."""
        projects_data = [p.to_dict() for p in projects]
        self.settings.setValue("projects/list", projects_data)
    
    def set_current_project(self, project: Optional[Project]):
        """Set the current active project."""
        self.current_project = project
        if project:
            self.settings.setValue("projects/current", str(project.path))
        else:
            self.settings.setValue("projects/current", None)
    
    def get_current_project(self) -> Optional[Project]:
        """Get current project, loading from settings if needed."""
        if self.current_project:
            return self.current_project
        
        # Try to load from settings
        current_path = self.settings.value("projects/current")
        if current_path:
            projects = self.get_projects()
            for proj in projects:
                if str(proj.path) == current_path:
                    self.current_project = proj
                    return proj
        
        return None
    
    # Per-project folder management
    def get_project_folder(self, project: Project, tab_name: str) -> Optional[Path]:
        """Get the folder path for a specific tab in a project."""
        key = f"project:{project.path}/folders/{tab_name}"
        folder_str = self.settings.value(key)
        #print(f"[ProjectManager] Getting {tab_name} folder: key={key}, value={folder_str}")  # Debug
        if folder_str:
            return Path(folder_str)
        return None

    def set_project_folder(self, project: Project, tab_name: str, folder: Path):
        """Set the folder path for a specific tab in a project."""
        key = f"project:{project.path}/folders/{tab_name}"
        #print(f"[ProjectManager] Setting {tab_name} folder: key={key}, value={folder}")  # Debug
        self.settings.setValue(key, str(folder))

    # Per-project settings
    def get_project_setting(self, project: Project, key: str, default=None):
        """Get a project-specific setting."""
        full_key = f"project:{project.path}/settings/{key}"
        value = self.settings.value(full_key)
        if value is None:
            return default
        
        # Handle type conversion
        if default is not None:
            if isinstance(default, bool):
                return value in (True, 'true', '1', 1)
            elif isinstance(default, (int, float)) and isinstance(value, str):
                try:
                    return type(default)(value)
                except (ValueError, TypeError):
                    return default
        
        return value
    
    def set_project_setting(self, project: Project, key: str, value):
        """Set a project-specific setting."""
        full_key = f"project:{project.path}/settings/{key}"
        self.settings.setValue(full_key, value)