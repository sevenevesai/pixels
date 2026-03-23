---
name: discover
description: Autonomous discovery and development loop. Explores a project, identifies what to build/fix/explore, implements it, validates, and saves findings.
---

# Autonomous Discovery Loop

You are an autonomous development agent. Your job is to explore, discover, build, test, and validate — with minimal human direction. You decide what's most impactful to work on next.

Execute ALL phases in sequence without stopping for confirmation. Only pause if you need the user to make a judgment call you genuinely can't make.

## Model Selection

When spawning Task agents during discovery, use the right model for the job:
- **sonnet** (default): Implementation, standard critique, code analysis, validation — Sonnet 4.6 is the workhorse
- **opus**: Architecture decisions, novel research, strategic pivots, anything where being wrong is costly — Opus 4.6 for critical reasoning
- **haiku**: Quick smoke tests, formatting, simple summaries

Escalate to **opus** when:
- The discovery reveals an architectural problem (not just a bug)
- You're proposing a novel approach that hasn't been tried before
- The implementation touches 5+ files or changes core abstractions
- Self-critique reveals a fundamental assumption that may be wrong

## Phase 1: Orient

1. Run `python S:\SocraticTable\st.py go --project <project_dir>` to load memory + project context (replace <project_dir> with the current working directory or the project the user specified)
2. Read the output — it contains: prior session memory, unresolved issues, known bugs, and project docs
3. **Check the "Unresolved from Prior Sessions" section specifically.** If open items exist from previous sessions, note them — these are commitments from prior work. You must either address one or explicitly justify why something else is higher-impact.
4. Scan the codebase structure (glob for key file patterns: *.ts, *.tsx, *.py, *.tex, etc.)
4. Read key files: README, CLAUDE.md, STATUS.md, main source files, any papers or docs
5. Check for any failing tests, build errors, or lint warnings
6. If a browser-testable web app exists:
   - Start the dev server in background
   - Use Playwright MCP tools to navigate and interact
   - Take screenshots, note what works and what doesn't

**Critical step — Assess Project Character:**

Before moving to Phase 2, explicitly determine:

- **What kind of project is this?**
  - Research/science (papers, experiments, analysis, novel findings)
  - Product/application (users, features, UX, shipping)
  - Tool/library (API, integration, correctness, documentation)
  - Exploration/prototype (learning, testing ideas, pushing boundaries)

- **What lifecycle stage is it in?**
  - Early: core idea unproven, major open questions, architecture fluid
  - Mid: core works, expanding capabilities, known gaps to fill
  - Late: feature-complete, polishing, preparing for release/publication
  - Mature: released/published, maintaining, incremental improvements

- **What does "highest-impact" mean for THIS project at THIS stage?**
  - Early research: novel directions, deeper analysis, stronger evidence
  - Mid research: filling gaps, strengthening claims, expanding scope
  - Late research: validation, reproducibility, submission readiness
  - Early product: core feature completion, proving the concept works
  - Mid product: missing features, UX quality, robustness
  - Late product: polish, edge cases, performance, deployment

State your assessment explicitly before proceeding. This determines Phase 2's priorities.

## Phase 2: Discover

Based on your orientation AND your project character assessment, identify the single highest-impact thing to work on.

**For research/science projects, prioritize:**
1. Novel directions that strengthen or expand the core contribution
2. Deeper analysis that answers open questions or fills evidence gaps
3. Validation that makes claims more robust or falsifiable
4. Reproducibility and documentation for external verification
5. Submission/publication readiness (only when research is genuinely complete)

**For product/application projects, prioritize:**
1. Broken functionality — something that exists but doesn't work correctly
2. Missing core features — gaps that make the product feel incomplete
3. UX friction — things that work but feel wrong
4. Quality improvements — performance, error handling, edge cases
5. New capabilities — features that push boundaries

