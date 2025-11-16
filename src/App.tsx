import { useState, useEffect } from "react";
import { invoke } from "@tauri-apps/api/core";
import { open } from "@tauri-apps/plugin-dialog";
import { readDir, exists } from "@tauri-apps/plugin-fs";
import { convertFileSrc } from "@tauri-apps/api/core";
import { join, sep } from "@tauri-apps/api/path";
import "./App.css";

interface Project {
  id: number;
  name: string;
  path: string;
}

interface ImageFile {
  name: string;
  path: string;
  selected: boolean;
}

type TabType = "downscale" | "process" | "pack";

// Helper to get setting key for a project and tab
function getProjectSettingKey(projectId: number, tab: string, key: string) {
  return `project_${projectId}_${tab}_${key}`;
}

function App() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [currentProjectId, setCurrentProjectId] = useState<number | null>(null);
  const [activeTab, setActiveTab] = useState<TabType>("downscale");

  useEffect(() => {
    loadProjects();
    loadCurrentProject();
  }, []);

  async function loadProjects() {
    try {
      const projs = await invoke<Project[]>("get_projects");
      setProjects(projs);
    } catch (err) {
      console.error("Failed to load projects:", err);
    }
  }

  async function loadCurrentProject() {
    try {
      const id = await invoke<number | null>("get_current_project_id");
      setCurrentProjectId(id);
    } catch (err) {
      console.error("Failed to load current project:", err);
    }
  }

  async function addProject() {
    const projectName = prompt("Project Name:");
    if (!projectName) return;

    try {
      const directory = await open({
        directory: true,
        multiple: false,
      });

      if (!directory) return;

      const project = await invoke<Project>("add_project", {
        name: projectName,
        path: directory,
      });

      setProjects([...projects, project]);
      setCurrentProjectId(project.id);
      await invoke("set_current_project_id", { id: project.id });
    } catch (err) {
      console.error("Failed to add project:", err);
      alert(`Error: ${err}`);
    }
  }

  async function selectProject(id: number) {
    try {
      setCurrentProjectId(id);
      await invoke("set_current_project_id", { id });
    } catch (err) {
      console.error("Failed to select project:", err);
    }
  }

  async function deleteProject(id: number) {
    if (!confirm("Remove this project? (files will not be deleted)")) return;

    try {
      await invoke("remove_project", { id });
      setProjects(projects.filter((p) => p.id !== id));
      if (currentProjectId === id) {
        setCurrentProjectId(null);
        await invoke("set_current_project_id", { id: null });
      }
    } catch (err) {
      console.error("Failed to delete project:", err);
    }
  }

  const currentProject = projects.find((p) => p.id === currentProjectId);

  return (
    <div className="app">
      <header className="app-header">
        <h1>Pixels Toolkit</h1>
        <div className="header-actions">
          <a
            href="https://www.paypal.com/donate/?hosted_button_id=XJUQUE78JATMN"
            target="_blank"
            rel="noopener noreferrer"
            className="donate-btn"
          >
            ❤️ Donate
          </a>
        </div>
      </header>

      <div className="project-bar">
        <button onClick={addProject} className="btn-primary">
          + Add Project
        </button>

        <select
          value={currentProjectId ?? ""}
          onChange={(e) => selectProject(Number(e.target.value))}
          disabled={projects.length === 0}
        >
          <option value="">Select Project...</option>
          {projects.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </select>

        {currentProject && (
          <div className="current-project">
            <strong>Current:</strong> {currentProject.name}
            <button
              onClick={() => deleteProject(currentProject.id)}
              className="btn-danger-small"
              title="Delete project"
            >
              ✕
            </button>
          </div>
        )}
      </div>

      <div className="tabs">
        <button
          className={`tab ${activeTab === "downscale" ? "active" : ""}`}
          onClick={() => setActiveTab("downscale")}
        >
          🔍 AI Downscale
        </button>
        <button
          className={`tab ${activeTab === "process" ? "active" : ""}`}
          onClick={() => setActiveTab("process")}
        >
          🎨 Post-Process
        </button>
        <button
          className={`tab ${activeTab === "pack" ? "active" : ""}`}
          onClick={() => setActiveTab("pack")}
        >
          📦 Pack Sprites
        </button>
      </div>

      <div className="tab-content">
        {!currentProject ? (
          <div className="empty-state">
            <h2>No Project Selected</h2>
            <p>Add or select a project to begin</p>
          </div>
        ) : (
          <>
            {activeTab === "downscale" && (
              <DownscaleTab key={currentProject.id} project={currentProject} />
            )}
            {activeTab === "process" && (
              <ProcessTab key={currentProject.id} project={currentProject} />
            )}
            {activeTab === "pack" && (
              <PackTab key={currentProject.id} project={currentProject} />
            )}
          </>
        )}
      </div>
    </div>
  );
}

