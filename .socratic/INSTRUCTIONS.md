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
python .socratic/st.py save --content "# Topic\n..." --name "topic"
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
