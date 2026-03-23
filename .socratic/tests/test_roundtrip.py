"""
Test suite for SocraticTable — critique toolkit with session memory.

Covers:
  - Session summarization (heuristic extraction)
  - Brief generation (context for Task agents)
  - Convergence detection (novelty tracking)
  - Agent weight computation
  - Pragmatic critique template
"""

import sys
import json
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from core.session_memory import (
    summarize_session, save_summary, load_summaries, load_brief,
    generate_project_state, _extract_summary_from_text,
)
from core.converse import (
    create_conversation, add_turn, measure_novelty, novelty_summary,
)
from core.roundtable import (
    PRAGMATIC_CRITIQUE_TEMPLATE, build_pragmatic_critique_prompt,
    compute_weight, STANDARD_AGENTS, AgentResponse,
)


# ---------------------------------------------------------------------------
# Session Memory — Summarization
# ---------------------------------------------------------------------------

class TestSummarization:

    def test_extracts_numbered_items(self):
        text = "# Session\n1. Built the content stream tokenizer\n2. Implemented font encoding codec\n3. Added reflow engine for word wrapping"
        summary = _extract_summary_from_text(text)
        assert len(summary["decisions"]) == 3

    def test_extracts_bullet_items(self):
        text = "# Fixes\n- Resolved blob buffer overflow issue\n- Addressed memory leak in PDF.js proxy"
        summary = _extract_summary_from_text(text)
        assert len(summary["decisions"]) + len(summary["issues"]) >= 2

    def test_classifies_issues(self):
        text = "# Session\n- Fixed crash on save\n- Bug: font encoding wrong\n- Error in parser"
        summary = _extract_summary_from_text(text)
        assert len(summary["issues"]) >= 2

    def test_extracts_file_paths(self):
        text = "Modified src/engine/tokenizer.ts and core/session_memory.py"
        summary = _extract_summary_from_text(text)
        assert "src/engine/tokenizer.ts" in summary["files_touched"]
        assert "core/session_memory.py" in summary["files_touched"]

    def test_extracts_title(self):
        text = "# PDF Editor Session 05\nSome content here"
        summary = _extract_summary_from_text(text)
        assert "PDF Editor Session 05" in summary["one_line"]

    def test_handles_escaped_newlines(self):
        text = "# Title\\n1. Built the content tokenizer\\n2. Added font codec module\\n3. Implemented reflow engine"
        summary = _extract_summary_from_text(text)
        assert len(summary["decisions"]) >= 2

    def test_handles_empty_input(self):
        summary = _extract_summary_from_text("")
        assert summary["decisions"] == []
        assert summary["method"] == "heuristic"

    def test_truncates_long_title(self):
        text = "# " + "A" * 200 + "\nContent"
        summary = _extract_summary_from_text(text)
        assert len(summary["one_line"]) <= 120

    def test_extracts_open_items(self):
        text = "# Session\n## Decisions\n- Built X\n## Open\n- Test suite still needed\n- Annotation selection not done"
        summary = _extract_summary_from_text(text)
        assert len(summary["open"]) >= 2
        assert any("test suite" in o.lower() for o in summary["open"])

    def test_extracts_next_markers(self):
        text = "# Session\n- Built X\n- Next: implement undo system\n- TODO: add keyboard shortcuts"
        summary = _extract_summary_from_text(text)
        assert len(summary["open"]) >= 1


# ---------------------------------------------------------------------------
# Session Memory — Brief Generation
# ---------------------------------------------------------------------------

class TestBrief:

    def test_empty_when_no_summaries(self, tmp_path):
        # Temporarily point summaries dir to empty temp
        import core.session_memory as sm
        original = sm.SUMMARIES_DIR
        sm.SUMMARIES_DIR = tmp_path / "summaries"
        sm.SUMMARIES_DIR.mkdir()

        brief = load_brief()
        assert brief == ""

        sm.SUMMARIES_DIR = original

    def test_brief_contains_session_info(self, tmp_path):
        import core.session_memory as sm
        original = sm.SUMMARIES_DIR
        sm.SUMMARIES_DIR = tmp_path / "summaries"
        sm.SUMMARIES_DIR.mkdir()

        save_summary({
            "decisions": ["Built tokenizer", "Added reflow"],
            "issues": ["Font crash"],
            "files_touched": ["tokenizer.ts"],
            "one_line": "Session 01: Engine built",
            "open": [],
            "patterns": [],
        }, "test_session")

        brief = load_brief()
        assert "Session 01: Engine built" in brief
        assert "Built tokenizer" in brief

        sm.SUMMARIES_DIR = original


