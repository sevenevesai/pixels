---
name: critique
description: Run adaptive self-critique on work done in this session. Challenges assumptions, finds what's missing, and revises — adapting to project type.
model: sonnet
---

# Adaptive Self-Critique

Review the work done so far in this conversation.

## Step 1: Assess what kind of project and work this is

Before critiquing, determine:
- **Project type**: Research? Product? Tool? Exploration?
- **What was the goal of the work?** Novel discovery? Bug fixing? Feature building? Analysis?
- **What mode should critique be in?**
  - Research: prioritize intellectual depth, novelty, rigor. Ask "did we push boundaries?"
  - Product: prioritize user impact, correctness, simplicity. Ask "would a user notice?"
  - Tool: prioritize API quality, edge cases, documentation. Ask "does it work correctly?"
  - Exploration: prioritize learning, evidence, direction. Ask "did we learn something real?"

## Step 2: Reframe (highest priority)

- Is this solving the RIGHT problem, or a convenient version of it?
- What assumption is the work built on that might be wrong?
- Is there a reframe that changes the entire approach?
- **Is the ambition level right?**
  - For research: are we doing housekeeping when we should be pushing frontiers?
  - For products: are we gold-plating when we should be shipping?
  - For exploration: are we converging too early when we should stay open?

"Ship it" and "cut scope" are valid critiques sometimes. "Go deeper" and "be more ambitious" are equally valid. Match the advice to the project.

## Step 3: Technical critique

- What's factually wrong or incomplete?
- What bugs, gaps, or untested parts exist?
- What's the single most important improvement?

## Step 4: Act on findings

1. Load memory context: `python S:\SocraticTable\st.py brief`
2. Review ALL changes made in this conversation
3. Identify the top 3 issues (reframe + technical gaps)
4. For each issue: state the problem and implement the fix
5. Save findings: `python S:\SocraticTable\st.py save --content "<critique summary>" --name "<session_name>_critique"`

## Rules

- The reframe is the MOST VALUABLE part. Challenge the premise before fixing details.
- Be specific. "Could be better" is worthless. Name the file, the line, the exact problem.
- Fix what you find. Critique without action is just complaining.
- Don't default to one mode. "Ship it" is not always right. "Go deeper" is not always right. Read the project.
