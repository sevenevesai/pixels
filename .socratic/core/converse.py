"""
Flowing Conversation Engine — Weighted Roundtable v0.3

A reactive dialogue system where agents respond to each other sequentially,
building a natural conversation. The Opus lead makes dynamic routing decisions
after each turn: who speaks next, when to stop, when to escalate.

Architecture:
  - ConversationLog: append-only message log with speaker, weight, content
  - ContextWindow: sliding window (last N messages + pinned pivotal messages)
  - Router: lead decides next speaker based on what was just said
  - Convergence: stops when novelty drops or max_turns reached

Usage:
  The Opus orchestrator imports this module, then:
    1. Creates a Conversation with topic + agents
    2. Calls get_next_turn() to get routing decision + prompt
    3. Spawns the agent via Task tool, gets response
    4. Calls add_turn() with the response
    5. Repeats until conversation.converged

This module does NOT call any LLM APIs — it structures the conversation
for the Opus lead to orchestrate.
"""

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from pathlib import Path

# Import shared definitions
from core.roundtable import (
    Agent, STANDARD_AGENTS, AGENT_TOOLS,
    compute_weight, apply_agent_history, load_agent_history,
)

# ---------------------------------------------------------------------------
# Conversation data structures
# ---------------------------------------------------------------------------

@dataclass
class Turn:
    """A single turn in the conversation."""
    turn_number: int
    agent_name: str
    agent_role: str
    weight: float
    content: str
    is_pivotal: bool = False        # flagged by lead as conversation-shifting
    provoked_by: Optional[str] = None  # which agent/turn triggered this
    tags: List[str] = field(default_factory=list)  # insight types


@dataclass
class RoutingDecision:
    """Lead's decision about what happens next."""
    next_agent: str
    reason: str                     # why this agent should speak now
    targeted_question: Optional[str] = None  # specific question to ask
    context_window: List[int] = field(default_factory=list)  # turn numbers to include
    should_stop: bool = False
    stop_reason: str = ""


@dataclass
class Conversation:
    """Full conversation state."""
    topic: str
    domain: str
    agents: Dict[str, Agent]
    turns: List[Turn] = field(default_factory=list)
    max_turns: int = 12
    context_window_size: int = 4    # last N turns visible to next agent
    pinned_turns: List[int] = field(default_factory=list)  # always-visible pivotal turns
    converged: bool = False
    convergence_reason: str = ""
    decisions: List[str] = field(default_factory=list)
    project_context: str = ""

    @property
    def turn_count(self) -> int:
        return len(self.turns)

    @property
    def last_speaker(self) -> Optional[str]:
        return self.turns[-1].agent_name if self.turns else None

    def speakers_so_far(self) -> Dict[str, int]:
        """Count how many times each agent has spoken."""
        counts: Dict[str, int] = {}
        for t in self.turns:
            counts[t.agent_name] = counts.get(t.agent_name, 0) + 1
        return counts

    def agent_said(self, agent_name: str) -> List[Turn]:
        """Get all turns by a specific agent."""
        return [t for t in self.turns if t.agent_name == agent_name]


# ---------------------------------------------------------------------------
# Context window management
# ---------------------------------------------------------------------------

