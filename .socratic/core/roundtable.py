"""
SocraticTable — Agent profiles, critique templates, and model escalation.

Used by the /discover and /critique skills via Claude Code, and by st.py
for agent scoring. The actual orchestration happens in Claude Code via
the Task tool — this file provides the data layer.
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional
from pathlib import Path

# ---------------------------------------------------------------------------
# Agent definitions
# ---------------------------------------------------------------------------

AGENT_HISTORY_PATH = Path("state/agent_history.json")


@dataclass
class Agent:
    name: str
    role: str
    expertise: Dict[str, float]
    system_prompt: str
    model: str  # "opus", "sonnet", "haiku"
    historical_accuracy: float = 1.0

    def relevance(self, domain: str) -> float:
        return self.expertise.get(domain, 0.0)


STANDARD_AGENTS: Dict[str, Agent] = {
    "architect": Agent(
        name="architect",
        role="System Architect",
        expertise={
            "architecture": 0.9, "implementation": 0.5,
            "ux": 0.3, "risk": 0.4, "research": 0.3,
        },
        system_prompt=(
            "You are a system architect. Focus on structure, modularity, "
            "data flow, and design tradeoffs. Be concrete — propose specific "
            "patterns and explain WHY they fit this context. Avoid generic advice."
        ),
        model="sonnet",
    ),
    "engineer": Agent(
        name="engineer",
        role="Implementation Engineer",
        expertise={
            "implementation": 0.9, "architecture": 0.6,
            "testing": 0.7, "risk": 0.4, "ux": 0.2,
        },
        system_prompt=(
            "You are a pragmatic engineer. Focus on build feasibility, "
            "complexity, and what will actually work in practice. Flag anything "
            "that sounds good in theory but is painful to implement. Suggest "
            "simpler alternatives when you see over-engineering."
        ),
        model="sonnet",
    ),
    "researcher": Agent(
        name="researcher",
        role="Prior Art Researcher",
        expertise={
            "research": 0.9, "architecture": 0.5,
            "implementation": 0.3, "risk": 0.3,
        },
        system_prompt=(
            "You are a researcher. Identify prior art, existing solutions, "
            "and relevant literature. If something already exists that solves "
            "part of this problem, say so. Ground discussion in what's known, "
            "not just what's imagined."
        ),
        model="sonnet",
    ),
    "skeptic": Agent(
        name="skeptic",
        role="Critical Skeptic",
        expertise={
            "risk": 0.9, "testing": 0.8,
            "architecture": 0.5, "implementation": 0.4,
        },
        system_prompt=(
            "You are the skeptic. Your job is to find failure modes, edge cases, "
            "hidden assumptions, and risks. Ask the hard questions. If something "
            "is being hand-waved, call it out. Be specific about WHAT could go "
            "wrong and HOW LIKELY it is."
        ),
        model="sonnet",
    ),
    "pragmatist": Agent(
        name="pragmatist",
        role="User/Value Pragmatist",
        expertise={
            "ux": 0.8, "business": 0.7,
            "implementation": 0.4, "risk": 0.3,
        },
        system_prompt=(
            "You are the pragmatist. Focus on real-world value, user needs, "
            "and adoption. Ask: who actually uses this? What's the simplest "
            "version that delivers value? Cut scope ruthlessly. Features nobody "
            "uses are worse than missing features."
        ),
        model="sonnet",
    ),
}

# ---------------------------------------------------------------------------
# Agent response parsing
# ---------------------------------------------------------------------------

@dataclass
class AgentResponse:
    agent_name: str
    raw_content: str
    summary: str
    key_claims: List[str]
    recommendation: str
    confidence: float
    weight: float
    agreements: List[str] = field(default_factory=list)
    dissents: List[dict] = field(default_factory=list)
    questions: List[str] = field(default_factory=list)

    @classmethod
    def from_raw(cls, agent_name: str, raw: str, weight: float) -> "AgentResponse":
        """Parse structured JSON from agent response, with fallback."""
        try:
            text = raw.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()
            if text.startswith("json"):
                text = text[4:].strip()
            data = json.loads(text)

            claims_data = data.get("claims", [])
            if claims_data and isinstance(claims_data[0], dict):
                key_claims = [c["claim"] for c in claims_data if "claim" in c]
                summary = "; ".join(
                    f"{c['claim']} [{c.get('evidence', 'no evidence')}]"
                    for c in claims_data
                )
                confidence = (
                    sum(c.get("confidence", 0.5) for c in claims_data) / len(claims_data)
                    if claims_data else 0.5
                )
            else:
                key_claims = data.get("key_claims", claims_data)
                summary = data.get("summary", "")
                confidence = float(data.get("confidence", 0.5))

            return cls(
                agent_name=agent_name,
                raw_content=raw,
                summary=summary,
                key_claims=key_claims,
                recommendation=data.get("recommendation", ""),
                confidence=confidence,
                weight=weight,
                agreements=data.get("agreements", []),
                dissents=data.get("dissents", []),
                questions=data.get("questions", []),
            )
        except (json.JSONDecodeError, ValueError):
            return cls(
                agent_name=agent_name,
                raw_content=raw,
                summary=raw[:500],
                key_claims=[],
                recommendation="",
                confidence=0.5,
                weight=weight,
            )


# ---------------------------------------------------------------------------
# Weight computation and agent history
# ---------------------------------------------------------------------------

AGENT_TOOLS: Dict[str, List[str]] = {
    "engineer": ["file_read"],
    "skeptic": ["grep"],
    "researcher": ["web_search"],
    "architect": [],
    "pragmatist": [],
}


def apply_agent_history(agents: Dict[str, Agent]) -> Dict[str, Agent]:
    """Load historical accuracy and apply to agent objects."""
    history = load_agent_history()
    for name, agent in agents.items():
        if name in history:
            agent.historical_accuracy = history[name]
    return agents


def compute_weight(agent: Agent, domain: str, confidence: float) -> float:
    """Compute response weight including historical accuracy."""
    relevance = agent.relevance(domain)
    return round(relevance * confidence * agent.historical_accuracy, 3)


def load_agent_history() -> Dict[str, float]:
    if AGENT_HISTORY_PATH.exists():
        data = json.loads(AGENT_HISTORY_PATH.read_text(encoding="utf-8"))
        return data.get("accuracy", {})
    return {}


def save_agent_history(accuracy: Dict[str, float]):
    data = {"accuracy": accuracy, "updated": datetime.now().isoformat()}
    AGENT_HISTORY_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def update_agent_accuracy(agent_name: str, contribution_score: float, alpha: float = 0.3):
    """Update agent accuracy via EMA. Called by st.py score command."""
    history = load_agent_history()
    current = history.get(agent_name, 1.0)
    updated = round((1 - alpha) * current + alpha * contribution_score, 4)
    history[agent_name] = updated
    save_agent_history(history)
    return updated


# ---------------------------------------------------------------------------
# Model escalation
# ---------------------------------------------------------------------------

def select_model(task_type: str, domain: str = "", confidence_needed: float = 0.5) -> str:
    """Select model tier for a Task agent.

    Returns "haiku", "sonnet", or "opus".
    """
    opus_tasks = {"architecture", "research", "strategic", "novel"}
    if task_type in opus_tasks or confidence_needed >= 0.85:
        return "opus"

    if task_type == "validate" and domain in {"math", "algorithm", "optimization", "numerical"}:
        return "opus"

    haiku_tasks = {"quick_check", "smoke_test", "format"}
    if task_type in haiku_tasks and confidence_needed < 0.5:
        return "haiku"

    return "sonnet"


# ---------------------------------------------------------------------------
# Critique and prompt templates
# ---------------------------------------------------------------------------

PRAGMATIC_CRITIQUE_TEMPLATE = """\
## Adaptive Self-Critique