// Downscale Tab with full features and settings persistence
function DownscaleTab({ project }: { project: Project }) {
  const [inputFolder, setInputFolder] = useState(project.path);
  const [outputFolderName, setOutputFolderName] = useState("downscaled");
  const [images, setImages] = useState<ImageFile[]>([]);
  const [processing, setProcessing] = useState(false);
  const [progress, setProgress] = useState("");

  // Settings
  const [bgRemovalMode, setBgRemovalMode] = useState("conservative");
  const [bgTolerance, setBgTolerance] = useState(15);
  const [bgEdgeTolerance, setBgEdgeTolerance] = useState(25);
  const [autoTrim, setAutoTrim] = useState(true);
  const [enableFineTune, setEnableFineTune] = useState(true);
  const [padCanvas, setPadCanvas] = useState(true);
  const [canvasMultiple, setCanvasMultiple] = useState(16);
  const [preserveDarkLines, setPreserveDarkLines] = useState(true);
  const [darkLineThreshold, setDarkLineThreshold] = useState(50);

  // Load settings on mount
  useEffect(() => {
    loadSettings();
  }, [project.id]);

  useEffect(() => {
    if (inputFolder) {
      loadImages();
    }
  }, [inputFolder]);

  async function loadSettings() {
    try {
      // Load project-specific folder
      const savedFolder = await invoke<string | null>("get_project_setting", {
        projectId: project.id,
        key: "downscale_input_folder",
      });
      if (savedFolder) {
        setInputFolder(savedFolder);
      }

      // Load project-specific output folder name
      const savedOutputName = await invoke<string | null>("get_project_setting", {
        projectId: project.id,
        key: "downscale_output_folder",
      });
      if (savedOutputName) {
        setOutputFolderName(savedOutputName);
      }

      // Load global settings
      const loadSetting = async (key: string, defaultVal: any, setter: Function) => {
        try {
          const val = await invoke<string | null>("get_app_setting", { key });
          if (val !== null) {
            if (typeof defaultVal === "boolean") {
              setter(val === "true");
            } else if (typeof defaultVal === "number") {
              setter(Number(val));
            } else {
              setter(val);
            }
          }
        } catch (e) {
          console.warn(`Failed to load setting ${key}:`, e);
        }
      };

      await loadSetting("downscale_bg_removal_mode", bgRemovalMode, setBgRemovalMode);
      await loadSetting("downscale_bg_tolerance", bgTolerance, setBgTolerance);
      await loadSetting("downscale_bg_edge_tolerance", bgEdgeTolerance, setBgEdgeTolerance);
      await loadSetting("downscale_auto_trim", autoTrim, setAutoTrim);
      await loadSetting("downscale_enable_fine_tune", enableFineTune, setEnableFineTune);
      await loadSetting("downscale_pad_canvas", padCanvas, setPadCanvas);
      await loadSetting("downscale_canvas_multiple", canvasMultiple, setCanvasMultiple);
      await loadSetting("downscale_preserve_dark_lines", preserveDarkLines, setPreserveDarkLines);
      await loadSetting("downscale_dark_line_threshold", darkLineThreshold, setDarkLineThreshold);
    } catch (err) {
      console.error("Failed to load settings:", err);
    }
  }

  async function saveSetting(key: string, value: any) {
    try {
      await invoke("set_app_setting", {
        key,
        value: String(value),
      });
    } catch (err) {
      console.error(`Failed to save setting ${key}:`, err);
    }
  }

  async function saveProjectSetting(key: string, value: string) {
    try {
      await invoke("set_project_setting", {
        projectId: project.id,
        key,
        value,
      });
    } catch (err) {
      console.error(`Failed to save project setting ${key}:`, err);
    }
  }

  async function selectInputFolder() {
    try {
      const directory = await open({
        directory: true,
        multiple: false,
        defaultPath: inputFolder,
      });

      if (directory) {
        setInputFolder(directory as string);
        await saveProjectSetting("downscale_input_folder", directory as string);
      }
    } catch (err) {
      console.error("Failed to select folder:", err);
    }
  }

  async function loadImages() {
    try {
      const entries = await readDir(inputFolder);
      const imageFiles: ImageFile[] = [];

      for (const entry of entries) {
        const name = entry.name.toLowerCase();
        if (
          !entry.isDirectory &&
          (name.endsWith(".png") ||
            name.endsWith(".jpg") ||
            name.endsWith(".jpeg") ||
            name.endsWith(".bmp") ||
            name.endsWith(".webp"))
        ) {
          // Build path - use backslash on Windows for local file paths
          const pathSeparator = inputFolder.includes("\\") ? "\\" : "/";
          const fullPath = `${inputFolder}${pathSeparator}${entry.name}`;

          imageFiles.push({
            name: entry.name,
            path: fullPath,
            selected: true,
          });
        }
      }

      setImages(imageFiles.sort((a, b) => a.name.localeCompare(b.name)));
    } catch (err) {
      console.error("Failed to load images:", err);
      setImages([]);
    }
  }

  async function smartSelect() {
    try {
      const pathSeparator = project.path.includes("\\") ? "\\" : "/";
      const outputPath = `${project.path}${pathSeparator}${outputFolderName}`;

      // Check if output folder exists
      const outputExists = await exists(outputPath);
      if (!outputExists) {
        // No output folder, select all
        setImages((imgs) => imgs.map((img) => ({ ...img, selected: true })));
        return;
      }

      const outputEntries = await readDir(outputPath);
      const outputNames = new Set(outputEntries.map((e) => e.name));

      setImages((imgs) =>
        imgs.map((img) => ({
          ...img,
          selected: !outputNames.has(img.name),
        }))
      );
    } catch (err) {
      console.warn("Smart select failed:", err);
      // On error, select all
      setImages((imgs) => imgs.map((img) => ({ ...img, selected: true })));
    }
  }

  function toggleImage(index: number) {
    setImages((imgs) =>
      imgs.map((img, i) => (i === index ? { ...img, selected: !img.selected } : img))
    );
  }

  function selectAll() {
    setImages((imgs) => imgs.map((img) => ({ ...img, selected: true })));
  }

  function deselectAll() {
    setImages((imgs) => imgs.map((img) => ({ ...img, selected: false })));
  }

  async function processImages() {
    const selectedImages = images.filter((img) => img.selected);
    if (selectedImages.length === 0) {
      alert("No images selected");
      return;
    }

    setProcessing(true);
    setProgress(`Processing 0/${selectedImages.length}...`);

    try {
      const outputPath = await join(project.path, outputFolderName);

      for (let i = 0; i < selectedImages.length; i++) {
        const img = selectedImages[i];
        setProgress(`Processing ${i + 1}/${selectedImages.length}: ${img.name}`);

        const outputFilePath = await join(outputPath, img.name);

        await invoke("downscale_image_command", {
          inputPath: img.path,
          outputPath: outputFilePath,
          settings: {
            bg_removal_mode: bgRemovalMode,
            bg_tolerance: bgTolerance,
            bg_edge_tolerance: bgEdgeTolerance,
            preserve_dark_lines: preserveDarkLines,
            dark_line_threshold: darkLineThreshold,
            auto_trim: autoTrim,
            enable_fine_tune: enableFineTune,
            pad_canvas: padCanvas,
            canvas_multiple: canvasMultiple,
          },
        });
      }

      setProgress(`Complete! Processed ${selectedImages.length} images`);
      setTimeout(() => setProgress(""), 3000);
    } catch (err) {
      alert(`Error: ${err}`);
    } finally {
      setProcessing(false);
    }
  }

  const selectedCount = images.filter((img) => img.selected).length;

  return (
    <div className="tab-layout">
      <div className="main-area">
        <div className="toolbar">
          <button onClick={selectInputFolder} className="btn">
            📁 Select Input Folder
          </button>
          <button onClick={loadImages} className="btn">
            🔄 Refresh
          </button>
          <button onClick={smartSelect} className="btn">
            ✨ Smart Select
          </button>
          <button onClick={selectAll} className="btn-small">
            Select All
          </button>
          <button onClick={deselectAll} className="btn-small">
            Deselect All
          </button>
          <div className="folder-path">
            <strong>Input:</strong> {inputFolder}
          </div>
        </div>

        {progress && <div className="progress-message">{progress}</div>}

        <div className="image-grid">
          {images.length === 0 ? (
            <div className="empty-grid">No images found in folder</div>
          ) : (
            images.map((img, i) => (
              <div
                key={i}
                className={`image-card ${img.selected ? "selected" : ""}`}
                onClick={() => toggleImage(i)}
              >
                <div className="image-thumb">
                  <img src={convertFileSrc(img.path)} alt={img.name} />
                </div>
                <div className="image-name">{img.name}</div>
                {img.selected && <div className="selected-indicator">✓</div>}
              </div>
            ))
          )}
        </div>

        <div className="action-bar">
          <button
            onClick={processImages}
            disabled={selectedCount === 0 || processing}
            className="btn-process"
          >
            {processing
              ? "Processing..."
              : `🔍 Downscale ${selectedCount} Image${selectedCount !== 1 ? "s" : ""}`}
          </button>
        </div>
      </div>

      <div className="settings-panel">
        <h3>Settings</h3>

        <div className="setting-group">
          <label>Output Folder Name</label>
          <input
            type="text"
            value={outputFolderName}
            onChange={(e) => {
              setOutputFolderName(e.target.value);
              saveProjectSetting("downscale_output_folder", e.target.value);
            }}
          />
          <small>Folder name relative to project path</small>
        </div>

        <div className="setting-group">
          <label>
            <input
              type="checkbox"
              checked={enableFineTune}
              onChange={(e) => {
                setEnableFineTune(e.target.checked);
                saveSetting("downscale_enable_fine_tune", e.target.checked);
              }}
            />
            Enable Fine-Tune
          </label>
          <small>Test fractional scale factors for better results</small>
        </div>

        <hr />

        <div className="setting-group">
          <label>Background Removal</label>
          <select
            value={bgRemovalMode}
            onChange={(e) => {
              setBgRemovalMode(e.target.value);
              saveSetting("downscale_bg_removal_mode", e.target.value);
            }}
          >
            <option value="conservative">Conservative</option>
            <option value="aggressive">Aggressive</option>
            <option value="none">None</option>
          </select>
        </div>

        <div className="setting-group">
          <label>BG Tolerance: {bgTolerance}</label>
          <input
            type="range"
            min="5"
            max="50"
            value={bgTolerance}
            onChange={(e) => {
              setBgTolerance(Number(e.target.value));
              saveSetting("downscale_bg_tolerance", e.target.value);
            }}
          />
        </div>

        <div className="setting-group">
          <label>BG Edge Tolerance: {bgEdgeTolerance}</label>
          <input
            type="range"
            min="10"
            max="80"
            value={bgEdgeTolerance}
            onChange={(e) => {
              setBgEdgeTolerance(Number(e.target.value));
              saveSetting("downscale_bg_edge_tolerance", e.target.value);
            }}
          />
        </div>

        <hr />

        <div className="setting-group">
          <label>
            <input
              type="checkbox"
              checked={preserveDarkLines}
              onChange={(e) => {
                setPreserveDarkLines(e.target.checked);
                saveSetting("downscale_preserve_dark_lines", e.target.checked);
              }}
            />
            Preserve Dark Lines
          </label>
        </div>

        <div className="setting-group">
          <label>Dark Line Threshold: {darkLineThreshold}</label>
          <input
            type="range"
            min="0"
            max="150"
            value={darkLineThreshold}
            onChange={(e) => {
              setDarkLineThreshold(Number(e.target.value));
              saveSetting("downscale_dark_line_threshold", e.target.value);
            }}
          />
        </div>

        <hr />

        <div className="setting-group">
          <label>
            <input
              type="checkbox"
              checked={autoTrim}
              onChange={(e) => {
                setAutoTrim(e.target.checked);
                saveSetting("downscale_auto_trim", e.target.checked);
              }}
            />
            Auto Trim Transparency
          </label>
        </div>

        <div className="setting-group">
          <label>
            <input
              type="checkbox"
              checked={padCanvas}
              onChange={(e) => {
                setPadCanvas(e.target.checked);
                saveSetting("downscale_pad_canvas", e.target.checked);
              }}
            />
            Pad Canvas to Multiple
          </label>
        </div>

        <div className="setting-group">
          <label>Canvas Multiple: {canvasMultiple}</label>
          <input
            type="range"
            min="8"
            max="128"
            step="8"
            value={canvasMultiple}
            onChange={(e) => {
              setCanvasMultiple(Number(e.target.value));
              saveSetting("downscale_canvas_multiple", e.target.value);
            }}
          />
        </div>
      </div>
    </div>
  );
}

// Process Tab - Simplified for now, will add full implementation
function ProcessTab({ project }: { project: Project }) {
  return (
    <div className="tab-layout">
      <div className="main-area">
        <div className="empty-state">
          <h2>Post-Process Tab</h2>
          <p>Implementation in progress...</p>
        </div>
      </div>
    </div>
  );
}

// Pack Tab - Simplified for now
function PackTab({ project }: { project: Project }) {
  return (
    <div className="tab-layout">
      <div className="main-area">
        <div className="empty-state">
          <h2>Pack Sprites Tab</h2>
          <p>Implementation in progress...</p>
        </div>
      </div>
    </div>
  );
}

export default App;