def build_context_window(
    conv: Conversation,
    for_agent: str,
    memory_context: Optional[str] = None,
) -> str:
    """Build the context a speaking agent sees.

    Includes:
    - Memory from prior sessions (if available)
    - The original topic
    - Pinned pivotal turns (always visible)
    - Last N turns (sliding window)
    - Compressed summary of earlier turns (if any exist before the window)
    """
    parts = [f"## Topic\n{conv.topic}\n"]

    if memory_context:
        parts.append(f"{memory_context}\n")

    if conv.project_context:
        ctx = conv.project_context[:3000]
        parts.append(f"## Project Context\n{ctx}\n")

    # Determine which turns are visible
    window_start = max(0, conv.turn_count - conv.context_window_size)
    window_turns = set(range(window_start, conv.turn_count))
    pinned = set(conv.pinned_turns)
    visible = sorted(window_turns | pinned)

    # Compressed summary of turns before the window
    early_turns = [t for t in conv.turns if t.turn_number < window_start
                   and t.turn_number not in pinned]
    if early_turns:
        summary_lines = []
        for t in early_turns:
            # One-line summary per early turn
            first_sentence = t.content.split(".")[0] + "." if "." in t.content else t.content[:100]
            summary_lines.append(f"- **{t.agent_name}** (turn {t.turn_number}): {first_sentence}")
        parts.append("## Earlier Discussion (compressed)\n" + "\n".join(summary_lines) + "\n")

    # Full visible turns
    if visible:
        parts.append("## Recent Conversation\n")
        for idx in visible:
            if idx < len(conv.turns):
                t = conv.turns[idx]
                pivot_marker = " [PIVOTAL]" if t.is_pivotal else ""
                parts.append(
                    f"### Turn {t.turn_number} — {t.agent_name} "
                    f"({t.agent_role}, weight: {t.weight}){pivot_marker}\n"
                    f"{t.content}\n"
                )

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Agent turn prompts
# ---------------------------------------------------------------------------

CONVERSATION_AGENT_PROMPT = """\
# Role: {role}

{system_prompt}

## Instructions
You are in a flowing conversation with other specialists. You've seen their recent messages above.

Respond naturally — react to what was said, build on it, challenge it, or take it in a new direction.
{targeted_question}

Rules:
- Be concise (under 200 words)
- React to specific points from the conversation (reference who said what)
- If you have nothing new to add, say "I'll pass — [agent] covered it" (this is fine)
- State your confidence (0.0-1.0) at the end
- If you notice something nobody else has mentioned, lead with that

Do NOT use JSON format. Speak naturally. End with "Confidence: X.X"
"""


def build_turn_prompt(
    agent: Agent,
    conv: Conversation,
    targeted_question: Optional[str] = None,
    memory_context: Optional[str] = None,
) -> str:
    """Build the full prompt for an agent's turn in the conversation."""
    context = build_context_window(conv, agent.name, memory_context)

    tq = ""
    if targeted_question:
        tq = f"\n**The lead is specifically asking you:** {targeted_question}\n"

    prompt = context + "\n" + CONVERSATION_AGENT_PROMPT.format(
        role=agent.role,
        system_prompt=agent.system_prompt,
        targeted_question=tq,
    )
    return prompt


# ---------------------------------------------------------------------------
# Routing logic (for the Opus lead)
# ---------------------------------------------------------------------------

ROUTING_PROMPT = """\
You just heard {last_speaker} say:
"{last_content}"

Current conversation state:
- Topic: {topic}
- Turns so far: {turn_count}/{max_turns}
- Speakers used: {speaker_counts}
- Agents available: {available}

Decide:
1. WHO should speak next? (Pick the agent whose expertise is most relevant to what was just said, OR pick someone who hasn't spoken and might have a fresh angle)
2. Should you ask them a SPECIFIC question, or let them react freely?
3. Should the conversation STOP? (Only if: the last 2-3 messages are repetitive, or a clear decision has been reached, or all agents have passed)

Respond as JSON:
```json
{{
  "next_agent": "agent_name",
  "reason": "why this agent should speak now (1 sentence)",
  "targeted_question": "specific question or null",
  "is_previous_pivotal": true/false,
  "should_stop": false,
  "stop_reason": ""
}}
```
"""


def build_routing_prompt(conv: Conversation) -> str:
    """Build the prompt the Opus lead uses to decide who speaks next.

    Includes novelty tracking signal so the lead knows when the
    conversation is becoming repetitive.
    """
    last = conv.turns[-1] if conv.turns else None
    speakers = conv.speakers_so_far()
    available = [n for n in conv.agents if n != (last.agent_name if last else None)]

    # Inject novelty signal
    novelty_line = novelty_summary(conv) if conv.turns else ""

    prompt = ROUTING_PROMPT.format(
        last_speaker=last.agent_name if last else "nobody",
        last_content=last.content[:500] if last else "Conversation hasn't started.",
        topic=conv.topic,
        turn_count=conv.turn_count,
        max_turns=conv.max_turns,
        speaker_counts=json.dumps(speakers),
        available=json.dumps(available),
    )

    if novelty_line:
        prompt += f"\n**Novelty tracker:** {novelty_line}\n"

    return prompt


