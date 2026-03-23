#!/usr/bin/env python
"""
SocraticTable — Autonomous discovery engine with session memory.

Usage:
    python st.py go --project <dir>       # Start autonomous discovery session
    python st.py brief                    # Session context for Task agents
    python st.py save --file <md>         # Save session + extract summary
    python st.py ingest <file.md>         # Extract summary from existing file
    python st.py project-state            # Generate project state for CLAUDE.md
    python st.py history                  # Agent accuracy scores
    python st.py score <agent> <0-1>      # Update agent score
    python st.py init <dir>               # Initialize in another project

Skills (invoke via /discover or /critique in Claude Code):
    /discover                             # Autonomous explore -> build -> validate loop
    /critique                             # Pragmatic self-critique on current session
"""

import argparse
import json
import os
import sys
import shutil
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))
os.chdir(PROJECT_ROOT)

os.environ.setdefault("PYTHONIOENCODING", "utf-8")

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_brief(args):
    """Show session brief for Task agent context injection."""
    from core.session_memory import load_brief
    brief = load_brief(max_sessions=args.sessions)
    if brief:
        print(brief)
    else:
        print("No session summaries yet. Save a session first:")
        print("  python st.py save --file <session.md>")


def cmd_ingest(args):
    """Extract summary from a session transcript."""
    from core.session_memory import summarize_session, save_summary

    text = Path(args.file).read_text(encoding="utf-8")
    session_name = Path(args.file).stem
    summary = summarize_session(text, use_llm=False)
    save_summary(summary, session_name)

    d = len(summary.get("decisions", []))
    i = len(summary.get("issues", []))
    f = len(summary.get("files_touched", []))
    print(f"Ingested {args.file}:")
    print(f"  {d} decisions, {i} issues, {f} files")
    print(f"  -> state/memory/summaries/{session_name}.json")


def cmd_ingest_all(args):
    """Ingest all session transcripts."""
    from core.session_memory import summarize_session, save_summary

    session_dir = PROJECT_ROOT / "sessions"
    if not session_dir.exists():
        print("No sessions/ directory found.")
        return

    total_d, total_i = 0, 0
    for md_file in sorted(session_dir.glob("*.md")):
        text = md_file.read_text(encoding="utf-8")
        summary = summarize_session(text, use_llm=False)
        save_summary(summary, md_file.stem)
        d = len(summary.get("decisions", []))
        i = len(summary.get("issues", []))
        total_d += d
        total_i += i
        print(f"  {md_file.name}: {d} decisions, {i} issues")

    print(f"\nTotal: {total_d} decisions, {total_i} issues")


def cmd_project_state(args):
    """Generate project state block for CLAUDE.md."""
    from core.session_memory import generate_project_state
    state = generate_project_state()
    if not state:
        print("No session summaries yet.")
        return

    print(state)
    if args.update:
        import re
        target = Path(args.update)
        if target.exists():
            content = target.read_text(encoding="utf-8")
            if "## Project State" in content:
                content = re.sub(
                    r'## Project State.*?(?=\n## |\Z)',
                    state + "\n\n",
                    content,
                    flags=re.DOTALL,
                )
            else:
                content += "\n\n" + state
            target.write_text(content, encoding="utf-8")
            print(f"\nUpdated {target}")


def cmd_save(args):
    """Save session content and extract summary."""
    from core.autosave import auto_save_raw
    if args.file:
        content = Path(args.file).read_text(encoding="utf-8")
        name = args.name or Path(args.file).stem
    elif args.content:
        content = args.content
        name = args.name or "session"
    else:
        print("Provide --file or --content")
        return

    result = auto_save_raw(content, name)
    path = result["path"]
    summary = result.get("summary", {})
    d = len(summary.get("decisions", []))
    i = len(summary.get("issues", []))
    print(f"Saved: {path}")
    print(f"  {d} decisions, {i} issues extracted")


def cmd_history(args):
    """Show agent accuracy history."""
    hist_file = PROJECT_ROOT / "state" / "agent_history.json"
    if not hist_file.exists():
        print("No agent history yet.")
        return
    data = json.loads(hist_file.read_text(encoding="utf-8"))
    accuracy = data.get("accuracy", {})
    if accuracy:
        print("\nAgent Historical Accuracy:")
        for name, score in sorted(accuracy.items(), key=lambda x: x[1], reverse=True):
            bar = "#" * int(score * 20)
            print(f"  {name:12s} {score:.3f} {bar}")
    else:
        print("No scores recorded yet.")