You are reviewing this output. You have two jobs:

**Job 1 (Reframe — highest priority):**
- Is this solving the RIGHT problem, or a convenient version of it?
- What assumption is the answer built on that might be wrong?
- Is there a reframe that changes the entire approach?
- Is the ambition level right? (Too safe/incremental? Or too scattered/unfocused?)
- For research: are we pushing intellectual boundaries, or just doing housekeeping?
- For products: are we building what users need, or what's convenient to build?

**Job 2 (Technical Critic):**
- What's factually wrong or missing?
- What bugs, gaps, or incomplete parts exist?
- What's the single most important improvement?

## The Output Being Reviewed
{output}

## Instructions
First give your reframe (1-3 sentences — the insight that changes the approach).
Then give your technical critique (specific fixes).
Then produce the revised output implementing both.

The reframe is the MOST VALUABLE part. If you don't challenge the premise, you're just copy-editing. But "ship it" and "cut scope" are not always the right reframe — sometimes the answer is "go deeper" or "be more ambitious."
"""


LIGHT_CHECK_TEMPLATE = """\
You are a critical skeptic performing a quick spot-check.

## Context
{context}

## Decision Under Review
{question}

## Instructions
In exactly 2 sentences:
1. State the biggest risk if this decision is wrong.
2. Give a verdict: GREEN (proceed), YELLOW (reconsider one thing), or RED (stop and rethink).

Be blunt. No preamble. No hedging. Just the risk and the verdict.
"""


def build_pragmatic_critique_prompt(output: str, context: str = "") -> str:
    """Build prompt for adaptive self-critique."""
    parts = []
    if context:
        parts.append(f"## Context\n{context}\n")
    parts.append(PRAGMATIC_CRITIQUE_TEMPLATE.format(output=output[:6000]))
    return "\n".join(parts)


def build_light_check_prompt(question: str, context: str = "") -> str:
    """Build prompt for a quick skeptic spot-check."""
    return LIGHT_CHECK_TEMPLATE.format(
        context=context[:3000] if context else "No additional context provided.",
        question=question,
    )