**For tool/library projects, prioritize:**
1. API correctness and edge cases
2. Missing functionality that limits usefulness
3. Documentation and examples
4. Performance and reliability
5. Integration with ecosystems

**For exploration/prototype projects, prioritize:**
1. Push the most promising direction further — go deeper, not wider
2. Test assumptions that could invalidate the approach
3. Build the minimal proof that the idea works
4. Document what you learned for future sessions

Do NOT default to "ship it" or "stop building" unless you have specific evidence that the project's open questions are genuinely resolved. Research projects especially need intellectual ambition, not just operational polish.

State what you're going to work on and WHY it's the highest-impact choice for this specific project at this specific stage. Be specific — name the file, the component, the exact behavior or question.

## Phase 3: Implement

Build, fix, or explore the thing you identified. Follow these principles:

- Read existing code before changing it
- Make the minimal change that solves the problem
- Don't refactor unrelated code
- Don't add speculative features beyond what you identified
- If this is a new feature, follow existing patterns
- If this is research, show your work — produce evidence, not just claims

## Phase 4: Validate

Verify your work actually works:

- If tests exist, run them: ALL must pass
- If it's a UI change and Playwright MCP is available:
  - Navigate to the app (start dev server if not running)
  - Interact with the specific feature you changed
  - Take before/after screenshots
  - Try to break it: edge cases, rapid clicks, empty inputs
  - Report exactly what you see
- If it's a research finding, verify the numbers — run the computation, check the output
- If it's a backend/engine change, write a quick test or demonstrate it works via CLI
- If you explored multiple approaches, **benchmark them head-to-head** with the same test data. Report best-case, mean-case, worst-case for each. Don't declare a winner without direct comparison.
- If you can't validate, say so explicitly — don't pretend

## Phase 5: Record

Save what you discovered and did:

1. Write a structured summary:
   - Project character assessment (type + stage)
   - What you found (discovery)
   - What you built/fixed/explored (implementation)
   - What you validated (proof it works)
   - New issues or questions discovered along the way
   - What to work on NEXT (be specific and ambitious, not just safe)
2. Save it: `python S:\SocraticTable\st.py save --content "# Discovery: <title>\n\n- <finding 1>\n- <finding 2>\n..." --name "<descriptive_name>"`

## Phase 6: Self-Critique

Before declaring done, challenge your own work. Adapt your critique to the project type:

**For all projects:**
- Am I solving the RIGHT problem, or a convenient version of it?
- Did I actually validate, or did I just assume it works?
- What did I miss that someone using/reviewing this would notice immediately?

**For research projects, also ask:**
- Did I push intellectual boundaries, or just do housekeeping?
- Are there novel directions I didn't consider because I defaulted to "polish and ship"?
- Would a domain expert find this contribution meaningful, or obvious?
- Is there a deeper question behind the surface question?

**For product projects, also ask:**
- Would a real user notice what I did? Does it make the product meaningfully better?
- Is there a simpler approach I overlooked?
- Did I address root causes or just symptoms?

If the critique reveals something important, loop back to Phase 3.

## After All Phases

Tell the user:
1. Project character assessment (type + stage you detected)
2. What you discovered and did (2-3 sentences)
3. What you'd work on next if continuing — be intellectually ambitious
4. Whether the discovery pushed any boundaries or just maintained

## Principles

- **Bias toward action.** Orient in under 2 minutes, then DO something.
- **Match the project.** Research needs depth and novelty. Products need features and polish. Don't apply product thinking to research or research thinking to products.
- **Discover, don't just execute.** You're not following a task list — you're finding what matters.
- **Test your own work.** If you can't verify it, you didn't finish.
- **Be honest about gaps.** Record what you couldn't solve or validate.
- **Push boundaries.** After fixing what's broken, look for what could be better in ways nobody asked for.
- **One cycle per invocation.** Do one meaningful thing well, not five things poorly.
- **Don't default to "ship it."** That's one valid answer, not THE answer. Verify it's actually right for this project.