def suggest_opening_speaker(conv: Conversation) -> RoutingDecision:
    """Suggest who should speak first based on domain relevance."""
    best = max(conv.agents.values(), key=lambda a: a.relevance(conv.domain))
    return RoutingDecision(
        next_agent=best.name,
        reason=f"Highest domain relevance ({conv.domain}: {best.relevance(conv.domain)})",
        targeted_question=f"What's your initial take on: {conv.topic}",
    )


# ---------------------------------------------------------------------------
# Turn management
# ---------------------------------------------------------------------------

def add_turn(
    conv: Conversation,
    agent_name: str,
    content: str,
    confidence: float = 0.5,
    is_pivotal: bool = False,
    provoked_by: Optional[str] = None,
    tags: Optional[List[str]] = None,
) -> Turn:
    """Add a completed turn to the conversation."""
    agent = conv.agents[agent_name]
    weight = compute_weight(agent, conv.domain, confidence)

    turn = Turn(
        turn_number=conv.turn_count,
        agent_name=agent_name,
        agent_role=agent.role,
        weight=weight,
        content=content,
        is_pivotal=is_pivotal,
        provoked_by=provoked_by,
        tags=tags or [],
    )
    conv.turns.append(turn)

    if is_pivotal:
        conv.pinned_turns.append(turn.turn_number)

    return turn


def parse_confidence(response: str) -> float:
    """Extract confidence from agent's natural-language response."""
    lines = response.strip().split("\n")
    for line in reversed(lines):
        line_lower = line.lower().strip()
        if "confidence" in line_lower:
            for token in line_lower.replace(":", " ").split():
                try:
                    val = float(token)
                    if 0.0 <= val <= 1.0:
                        return val
                except ValueError:
                    continue
    return 0.5  # default


# ---------------------------------------------------------------------------
# Convergence detection — novelty tracking
# ---------------------------------------------------------------------------

def _turn_words(turn: Turn) -> set:
    """Extract content words from a turn (skip common stopwords)."""
    STOP = {
        "the", "and", "but", "for", "not", "are", "was", "has", "been", "this",
        "that", "with", "from", "will", "can", "all", "also", "more", "than",
        "just", "about", "would", "could", "should", "into", "their", "which",
        "some", "what", "when", "there", "other", "like", "very", "think",
        "here", "well", "point", "agree", "said", "think", "need", "make",
    }
    words = set()
    for w in turn.content.lower().split():
        w = w.strip(".,!?;:\"'()-")
        if len(w) > 2 and w not in STOP:
            words.add(w)
    return words