def cmd_score(args):
    """Update an agent's accuracy score."""
    from core.roundtable import update_agent_accuracy
    new_score = update_agent_accuracy(args.agent, args.value)
    print(f"Updated {args.agent}: {new_score:.4f}")


def cmd_dissent(args):
    """Analyze dissent from the last roundtable session."""
    session_path = args.session or "state/session.json"
    p = Path(session_path)
    if not p.exists():
        print(f"No session found at {session_path}")
        return

    data = json.loads(p.read_text(encoding="utf-8"))
    from core.roundtable import AgentResponse
    from core.dissent import analyze_dissent, format_dissent_report

    all_responses = []
    for rnd in data.get("rounds", []):
        for resp_data in rnd.get("responses", []):
            resp = AgentResponse(
                agent_name=resp_data["agent_name"],
                raw_content=resp_data.get("raw_content", ""),
                summary=resp_data.get("summary", ""),
                key_claims=resp_data.get("key_claims", []),
                recommendation=resp_data.get("recommendation", ""),
                confidence=resp_data.get("confidence", 0.5),
                weight=resp_data.get("weight", 0.5),
                agreements=resp_data.get("agreements", []),
                dissents=resp_data.get("dissents", []),
                questions=resp_data.get("questions", []),
            )
            all_responses.append(resp)

    if not all_responses:
        print("No agent responses found in session.")
        return

    report = analyze_dissent(all_responses)
    print(format_dissent_report(report))


def _detect_project_character(target: Path) -> dict:
    """Heuristic detection of project type and lifecycle stage.

    Scans for structural signals (file types, directories, configs)
    to guess whether this is research, product, tool, or exploration,
    and whether it's early, mid, late, or mature.
    """
    import glob as _glob

    signals = []

    # --- Type detection signals ---
    # Look for paper/research signals — only in top 2 levels (not deep rglob)
    # to avoid false positives from node_modules, session transcripts, etc.
    top_files = list(target.glob("*.tex")) + list(target.glob("*/*.tex")) + list(target.glob("paper/*"))
    has_paper = bool(top_files)
    has_data = (target / "data").is_dir()
    has_experiments = bool([f for f in list(target.glob("*.py")) + list(target.glob("src/*.py"))
                           if "experiment" in f.name.lower() or "validate" in f.name.lower()])
    has_webapp = (target / "src" / "App.tsx").exists() or (target / "src" / "App.jsx").exists()
    has_package = (target / "package.json").exists()
    has_setup = (target / "setup.py").exists() or (target / "pyproject.toml").exists()
    has_components = (target / "src" / "components").is_dir()
    has_ui = has_webapp or has_components
    has_notebook = bool(list(target.rglob("*.ipynb")))

    # Determine type
    if has_paper or (has_experiments and has_data and not has_ui):
        proj_type = "research"
        if has_paper:
            signals.append("has paper/tex files")
        if has_data:
            signals.append("has data directory")
        if has_experiments:
            signals.append("has experiment/validation scripts")
    elif has_ui or (has_package and has_components):
        proj_type = "product"
        if has_webapp:
            signals.append("has React/web app")
        if has_components:
            signals.append("has components directory")
    elif has_setup or (has_package and not has_ui):
        proj_type = "tool"
        signals.append("has package config without UI")
    else:
        proj_type = "exploration"
        signals.append("no strong structural signals")
        if has_notebook:
            signals.append("has notebooks")

    # --- Stage detection signals ---
    # Count source files as proxy for maturity
    py_files = list(target.rglob("*.py"))
    ts_files = list(target.rglob("*.ts")) + list(target.rglob("*.tsx"))
    src_files = [f for f in (py_files + ts_files)
                 if "node_modules" not in str(f) and ".git" not in str(f)]
    file_count = len(src_files)

    has_tests = bool([f for f in src_files
                      if "test" in f.name.lower() or "spec" in f.name.lower()])
    has_ci = (target / ".github" / "workflows").is_dir()
    has_dist = (target / "dist").is_dir() or (target / "build").is_dir()
    has_sessions = (target / "sessions").is_dir() or (target / ".socratic").is_dir()

    # Check git commit count as maturity signal
    git_dir = target / ".git"
    commit_count = 0
    if git_dir.exists():
        try:
            import subprocess
            result = subprocess.run(
                ["git", "rev-list", "--count", "HEAD"],
                capture_output=True, text=True, cwd=str(target), timeout=5
            )
            if result.returncode == 0:
                commit_count = int(result.stdout.strip())
        except Exception:
            pass

    if commit_count > 0:
        signals.append(f"{commit_count} commits")

    # Determine stage
    if file_count < 5 and commit_count < 10:
        stage = "early"
        signals.append(f"{file_count} source files")
    elif not has_tests and not has_dist and file_count < 20:
        stage = "mid"
        signals.append("no tests yet")
    elif has_tests and (has_dist or has_paper):
        stage = "late"
        if has_tests:
            signals.append("has tests")
        if has_dist:
            signals.append("has build output")
    else:
        stage = "mid"
        signals.append(f"{file_count} source files")

    # Override for research: if paper exists and data exists, likely late
    if proj_type == "research" and has_paper and has_data:
        if file_count >= 3:
            stage = "mid-to-late"
            signals.append("paper + data + code all present")

    # --- Focus suggestion ---
    focus_map = {
        ("research", "early"): "Prove the core idea works. Run initial experiments, gather evidence.",
        ("research", "mid"): "Deepen analysis, fill evidence gaps, explore novel directions.",
        ("research", "mid-to-late"): "Strengthen claims, address open questions, expand scope if warranted.",
        ("research", "late"): "Validate rigorously, ensure reproducibility, prepare for publication.",
        ("product", "early"): "Get core features working. Prove the concept.",
        ("product", "mid"): "Fill feature gaps, fix UX friction, make it robust.",
        ("product", "late"): "Polish, edge cases, performance, deployment readiness.",
        ("tool", "early"): "Define the API, build core functionality.",
        ("tool", "mid"): "Edge cases, documentation, error handling.",
        ("tool", "late"): "Integration tests, examples, publishing.",
        ("exploration", "early"): "Push the most promising direction. Don't converge too early.",
        ("exploration", "mid"): "Test assumptions, build minimal proofs.",
    }
    focus = focus_map.get((proj_type, stage),
                          "Assess the project's needs based on what you find during orientation.")

    return {
        "type": proj_type,
        "stage": stage,
        "signals": signals,
        "focus": focus,
    }


