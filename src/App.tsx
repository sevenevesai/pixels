import { useState, useEffect } from "react";
import { invoke } from "@tauri-apps/api/core";
import { open } from "@tauri-apps/plugin-dialog";
import { readDir, exists, readFile } from "@tauri-apps/plugin-fs";
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
  thumbnail?: string; // base64 data URL
}

type TabType = "downscale" | "process" | "pack";

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
              <ProcessTab key={currentProject.id} />
            )}
            {activeTab === "pack" && (
              <PackTab key={currentProject.id} />
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
  const [outputFolder, setOutputFolder] = useState("");
  const [images, setImages] = useState<ImageFile[]>([]);
  const [processing, setProcessing] = useState(false);
  const [progress, setProgress] = useState("");

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
      // Load project-specific input folder
      const savedInputFolder = await invoke<string | null>("get_project_setting", {
        projectId: project.id,
        key: "downscale_input_folder",
      });
      if (savedInputFolder) {
        setInputFolder(savedInputFolder);
      }

      // Load project-specific output folder
      const savedOutputFolder = await invoke<string | null>("get_project_setting", {
        projectId: project.id,
        key: "downscale_output_folder",
      });
      if (savedOutputFolder) {
        setOutputFolder(savedOutputFolder);
      } else {
        // Default to project path + "downscaled" subfolder
        const pathSeparator = project.path.includes("\\") ? "\\" : "/";
        setOutputFolder(`${project.path}${pathSeparator}downscaled`);
      }
    } catch (err) {
      console.error("Failed to load settings:", err);
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

  async function selectOutputFolder() {
    try {
      const directory = await open({
        directory: true,
        multiple: false,
        defaultPath: outputFolder || project.path,
      });

      if (directory) {
        setOutputFolder(directory as string);
        await saveProjectSetting("downscale_output_folder", directory as string);
      }
    } catch (err) {
      console.error("Failed to select output folder:", err);
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

          // Read image file as base64 for thumbnail
          let thumbnail: string | undefined;
          try {
            const fileData = await readFile(fullPath);
            const base64 = btoa(
              new Uint8Array(fileData).reduce(
                (data, byte) => data + String.fromCharCode(byte),
                ""
              )
            );
            // Determine MIME type from extension
            let mimeType = "image/png";
            if (name.endsWith(".jpg") || name.endsWith(".jpeg")) {
              mimeType = "image/jpeg";
            } else if (name.endsWith(".webp")) {
              mimeType = "image/webp";
            } else if (name.endsWith(".bmp")) {
              mimeType = "image/bmp";
            }
            thumbnail = `data:${mimeType};base64,${base64}`;
          } catch (thumbErr) {
            console.warn(`Failed to load thumbnail for ${entry.name}:`, thumbErr);
          }

          imageFiles.push({
            name: entry.name,
            path: fullPath,
            selected: true,
            thumbnail,
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
    if (!outputFolder) {
      alert("Please select an output folder first");
      return;
    }

    try {
      // Check if output folder exists
      const outputExists = await exists(outputFolder);
      if (!outputExists) {
        // No output folder, select all
        setImages((imgs) => imgs.map((img) => ({ ...img, selected: true })));
        return;
      }

      const outputEntries = await readDir(outputFolder);
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

    if (!outputFolder) {
      alert("Please select an output folder first");
      return;
    }

    setProcessing(true);
    setProgress(`Processing 0/${selectedImages.length}...`);

    try {
      for (let i = 0; i < selectedImages.length; i++) {
        const img = selectedImages[i];
        setProgress(`Processing ${i + 1}/${selectedImages.length}: ${img.name}`);

        const pathSeparator = outputFolder.includes("\\") ? "\\" : "/";
        const outputFilePath = `${outputFolder}${pathSeparator}${img.name}`;

        await invoke("downscale_image_command", {
          inputPath: img.path,
          outputPath: outputFilePath,
          settings: {
            bg_removal_mode: "conservative",
            bg_tolerance: 15,
            bg_edge_tolerance: 30,
            preserve_dark_lines: false, // Post-processing handles outlines
            dark_line_threshold: 100,
            auto_trim: true,
            enable_fine_tune: true, // Always use fine-tuning for accuracy
            pad_canvas: false,
            canvas_multiple: 16,
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
                  {img.thumbnail ? (
                    <img src={img.thumbnail} alt={img.name} />
                  ) : (
                    <div style={{ color: "#999" }}>No preview</div>
                  )}
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
        <h3>Output</h3>

        <div className="setting-group">
          <label>Output Folder</label>
          <button onClick={selectOutputFolder} className="btn" style={{ width: "100%", marginBottom: "0.5rem" }}>
            📁 Select Output Folder
          </button>
          {outputFolder && (
            <small style={{ display: "block", marginTop: "0.5rem", wordBreak: "break-all" }}>
              {outputFolder}
            </small>
          )}
        </div>

        <hr />

        <div className="setting-group">
          <h4 style={{ margin: "0 0 0.5rem 0", fontSize: "0.95rem", color: "#666" }}>How it works</h4>
          <small style={{ lineHeight: "1.6" }}>
            AI-generated pixel art is actually high-resolution images that mimic nearest-neighbor upscaling.
            This tool automatically detects the grid pattern and downscales to the true pixel resolution.
          </small>
        </div>
      </div>
    </div>
  );
}

// Process Tab - Simplified for now, will add full implementation
function ProcessTab() {
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
function PackTab() {
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