def measure_novelty(conv: Conversation) -> Dict:
    """Measure how much novelty each turn added to the conversation.

    Uses two complementary signals:
    1. Word novelty — fraction of new content words vs all prior turns
    2. Semantic overlap — how similar this turn is to the most similar prior turn
       (catches paraphrasing that word novelty misses)

    Returns a dict with:
      - per_turn: list of (turn_number, novelty_score)
      - recent_trend: average novelty of last 3 turns
      - is_stale: True if recent novelty below threshold
      - recommendation: "continue", "probe", or "stop"
    """
    if len(conv.turns) < 2:
        return {
            "per_turn": [],
            "recent_trend": 1.0,
            "is_stale": False,
            "recommendation": "continue",
        }

    per_turn = []
    cumulative_words = set()

    for i, turn in enumerate(conv.turns):
        turn_words = _turn_words(turn)
        if not turn_words:
            per_turn.append((turn.turn_number, 0.0))
            continue

        # Signal 1: Word novelty (new words vs cumulative)
        new_words = turn_words - cumulative_words
        word_novelty = len(new_words) / len(turn_words)
        cumulative_words |= turn_words

        # Signal 2: Max similarity to any prior turn (semantic overlap)
        max_sim = 0.0
        for prev in conv.turns[:i]:
            prev_words = _turn_words(prev)
            if prev_words and turn_words:
                overlap = len(turn_words & prev_words) / min(len(turn_words), len(prev_words))
                max_sim = max(max_sim, overlap)

        # Combined score: low novelty = high word overlap OR low new words
        # Both signals matter — paraphrasing has high overlap, agreement has low new words
        semantic_novelty = 1.0 - max_sim
        combined = min(word_novelty, semantic_novelty)

        per_turn.append((turn.turn_number, round(combined, 3)))

    # Recent trend: average of last 3 turns (skip first turn — always 1.0)
    scoreable = per_turn[1:] if len(per_turn) > 1 else per_turn
    recent = [n for _, n in scoreable[-3:]]
    recent_trend = sum(recent) / len(recent) if recent else 1.0

    # Recommendation thresholds
    if recent_trend < 0.20:
        recommendation = "stop"
    elif recent_trend < 0.35:
        recommendation = "probe"
    else:
        recommendation = "continue"

    return {
        "per_turn": per_turn,
        "recent_trend": round(recent_trend, 3),
        "is_stale": recent_trend < 0.20,
        "recommendation": recommendation,
    }


def novelty_summary(conv: Conversation) -> str:
    """One-line novelty summary for injection into routing prompts."""
    data = measure_novelty(conv)
    trend = data["recent_trend"]
    rec = data["recommendation"]

    if rec == "stop":
        return (f"⚠ NOVELTY LOW ({trend:.0%}) — last 3 turns mostly repeated "
                f"prior content. Consider stopping or asking a specific new question.")
    elif rec == "probe":
        return (f"Novelty declining ({trend:.0%}). Consider a targeted question "
                f"to a fresh agent to introduce new perspective.")
    else:
        return f"Novelty healthy ({trend:.0%})."


def mark_converged(conv: Conversation, reason: str, decisions: List[str]):
    """Mark conversation as converged with final decisions."""
    conv.converged = True
    conv.convergence_reason = reason
    conv.decisions = decisions


def save_to_memory(conv: Conversation, export_path: str):
    """Export conversation to markdown and extract summary."""
    export_conversation_doc(conv, export_path)
    try:
        from core.session_memory import summarize_session, save_summary
        text = Path(export_path).read_text(encoding="utf-8")
        summary = summarize_session(text, use_llm=False)
        save_summary(summary, Path(export_path).stem)
        return {"path": export_path, "summary": summary}
    except ImportError:
        return {"status": "session_memory not available"}


def get_memory_context(topic: str) -> Optional[str]:
    """Retrieve relevant memory for a conversation topic.

    Uses session brief (recent session summaries) for context injection.
    """
    try:
        from core.session_memory import load_brief
        brief = load_brief(max_sessions=5)
        return brief if brief else None
    except ImportError:
        return None


# ---------------------------------------------------------------------------
# Session I/O
# ---------------------------------------------------------------------------

def create_conversation(
    topic: str,
    domain: str = "architecture",
    agent_names: Optional[List[str]] = None,
    context_path: Optional[str] = None,
    max_turns: int = 12,
    context_window: int = 4,
) -> Conversation:
    """Create a new flowing conversation."""
    if agent_names:
        agents = {n: STANDARD_AGENTS[n] for n in agent_names if n in STANDARD_AGENTS}
    else:
        agents = dict(STANDARD_AGENTS)

    agents = apply_agent_history(agents)

    project_context = ""
    if context_path and Path(context_path).exists():
        project_context = Path(context_path).read_text(encoding="utf-8")

    return Conversation(
        topic=topic,
        domain=domain,
        agents=agents,
        max_turns=max_turns,
        context_window_size=context_window,
        project_context=project_context,
    )


