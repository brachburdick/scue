# SCUE Agent Preamble — Addendum: Environment & Session Artifacts

> Paste this alongside the main `AGENT_PREAMBLE.md` in every agent session.
> It addresses recurring issues discovered during early agent deployments.

---

## Environment Setup (Do This FIRST, Before Any Code Work)

Agents have repeatedly wasted time discovering the correct Python path and test runner. Follow this sequence at the start of every session that involves running code or tests:

### Step 1: Find the Python interpreter

```bash
# The project uses a .venv virtual environment. ALWAYS check for it first.
ls -la .venv/bin/python 2>/dev/null && echo "FOUND: .venv/bin/python"
```

If `.venv/bin/python` exists, use it for ALL Python commands:

```bash
.venv/bin/python -m pytest tests/test_bridge/ -v
.venv/bin/python -m uvicorn scue.main:app --reload
```

**Do NOT use bare `python` or `python3`.** These resolve to the system Python which does not have project dependencies installed.

### Step 2: Verify pytest is available

```bash
.venv/bin/python -m pytest --version
```

If this fails, tell Brach — the venv may need rebuilding.

### Step 3: Run the relevant test suite BEFORE making changes

```bash
# Run only the tests for your layer to establish a baseline
.venv/bin/python -m pytest tests/test_bridge/ -v    # Bridge (L0)
.venv/bin/python -m pytest tests/test_layer1/ -v     # Layer 1
.venv/bin/python -m pytest tests/test_api/ -v        # API
.venv/bin/python -m pytest tests/ -v                  # Full suite
```

Record the baseline count (e.g., "108 passed, 0 failed") in your session summary.

### Step 4: Run tests AFTER making changes

Same command as Step 3. Compare against baseline. All pre-existing tests must still pass.

### Common Pitfalls (from real agent sessions)

- `command not found: python` → Use `.venv/bin/python`, not `python`
- `No module named pytest` → You're using system Python, not the venv
- `ModuleNotFoundError` for project imports → You're not in the project root, or using wrong Python
- Tests that reference private attributes by name (e.g., `_restart_count`) may exist in other test files outside your scope. If you rename an internal attribute, add a backward-compatible property alias rather than modifying out-of-scope test files.

---

## Session Summary: Write to Disk (Non-Negotiable)

Session summaries are the ONLY communication channel between agents. If it's not written to a file, it doesn't exist for the next agent.

### When to write

Write the session summary to disk as the **LAST** thing you do, after all acceptance criteria are met and all tests pass.

### Where to write

```
sessions/YYYY-MM-DD/[agent]-[task-slug].md
```

Create the date directory if it doesn't exist:

```bash
mkdir -p sessions/$(date +%Y-%m-%d)
```

### Naming convention

- `sessions/2026-03-17/bridge-l0-device-discovery.md`
- `sessions/2026-03-17/bridge-l0-restart-logic.md`
- `sessions/2026-03-17/fe-state-type-updates.md`
- `sessions/2026-03-18/api-yaml-consolidation.md`

Format: `[agent-role]-[task-slug].md`, lowercase, hyphens.

### What to write

The exact session summary format from your handoff packet. Copy it verbatim from your chat output into the file.

### Confirm to Brach

After writing, tell Brach: **"Session summary written to `sessions/YYYY-MM-DD/[filename].md`"** so they can verify.

---

## LEARNINGS.md: Write Entries to Disk (Non-Negotiable)

If your session summary contains a "LEARNINGS.md Candidates" section with any entries, you MUST append them to `LEARNINGS.md` in the project root before ending your session. Do not leave them only in the session summary — the whole point is that future agents read `LEARNINGS.md` at the start of their session.

### When to write

After writing the session summary to disk and before telling Brach you're done.

### How to write

Append your entries to the appropriate section in `LEARNINGS.md`. The file is organized by layer:

- `## Layer 0 — Beat-Link Bridge`
- `## Layer 1 — Track Analysis & Live Tracking`
- `## Layer 2 — Cue Generation`
- `## Layer 3 — Effect Engine`
- `## Layer 4 — Output & Hardware`
- `## UI / WebSocket`
- `## Resolved`

Use the established format:

```
### Short descriptive title
Date: YYYY-MM-DD
Context: What were you doing?
Problem: What went wrong or was surprising?
Fix/Pattern: What's the correct approach?
Prevention: How to avoid in the future?
```

If an entry documents a bug that is now fixed, add `(fixed)` to the title:
`### Bridge listen loop crash does not auto-recover (fixed)`

### Cross-cutting entries

If a learning applies to all agents (e.g., environment issues, naming conventions), add it under a new `## Cross-Cutting / Workflow` section at the bottom of `LEARNINGS.md`, before `## Resolved`.

### Confirm to Brach

After writing, tell Brach: **"LEARNINGS.md updated with N new entries under [section]"** so they can verify.

---

## Iterative Improvement: Flag Preamble Issues

If you encounter a problem during your session that:
- Wasted significant time
- Would affect other agents working on different tasks
- Relates to environment, tooling, or workflow rather than domain-specific code

Flag it in your session summary under a new section:

### Preamble Improvement Candidates

```
- [Issue]: Describe what went wrong
- [Fix]: What should be added to the preamble to prevent this
- [Scope]: Does this affect all agents, or only [specific role]?
```

The Orchestrator reviews these after every session and updates the preamble for future agents.
