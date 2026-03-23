"""
Session Memory — LLM-based session summarization + brief generation.

Replaces the section parser / BM25 / keyword graph memory system with
a simpler, domain-agnostic approach:

1. After each session: one LLM call compresses transcript → structured summary
2. At session start: concatenate recent summaries → inject into Task agent prompts
3. Optionally: update CLAUDE.md with current project state

Why this replaces the old system:
- Section parser required ## Decisions headers (93% failure on real projects)
- Keyword graph was domain-locked (25 clusters, all self-referential)
- BM25 retrieval was useless on sparse corpus (10 units from 9 sessions)
- LLM summarization handles ANY format and ANY domain

Cost: ~$0.01 per session (one Haiku call for summarization)

Usage:
    from core.session_memory import summarize_session, load_brief, update_project_state

    # After a session:
    summary = summarize_session(transcript_text)
    save_summary(summary, "session_name")

    # Before spawning Task agents:
    brief = load_brief(max_sessions=5)
    task_prompt = f"{brief}\n\n{your_critique_prompt}"

    # After session, update CLAUDE.md:
    update_project_state(project_claude_md_path)
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

MEMORY_DIR = Path("state/memory")
SUMMARIES_DIR = MEMORY_DIR / "summaries"

# ---------------------------------------------------------------------------
# Summary extraction prompt — domain-agnostic, handles any format
# ---------------------------------------------------------------------------

SUMMARIZE_PROMPT = """\
Extract the key information from this coding session transcript.

Be specific: include file paths, function names, exact error messages,
specific numbers. Target 200 words total.

## Format
Respond with ONLY valid JSON:
```json
{
  "decisions": ["what was decided/built/changed — 3-5 specific items"],
  "patterns": ["code structures, file locations, architectural insights"],
  "issues": ["bugs found, problems encountered, error patterns"],
  "open": ["unresolved questions, next steps"],
  "files_touched": ["src/foo.ts", "core/bar.py"],
  "one_line": "Single sentence: what this session accomplished"
}
```