def cmd_go(args):
    """Generate discovery kickoff context for an autonomous session.

    Loads memory, examines target project, and outputs a complete
    context block that Claude Code uses with the /discover skill.
    """
    from core.session_memory import load_brief, load_summaries

    target = Path(args.project).resolve() if args.project else None

    # --- Memory context ---
    brief = load_brief(max_sessions=10, max_chars=3000)
    summaries = load_summaries(max_sessions=10)

    # --- Compute what's unresolved ---
    all_open = []
    all_issues = []
    for s in summaries:
        all_open.extend(s.get("open", []))
        all_issues.extend(s.get("issues", []))

    # --- Target project info + character detection ---
    project_info = ""
    project_character = None
    if target and target.exists():
        project_info = f"\n## Target Project: {target}\n"

        # Check for CLAUDE.md, README, package.json, STATUS.md
        docs_found = []
        for doc in ["CLAUDE.md", "STATUS.md", "README.md"]:
            doc_path = target / doc
            if doc_path.exists():
                content = doc_path.read_text(encoding="utf-8")[:2000]
                project_info += f"\n### {doc} (first 2000 chars)\n{content}\n"
                docs_found.append(doc)
                break

        pkg = target / "package.json"
        if pkg.exists():
            import json as _json
            pkg_data = _json.loads(pkg.read_text(encoding="utf-8"))
            project_info += f"\n### package.json\n"
            project_info += f"- name: {pkg_data.get('name', '?')}\n"
            project_info += f"- scripts: {', '.join(pkg_data.get('scripts', {}).keys())}\n"
            deps = list(pkg_data.get("dependencies", {}).keys())[:10]
            project_info += f"- deps: {', '.join(deps)}\n"

        # --- Detect project character ---
        project_character = _detect_project_character(target)

    # --- Output ---
    print("# Autonomous Discovery Session\n")
    print(f"**Started:** {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    if target:
        print(f"**Target:** {target}")
    print()

    if project_character:
        print(f"## Detected Project Character")
        print(f"- **Type:** {project_character['type']}")
        print(f"- **Stage:** {project_character['stage']}")
        print(f"- **Signals:** {', '.join(project_character['signals'])}")
        print(f"- **Suggested focus:** {project_character['focus']}")
        print()
        print("NOTE: This is a heuristic assessment. The /discover orient phase should verify and override if wrong.")
        print()

    if brief:
        print(brief)
        print()

    if all_open:
        print("## Unresolved from Prior Sessions")
        seen = set()
        for item in all_open:
            key = item[:40].lower()
            if key not in seen:
                seen.add(key)
                print(f"- {item}")
        print()

    if all_issues:
        print("## Known Issues from Prior Sessions")
        seen = set()
        for item in all_issues[:8]:
            key = item[:40].lower()
            if key not in seen:
                seen.add(key)
                print(f"- {item}")
        print()

    if project_info:
        print(project_info)

    print("## Instructions")
    print("Run /discover to start the autonomous discovery loop.")
    print("The agent will orient, discover, implement, validate, and record findings.")


def cmd_init(args):
    """Initialize .socratic/ in another project directory."""
    target = Path(args.dir).resolve()
    rt_dir = target / ".socratic"

    if rt_dir.exists():
        print(f".socratic/ already exists at {rt_dir}")
        return

    rt_dir.mkdir(parents=True)
    (rt_dir / "sessions").mkdir()
    (rt_dir / "state").mkdir()
    (rt_dir / "state" / "memory").mkdir()
    (rt_dir / "state" / "memory" / "summaries").mkdir()

    # Copy core files (only what's needed)
    core_src = PROJECT_ROOT / "core"
    core_dst = rt_dir / "core"
    core_dst.mkdir()

    for f in ["roundtable.py", "converse.py", "autosave.py",
              "session_memory.py", "dissent.py", "__init__.py"]:
        src = core_src / f
        if src.exists():
            shutil.copy2(src, core_dst / f)

    # Copy entry point
    shutil.copy2(PROJECT_ROOT / "st.py", rt_dir / "st.py")

    # Copy test suite
    tests_dst = rt_dir / "tests"
    tests_dst.mkdir()
    test_src = PROJECT_ROOT / "tests" / "test_roundtrip.py"
    if test_src.exists():
        shutil.copy2(test_src, tests_dst / "test_roundtrip.py")

    # Pre-seed agent history
    (rt_dir / "state" / "agent_history.json").write_text(json.dumps({
        "accuracy": {
            "pragmatist": 0.938, "architect": 0.879, "skeptic": 0.861,
            "researcher": 0.848, "engineer": 0.828,
        },
        "updated": datetime.now().isoformat(),
    }, indent=2), encoding="utf-8")

    # Deploy .mcp.json for Playwright browser control
    mcp_src = PROJECT_ROOT / ".mcp.json"
    mcp_dst = target / ".mcp.json"
    if mcp_src.exists() and not mcp_dst.exists():
        shutil.copy2(mcp_src, mcp_dst)

    # Deploy skills (each skill is a directory with SKILL.md inside)
    skills_src = PROJECT_ROOT / ".claude" / "skills"
    if skills_src.exists():
        skills_dst = target / ".claude" / "skills"
        for skill_dir in skills_src.iterdir():
            if skill_dir.is_dir() and (skill_dir / "SKILL.md").exists():
                dst_dir = skills_dst / skill_dir.name
                dst_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy2(skill_dir / "SKILL.md", dst_dir / "SKILL.md")

    # Write instructions
    (rt_dir / "INSTRUCTIONS.md").write_text(_get_instructions(), encoding="utf-8")

    # Gitignore
    gitignore = target / ".gitignore"
    if gitignore.exists():
        content = gitignore.read_text(encoding="utf-8")
        if ".socratic/state" not in content:
            with open(gitignore, "a", encoding="utf-8") as f:
                f.write("\n.socratic/state/\n")
    else:
        with open(gitignore, "w", encoding="utf-8") as f:
            f.write(".socratic/state/\n")

    print(f"Initialized .socratic/ at {rt_dir}")
    print(f"  Brief:   python .socratic/st.py brief")
    print(f"  Save:    python .socratic/st.py save --file <session.md>")
    print(f"  State:   python .socratic/st.py project-state")
    print(f"  Tests:   python -m pytest .socratic/tests/ -v")


def _get_instructions() -> str:
    return """\
# SocraticTable

Pragmatic critique toolkit with session memory. Challenges assumptions, catches bugs, carries context across sessions.

## 60-Second Start

```bash
# Get project context for Task agents (from prior sessions)
python .socratic/st.py brief

# Save a session (auto-extracts decisions, issues, files)
python .socratic/st.py save --file session.md

# Generate project state for CLAUDE.md
python .socratic/st.py project-state --update CLAUDE.md
```

## Pragmatic Self-Critique (the proven mode — +25% quality)

Two Task agent calls:

**Call 1:** Answer/build the thing (any agent, sonnet)

**Call 2:** Critique with this prompt:
```
You are a pragmatist-critic hybrid reviewing this output. Two jobs:

Job 1 (Pragmatist): Is this solving the RIGHT problem? What assumption is wrong?
What would you CUT? Is there a reframe that changes the approach?

Job 2 (Critic): What's factually wrong or missing? What's the single most
important improvement?

The pragmatist reframe is the MOST VALUABLE part.

## Output Being Reviewed
[paste output from call 1]
```

**Call 3 (optional):** Save the session:
```bash
python .socratic/st.py save --content "# Topic\\n..." --name "topic"
```

## Before Spawning Task Agents

Prepend project context so agents don't start from zero:
```bash
python .socratic/st.py brief
```
Copy the output into your Task agent's prompt. This replaces "scan entire repo."

## CLI Reference

```bash
python .socratic/st.py brief                         # Context for Task agents
python .socratic/st.py brief --sessions 10            # More history
python .socratic/st.py save --file <md>               # Save + summarize
python .socratic/st.py ingest <file.md>               # Summarize existing file
python .socratic/st.py ingest-all                     # Summarize all sessions/
python .socratic/st.py project-state                  # Project state block
python .socratic/st.py project-state --update X.md    # Auto-update CLAUDE.md
python .socratic/st.py history                        # Agent accuracy scores
python .socratic/st.py score <agent> <0-1>            # Score after session
python .socratic/st.py dissent --session <json>       # Analyze roundtable dissent
python .socratic/st.py init <dir>                     # Deploy to another project
```

## What's Inside

- **Pragmatic critique template**: Fused pragmatist + critic in one prompt. Reframes problems, not just fixes errors.
- **Session memory**: Heuristic summarizer extracts decisions/issues/files from any format. Brief generator concatenates recent summaries for Task agent injection.
- **5 agent profiles**: architect, engineer, skeptic, pragmatist, researcher — EMA-weighted by accuracy
- **Convergence detection**: Stops conversations when agents repeat themselves
- **Dissent detection**: Surfaces low-weight agents challenging high-weight claims
- **Zero dependencies**: Pure Python

## Proven Findings (13 sessions, 5 A/B tests)

- Pragmatist-fused critique: +25% quality over single-pass
- Critique catches 40-60% of errors, reframes ~20% of the time
- On real project (PDF editor): 16 bugs caught across 3 critique rounds
- Pragmatist (lowest domain weight) drives highest-impact contributions
"""


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="SocraticTable — Pragmatic critique toolkit with session memory",
    )
    subparsers = parser.add_subparsers(dest="command")

    # brief
    brief_p = subparsers.add_parser("brief", help="Session context for Task agents")
    brief_p.add_argument("--sessions", type=int, default=5, help="Recent sessions to include")

    # ingest
    ing_p = subparsers.add_parser("ingest", help="Extract summary from session file")
    ing_p.add_argument("file", help="Markdown file to process")

    # ingest-all
    subparsers.add_parser("ingest-all", help="Summarize all sessions/")

    # save
    save_p = subparsers.add_parser("save", help="Save session + extract summary")
    save_p.add_argument("--file", help="Markdown file to save")
    save_p.add_argument("--content", help="Raw content string")
    save_p.add_argument("--name", help="Session name")

    # project-state
    ps_p = subparsers.add_parser("project-state", help="Generate project state for CLAUDE.md")
    ps_p.add_argument("--update", help="CLAUDE.md path to update in-place")

    # history
    subparsers.add_parser("history", help="Agent accuracy scores")

    # score
    sc_p = subparsers.add_parser("score", help="Update agent accuracy")
    sc_p.add_argument("agent", help="Agent name")
    sc_p.add_argument("value", type=float, help="Score 0.0-1.0")

    # dissent
    dis_p = subparsers.add_parser("dissent", help="Analyze roundtable dissent")
    dis_p.add_argument("--session", help="Path to session JSON")

    # go
    go_p = subparsers.add_parser("go", help="Start autonomous discovery session")
    go_p.add_argument("--project", help="Target project directory")

    # init
    init_p = subparsers.add_parser("init", help="Deploy to another project")
    init_p.add_argument("dir", help="Target directory")

    args = parser.parse_args()

    commands = {
        "brief": cmd_brief,
        "ingest": cmd_ingest,
        "ingest-all": cmd_ingest_all,
        "save": cmd_save,
        "project-state": cmd_project_state,
        "history": cmd_history,
        "score": cmd_score,
        "dissent": cmd_dissent,
        "go": cmd_go,
        "init": cmd_init,
    }

    handler = commands.get(args.command)
    if handler:
        handler(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