def save_conversation(conv: Conversation, path: str):
    """Save conversation to JSON."""
    data = {
        "topic": conv.topic,
        "domain": conv.domain,
        "max_turns": conv.max_turns,
        "turn_count": conv.turn_count,
        "converged": conv.converged,
        "convergence_reason": conv.convergence_reason,
        "decisions": conv.decisions,
        "agents": list(conv.agents.keys()),
        "pinned_turns": conv.pinned_turns,
        "turns": [asdict(t) for t in conv.turns],
        "timestamp": datetime.now().isoformat(),
    }
    Path(path).write_text(json.dumps(data, indent=2), encoding="utf-8")


def export_conversation_doc(conv: Conversation, path: str):
    """Export conversation as readable markdown."""
    lines = [
        f"# Conversation: {conv.topic}",
        f"\n**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"**Domain:** {conv.domain}",
        f"**Agents:** {', '.join(conv.agents.keys())}",
        f"**Turns:** {conv.turn_count}",
        f"**Converged:** {conv.converged}",
    ]

    if conv.decisions:
        lines.append("\n## Decisions")
        for i, d in enumerate(conv.decisions, 1):
            lines.append(f"{i}. {d}")

    lines.append("\n---\n## Conversation\n")

    for t in conv.turns:
        pivot = " **[PIVOTAL]**" if t.is_pivotal else ""
        provoked = f" *(reacting to {t.provoked_by})*" if t.provoked_by else ""
        lines.append(
            f"### Turn {t.turn_number} — {t.agent_name} "
            f"({t.agent_role}, w={t.weight}){pivot}{provoked}"
        )
        lines.append(f"{t.content}\n")

    if conv.convergence_reason:
        lines.append(f"\n---\n**Convergence:** {conv.convergence_reason}")

    # Participation stats
    lines.append("\n## Participation Stats")
    speakers = conv.speakers_so_far()
    for name, count in sorted(speakers.items(), key=lambda x: x[1], reverse=True):
        agent_turns = conv.agent_said(name)
        avg_weight = sum(t.weight for t in agent_turns) / len(agent_turns) if agent_turns else 0
        pivotals = sum(1 for t in agent_turns if t.is_pivotal)
        lines.append(f"- **{name}**: {count} turns, avg weight {avg_weight:.3f}, {pivotals} pivotal")

    lines.append("")
    Path(path).write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    import argparse
    import os
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")

    parser = argparse.ArgumentParser(description="Flowing Conversation Engine")
    parser.add_argument("--topic", required=True, help="Conversation topic")
    parser.add_argument("--context", help="Path to context file")
    parser.add_argument("--agents", help="Comma-separated agent names")
    parser.add_argument("--domain", default="architecture")
    parser.add_argument("--max-turns", type=int, default=12)
    parser.add_argument("--window", type=int, default=4, help="Context window size")
    args = parser.parse_args()

    agent_names = args.agents.split(",") if args.agents else None
    conv = create_conversation(
        args.topic, args.domain, agent_names,
        args.context, args.max_turns, args.window,
    )

    # Print opening state
    print(f"\n{'='*60}")
    print(f"CONVERSATION: {conv.topic}")
    print(f"{'='*60}")
    print(f"Domain: {conv.domain}")
    print(f"Agents: {', '.join(conv.agents.keys())}")
    print(f"Max turns: {conv.max_turns} | Context window: {conv.context_window_size}")

    # Suggest opening
    opening = suggest_opening_speaker(conv)
    print(f"\nSuggested opener: {opening.next_agent}")
    print(f"Reason: {opening.reason}")
    print(f"Question: {opening.targeted_question}")

    print(f"\n--- Orchestration flow ---")
    print(f"1. Spawn {opening.next_agent} with build_turn_prompt()")
    print(f"2. Add response with add_turn()")
    print(f"3. Use build_routing_prompt() to decide next speaker")
    print(f"4. Repeat until converged or max_turns reached")
    print(f"5. Export with export_conversation_doc()")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