# ---------------------------------------------------------------------------
# Convergence Detection
# ---------------------------------------------------------------------------

class TestConvergence:

    def test_diverse_turns_high_novelty(self):
        conv = create_conversation("test", domain="architecture")
        add_turn(conv, "architect", "Redis offers sorted sets and streams.", confidence=0.8)
        add_turn(conv, "engineer", "Memcached uses slab allocator efficiently.", confidence=0.7)
        add_turn(conv, "skeptic", "Single-threaded bottleneck is the real risk.", confidence=0.7)

        data = measure_novelty(conv)
        assert data["recent_trend"] > 0.5
        assert data["recommendation"] == "continue"

    def test_repetitive_turns_low_novelty(self):
        conv = create_conversation("test", domain="architecture")
        add_turn(conv, "architect", "Redis is the best choice for caching.", confidence=0.8)
        add_turn(conv, "engineer", "Redis is the best choice for caching.", confidence=0.7)
        add_turn(conv, "skeptic", "Redis is the best choice for caching.", confidence=0.6)

        data = measure_novelty(conv)
        assert data["recent_trend"] < 0.2
        assert data["recommendation"] == "stop"

    def test_single_turn_no_crash(self):
        conv = create_conversation("test", domain="architecture")
        add_turn(conv, "architect", "One turn only.", confidence=0.8)
        data = measure_novelty(conv)
        assert data["recent_trend"] == 1.0

    def test_novelty_summary_string(self):
        conv = create_conversation("test", domain="architecture")
        add_turn(conv, "architect", "Point A.", confidence=0.8)
        add_turn(conv, "engineer", "Point A repeated.", confidence=0.7)
        result = novelty_summary(conv)
        assert isinstance(result, str)
        assert len(result) > 0


# ---------------------------------------------------------------------------
# Agent System
# ---------------------------------------------------------------------------

class TestAgents:

    def test_weight_computation(self):
        agent = STANDARD_AGENTS["architect"]
        weight = compute_weight(agent, "architecture", 0.8)
        assert weight > 0
        assert weight <= 1.0

    def test_pragmatic_critique_template_exists(self):
        assert "reframe" in PRAGMATIC_CRITIQUE_TEMPLATE.lower()
        assert "ambition" in PRAGMATIC_CRITIQUE_TEMPLATE.lower()

    def test_build_critique_prompt(self):
        prompt = build_pragmatic_critique_prompt("test output")
        assert "test output" in prompt
        assert "reframe" in prompt.lower()

    def test_agent_response_from_raw_json(self):
        raw = json.dumps({
            "claims": [{"claim": "Test claim", "evidence": "proof", "confidence": 0.8}],
            "recommendation": "Do X",
            "dissents": [],
            "agreements": [],
            "questions": [],
        })
        resp = AgentResponse.from_raw("test_agent", raw, 0.5)
        assert resp.agent_name == "test_agent"
        assert len(resp.key_claims) == 1

    def test_agent_response_fallback(self):
        resp = AgentResponse.from_raw("test", "just plain text", 0.5)
        assert resp.summary == "just plain text"[:500]
        assert resp.confidence == 0.5


# ---------------------------------------------------------------------------
# Project State Generation
# ---------------------------------------------------------------------------

class TestProjectState:

    def test_generates_from_summaries(self, tmp_path):
        import core.session_memory as sm
        original = sm.SUMMARIES_DIR
        sm.SUMMARIES_DIR = tmp_path / "summaries"
        sm.SUMMARIES_DIR.mkdir()

        save_summary({
            "decisions": ["Use BM25", "Cut SMOS"],
            "issues": ["Parser crash"],
            "files_touched": ["scoring.py"],
            "one_line": "Memory rebuild",
            "open": ["Test on real project"],
            "patterns": [],
        }, "state_test")

        state = generate_project_state()
        assert "Use BM25" in state
        assert "Parser crash" in state
        assert "scoring.py" in state

        sm.SUMMARIES_DIR = original
