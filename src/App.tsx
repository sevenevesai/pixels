import { useState, useEffect } from "react";
import { invoke } from "@tauri-apps/api/core";
import { open } from "@tauri-apps/plugin-dialog";
import { readDir, exists, readFile } from "@tauri-apps/plugin-fs";
import "./App.css";
import { Workspace } from "./components/v2";
import { WorkspaceV3 } from "./components/v2/WorkspaceV3";

// Toggle this to switch between UI versions
// v1 = legacy tab-based UI
// v2 = batch/samples UI (complex)
// v3 = simplified image editor (current)
const UI_VERSION: 'v1' | 'v2' | 'v3' = 'v3';

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
  if (UI_VERSION === 'v3') {
    return <WorkspaceV3 />;
  }

  if (UI_VERSION === 'v2') {
    return <Workspace />;
  }

  // V1 UI - tab-based (legacy)
  return <AppV1 />;
}

function AppV1() {
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
            auto_trim: true,
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

// Process Tab - Full implementation with simplified UI
function ProcessTab({ project }: { project: Project }) {
  const [inputFolder, setInputFolder] = useState(project.path);
  const [outputFolder, setOutputFolder] = useState("");
  const [images, setImages] = useState<ImageFile[]>([]);
  const [processing, setProcessing] = useState(false);
  const [progress, setProgress] = useState("");

  // Simplified settings (best defaults from Python)
  const [enableColorSimplify, setEnableColorSimplify] = useState(true);
  const [labMergeThreshold, setLabMergeThreshold] = useState(3.0);
  const [enableOutline, setEnableOutline] = useState(true);
  const [outlineColor, setOutlineColor] = useState("#110602"); // (17, 6, 2) in hex
  const [outlineThickness, setOutlineThickness] = useState(1);

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
      const savedInputFolder = await invoke<string | null>("get_project_setting", {
        projectId: project.id,
        key: "process_input_folder",
      });
      if (savedInputFolder) setInputFolder(savedInputFolder);

      const savedOutputFolder = await invoke<string | null>("get_project_setting", {
        projectId: project.id,
        key: "process_output_folder",
      });
      if (savedOutputFolder) {
        setOutputFolder(savedOutputFolder);
      } else {
        const pathSeparator = project.path.includes("\\") ? "\\" : "/";
        setOutputFolder(`${project.path}${pathSeparator}processed`);
      }

      // Load saved settings
      const savedThreshold = await invoke<string | null>("get_project_setting", {
        projectId: project.id,
        key: "process_lab_threshold",
      });
      if (savedThreshold) setLabMergeThreshold(parseFloat(savedThreshold));

      const savedOutlineColor = await invoke<string | null>("get_project_setting", {
        projectId: project.id,
        key: "process_outline_color",
      });
      if (savedOutlineColor) setOutlineColor(savedOutlineColor);

      const savedThickness = await invoke<string | null>("get_project_setting", {
        projectId: project.id,
        key: "process_outline_thickness",
      });
      if (savedThickness) setOutlineThickness(parseInt(savedThickness));
    } catch (err) {
      console.error("Failed to load settings:", err);
    }
  }

  async function saveProjectSetting(key: string, value: string) {
    try {
      await invoke("set_project_setting", { projectId: project.id, key, value });
    } catch (err) {
      console.error(`Failed to save setting ${key}:`, err);
    }
  }

  async function selectInputFolder() {
    try {
      const directory = await open({ directory: true, multiple: false, defaultPath: inputFolder });
      if (directory) {
        setInputFolder(directory as string);
        await saveProjectSetting("process_input_folder", directory as string);
      }
    } catch (err) {
      console.error("Failed to select folder:", err);
    }
  }

  async function selectOutputFolder() {
    try {
      const directory = await open({ directory: true, multiple: false, defaultPath: outputFolder || project.path });
      if (directory) {
        setOutputFolder(directory as string);
        await saveProjectSetting("process_output_folder", directory as string);
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
        if (!entry.isDirectory && (name.endsWith(".png") || name.endsWith(".jpg") || name.endsWith(".jpeg"))) {
          const pathSeparator = inputFolder.includes("\\") ? "\\" : "/";
          const fullPath = `${inputFolder}${pathSeparator}${entry.name}`;

          let thumbnail: string | undefined;
          try {
            const fileData = await readFile(fullPath);
            const base64 = btoa(new Uint8Array(fileData).reduce((data, byte) => data + String.fromCharCode(byte), ""));
            const mimeType = name.endsWith(".png") ? "image/png" : "image/jpeg";
            thumbnail = `data:${mimeType};base64,${base64}`;
          } catch {
            // Thumbnail failed, continue
          }

          imageFiles.push({ name: entry.name, path: fullPath, selected: true, thumbnail });
        }
      }

      setImages(imageFiles.sort((a, b) => a.name.localeCompare(b.name)));
    } catch (err) {
      console.error("Failed to load images:", err);
      setImages([]);
    }
  }

  function hexToRgba(hex: string): [number, number, number, number] {
    const r = parseInt(hex.slice(1, 3), 16);
    const g = parseInt(hex.slice(3, 5), 16);
    const b = parseInt(hex.slice(5, 7), 16);
    return [r, g, b, 255];
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

    const [r, g, b, a] = hexToRgba(outlineColor);

    try {
      for (let i = 0; i < selectedImages.length; i++) {
        const img = selectedImages[i];
        setProgress(`Processing ${i + 1}/${selectedImages.length}: ${img.name}`);

        const pathSeparator = outputFolder.includes("\\") ? "\\" : "/";
        const outputFilePath = `${outputFolder}${pathSeparator}${img.name}`;

        await invoke("process_image_command", {
          inputPath: img.path,
          outputPath: outputFilePath,
          settings: {
            alpha_low_cutoff: 200,
            alpha_high_min: 200,
            alpha_high_max: 255,
            enable_color_simplify: enableColorSimplify,
            lab_merge_threshold: labMergeThreshold,
            enable_outline: enableOutline,
            outline_color: [r, g, b, a],
            edge_transparent_cutoff: 0,
            outline_connectivity: "four",
            outline_thickness: outlineThickness,
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

  function toggleImage(index: number) {
    setImages((imgs) => imgs.map((img, i) => (i === index ? { ...img, selected: !img.selected } : img)));
  }

  function selectAll() {
    setImages((imgs) => imgs.map((img) => ({ ...img, selected: true })));
  }

  function deselectAll() {
    setImages((imgs) => imgs.map((img) => ({ ...img, selected: false })));
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
              : `🎨 Process ${selectedCount} Image${selectedCount !== 1 ? "s" : ""}`}
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

        <h3>Color Simplification</h3>
        <div className="setting-group">
          <label style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
            <input
              type="checkbox"
              checked={enableColorSimplify}
              onChange={(e) => setEnableColorSimplify(e.target.checked)}
            />
            Enable Color Merging
          </label>
          <small>Merge similar colors to create cleaner pixel art palette</small>
        </div>

        {enableColorSimplify && (
          <div className="setting-group">
            <label>Merge Intensity: {labMergeThreshold.toFixed(1)}</label>
            <input
              type="range"
              min="1"
              max="15"
              step="0.5"
              value={labMergeThreshold}
              onChange={(e) => {
                const val = parseFloat(e.target.value);
                setLabMergeThreshold(val);
                saveProjectSetting("process_lab_threshold", val.toString());
              }}
              style={{ width: "100%" }}
            />
            <small>Lower = more aggressive merging (fewer colors)</small>
          </div>
        )}

        <hr />

        <h3>Outline</h3>
        <div className="setting-group">
          <label style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
            <input
              type="checkbox"
              checked={enableOutline}
              onChange={(e) => setEnableOutline(e.target.checked)}
            />
            Add Outline
          </label>
          <small>Add a 1px outline around sprites</small>
        </div>

        {enableOutline && (
          <>
            <div className="setting-group">
              <label>Outline Color</label>
              <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                <input
                  type="color"
                  value={outlineColor}
                  onChange={(e) => {
                    setOutlineColor(e.target.value);
                    saveProjectSetting("process_outline_color", e.target.value);
                  }}
                  style={{ width: "50px", height: "30px", border: "none", cursor: "pointer" }}
                />
                <span style={{ fontFamily: "monospace", fontSize: "0.85rem" }}>{outlineColor}</span>
              </div>
            </div>

            <div className="setting-group">
              <label>Thickness: {outlineThickness}px</label>
              <input
                type="range"
                min="1"
                max="5"
                step="1"
                value={outlineThickness}
                onChange={(e) => {
                  const val = parseInt(e.target.value);
                  setOutlineThickness(val);
                  saveProjectSetting("process_outline_thickness", val.toString());
                }}
                style={{ width: "100%" }}
              />
            </div>
          </>
        )}

        <hr />

        <div className="setting-group">
          <h4 style={{ margin: "0 0 0.5rem 0", fontSize: "0.95rem", color: "#666" }}>What this does</h4>
          <small style={{ lineHeight: "1.6" }}>
            <strong>Color Merging:</strong> Uses perceptual LAB color space to identify and merge similar shades,
            creating a cleaner, more hand-crafted look.<br /><br />
            <strong>Outline:</strong> Detects sprite edges and applies a consistent outline color,
            growing inward from the border.
          </small>
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
