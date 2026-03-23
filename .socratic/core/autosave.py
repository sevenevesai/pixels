"""
Session Auto-Save — Save transcripts and extract summaries.

Usage:
    from core.autosave import auto_save_raw, next_session_path
    result = auto_save_raw(content, "topic_name")
    # -> {"path": "sessions/01_topic_name.md", "summary": {...}}
"""

from pathlib import Path
from typing import Dict

SESSIONS_DIR = Path("sessions")


def next_session_number() -> int:
    """Find the next available session number."""
    SESSIONS_DIR.mkdir(exist_ok=True)
    existing = sorted(SESSIONS_DIR.glob("*.md"))
    max_num = -1
    for f in existing:
        try:
            num = int(f.stem.split("_")[0])
            max_num = max(max_num, num)
        except (ValueError, IndexError):
            pass
    return max_num + 1


def next_session_path(name: str) -> str:
    """Get the next session file path with auto-incrementing number."""
    num = next_session_number()
    filename = f"{num:02d}_{name}.md"
    return str(SESSIONS_DIR / filename)


def auto_save_raw(content: str, name: str) -> Dict:
    """Save raw markdown content and extract summary.

    Args:
        content: markdown text of the session
        name: descriptive name

    Returns:
        dict with path and summary
    """
    from core.session_memory import summarize_session, save_summary

    path = next_session_path(name)
    Path(path).write_text(content, encoding="utf-8")

    summary = summarize_session(content, use_llm=False)
    save_summary(summary, Path(path).stem)

    return {
        "path": path,
        "summary": summary,
    }