## Session Transcript
{transcript}
"""


def _extract_summary_from_text(transcript: str) -> Dict:
    """Fallback: extract summary without LLM using simple heuristics.

    Used when no LLM API is available. Gets ~40% of the value of
    LLM summarization, but works offline with zero cost.
    """
    import re

    # Normalize escaped newlines (some session files use literal \n)
    normalized = transcript.replace("\\n", "\n")
    lines = normalized.strip().split("\n")
    decisions = []
    issues = []
    files = set()

    open_items = []
    in_open_section = False

    for line in lines:
        stripped = line.strip()

        # Detect "Open" / "Next" / "TODO" sections
        if re.match(r'^#{1,3}\s*(open|next|todo|remaining|unresolved)', stripped, re.IGNORECASE):
            in_open_section = True
            continue
        elif re.match(r'^#{1,3}\s', stripped):
            in_open_section = False

        # Extract file paths
        for match in re.finditer(r'[\w/\\.-]+\.\w{1,4}', stripped):
            path = match.group()
            if any(ext in path for ext in ['.ts', '.py', '.js', '.tsx', '.jsx',
                                            '.md', '.json', '.html', '.css']):
                files.add(path)

        # Lines that look like decisions/actions (numbered or bulleted)
        if re.match(r'^\d+\.\s+', stripped) or re.match(r'^[-*]\s+', stripped):
            text = re.sub(r'^\d+\.\s+|^[-*]\s+', '', stripped).strip()
            text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)  # strip bold
            if len(text) > 10 and len(text) < 300:
                if in_open_section:
                    open_items.append(text)
                elif any(w in text.lower() for w in ['fix', 'bug', 'error', 'broken',
                                                     'crash', 'fail', 'wrong']):
                    issues.append(text)
                else:
                    decisions.append(text)

        # Also catch inline "next:" or "TODO:" markers outside sections
        if not in_open_section and re.match(r'^[-*]\s+(next|todo|still need|remaining):', stripped, re.IGNORECASE):
            text = re.sub(r'^[-*]\s+', '', stripped).strip()
            if len(text) > 10 and len(text) < 300:
                open_items.append(text)

    # Title as one-liner (first heading only, truncate)
    title = ""
    for line in lines[:10]:
        line = line.strip()
        if line.startswith("#") and len(line) > 3:
            title = line.lstrip("# ").strip()[:120]
            break

    return {
        "decisions": decisions[:8],
        "patterns": [],
        "issues": issues[:5],
        "open": open_items[:5],
        "files_touched": sorted(files)[:15],
        "one_line": title or "Session summary (auto-extracted)",
        "method": "heuristic",
    }


def summarize_session(transcript: str, use_llm: bool = True) -> Dict:
    """Summarize a session transcript into structured memory.

    Args:
        transcript: Full session text (any format)
        use_llm: If True, attempt LLM call. Falls back to heuristic if unavailable.

    Returns:
        Dict with decisions, patterns, issues, open, files_touched, one_line
    """
    # Truncate very long transcripts (keep first + last portions)
    if len(transcript) > 30000:
        transcript = transcript[:20000] + "\n\n...[truncated]...\n\n" + transcript[-8000:]

    if use_llm:
        try:
            return _llm_summarize(transcript)
        except Exception:
            pass  # Fall back to heuristic

    return _extract_summary_from_text(transcript)


def _llm_summarize(transcript: str) -> Dict:
    """Call LLM to summarize session. Override this with your API."""
    # This is a hook — the actual LLM call depends on the user's setup.
    # In Claude Code, this would be done via Task agent, not direct API call.
    # For now, raise to trigger heuristic fallback.
    raise NotImplementedError(
        "LLM summarization requires API access. "
        "Use the CLI: python st.py summarize <file> "
        "or pass the transcript through a Task agent with SUMMARIZE_PROMPT."
    )


def save_summary(summary: Dict, session_name: str) -> Path:
    """Save a session summary to disk."""
    SUMMARIES_DIR.mkdir(parents=True, exist_ok=True)

    summary["session_name"] = session_name
    summary["timestamp"] = datetime.now().isoformat()

    path = SUMMARIES_DIR / f"{session_name}.json"
    path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return path


def load_summaries(max_sessions: int = 10) -> List[Dict]:
    """Load the most recent session summaries, newest first."""
    if not SUMMARIES_DIR.exists():
        return []

    files = sorted(SUMMARIES_DIR.glob("*.json"), key=lambda f: f.stat().st_mtime,
                   reverse=True)

    summaries = []
    for f in files[:max_sessions]:
        try:
            summaries.append(json.loads(f.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            continue

    return summaries


def load_brief(max_sessions: int = 5, max_chars: int = 2000) -> str:
    """Generate a context brief from recent session summaries.

    This is what gets prepended to Task agent prompts so they
    have project context without scanning the codebase.
    """
    summaries = load_summaries(max_sessions)

    if not summaries:
        return ""

    lines = ["## Project Context (from prior sessions)\n"]
    chars = len(lines[0])

    for s in summaries:
        name = s.get("session_name", "?")
        one_line = s.get("one_line", "")

        section = f"### {name}\n{one_line}\n"

        # Decisions (most important)
        decisions = s.get("decisions", [])
        if decisions:
            section += "- " + "\n- ".join(decisions[:4]) + "\n"

        # Issues (second most important)
        issues = s.get("issues", [])
        if issues:
            section += "Issues: " + "; ".join(issues[:3]) + "\n"

        # Files (compact reference)
        files = s.get("files_touched", [])
        if files:
            section += f"Files: {', '.join(files[:8])}\n"

        # Open questions
        open_items = s.get("open", [])
        if open_items:
            section += f"Open: {'; '.join(open_items[:2])}\n"

        if chars + len(section) > max_chars:
            break

        lines.append(section)
        chars += len(section)

    return "\n".join(lines)


def generate_project_state(max_sessions: int = 10) -> str:
    """Generate a project state block for CLAUDE.md.

    This summarizes what's been built across all sessions into
    a block suitable for appending to a project's CLAUDE.md.
    """
    summaries = load_summaries(max_sessions)

    if not summaries:
        return ""

    all_decisions = []
    all_issues = []
    all_files = set()
    all_open = []

    for s in summaries:
        all_decisions.extend(s.get("decisions", []))
        all_issues.extend(s.get("issues", []))
        all_files.update(s.get("files_touched", []))
        all_open.extend(s.get("open", []))

    lines = [
        f"## Project State ({len(summaries)} sessions)\n",
        f"**Last session:** {summaries[0].get('one_line', 'N/A')}\n",
    ]

    if all_decisions:
        lines.append("**Key decisions:**")
        # Deduplicate by first 40 chars
        seen = set()
        for d in all_decisions:
            key = d[:40].lower()
            if key not in seen:
                seen.add(key)
                lines.append(f"- {d}")

    if all_issues:
        lines.append("\n**Known issues:**")
        seen = set()
        for i in all_issues[:5]:
            key = i[:40].lower()
            if key not in seen:
                seen.add(key)
                lines.append(f"- {i}")

    if all_open:
        lines.append("\n**Open questions:**")
        for o in all_open[:3]:
            lines.append(f"- {o}")

    if all_files:
        lines.append(f"\n**Files touched:** {', '.join(sorted(all_files)[:15])}")

    return "\n".join(lines)
