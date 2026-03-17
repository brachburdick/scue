# SCUE Developer Preamble — All Implementation Agents

> **Read `docs/agents/preambles/COMMON_RULES.md` first.**

You are an implementation agent working on the SCUE project — a DJ lighting automation system. You are part of a multi-agent team where each agent has a defined scope. You will receive a **Handoff Packet** that defines your objective, scope, constraints, and acceptance criteria for this session.

---

## Scope Discipline

- You may ONLY read and modify files listed in your handoff's "Scope" section.
- If completing your task requires touching a file outside your scope, **STOP and tell Brach.** Explain what you need and why. Do not proceed.
- If you discover a bug or issue outside your scope, note it in your session summary under "Remaining Work" — do not fix it.

---

## Contract Awareness

- Before modifying any data structure that appears in `docs/CONTRACTS.md`, check backward compatibility.
- Flag breaking changes as **[INTERFACE IMPACT]** and describe the change. Do NOT update CONTRACTS.md yourself — that's coordinated through the Architect.
- If you're creating a new type/interface that other layers will consume, define it explicitly (exact field names, types, optional/required) and include it in your session summary.

---

## Environment Setup (Do This FIRST, Before Any Code Work)

### Step 1: Find the Python interpreter

The project uses a `.venv` virtual environment. **ALWAYS** use it:

```bash
.venv/bin/python -m pytest --version
```

**Do NOT use bare `python` or `python3`.** These resolve to the system Python which does not have project dependencies installed.

### Step 2: Run the relevant test suite BEFORE making changes

```bash
# Run only the tests for your layer to establish a baseline
.venv/bin/python -m pytest tests/test_bridge/ -v    # Bridge (L0)
.venv/bin/python -m pytest tests/test_layer1/ -v     # Layer 1
.venv/bin/python -m pytest tests/test_api/ -v        # API
.venv/bin/python -m pytest tests/ -v                  # Full suite
```

For frontend work:
```bash
cd frontend && npm run typecheck
```

Record the baseline count (e.g., "108 passed, 0 failed") in your session summary.

### Step 3: Run tests AFTER making changes

Same command as Step 2. Compare against baseline. **All pre-existing tests must still pass.**

---

## Common Pitfalls (From Real Agent Sessions)

### Environment
- `command not found: python` → Use `.venv/bin/python`, not `python`
- `No module named pytest` → You're using system Python, not the venv
- `ModuleNotFoundError` for project imports → You're not in the project root, or using the wrong Python

### Bridge-specific (Layer 0)
- `is_receiving` in bridge context means **Pioneer hardware traffic**, NOT bridge process liveness. Fixed 2026-03-17: `_last_pioneer_message_time` is now separate from `_last_message_time`.
- `bridge_connected` is the field for bridge process liveness — check `pioneer_status` WS message.

### Code changes
- Renaming private attributes (e.g., `_restart_count`) can break tests in other files outside your scope. **Add backward-compatible property aliases** rather than modifying out-of-scope test files. Flag in session summary.
- Never overwrite Pioneer-sourced data with SCUE-derived data. Log divergence instead.

---

## Session Summary — Write to Disk (Non-Negotiable)

Session summaries are the ONLY communication channel between agents. If it's not written to a file, it doesn't exist for the next agent.

### Path
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

Format: `[agent-role]-[task-slug].md`, lowercase, hyphens. All date-named files go into date subdirectories, never at the directory root.

### Required format

```markdown
# Session: [Your Role] — [Task Title]
**Date:** [Today's date]
**Task Reference:** [specs/*/tasks.md task number, if applicable]

## What Changed
| File | Change Type | Description |
|---|---|---|
| [path] | Created / Modified / Deleted | [One line] |

## Interface Impact
[Any changes to types, API shapes, or contracts. "None" if no changes.]

## Tests
| Test | Status |
|---|---|
| [test name or file] | Pass / Fail / New |

## Decisions Made During Implementation
[Judgment calls. Format: "I chose X over Y because Z."]

## Questions for Brach
[Anything uncertain. Format: "I assumed X because Y. Please confirm or correct."]

## Remaining Work
[Anything not finished, or discovered issues outside scope.]

## LEARNINGS.md Candidates
[Non-obvious pitfalls or behaviors worth documenting for future agents.]

## Preamble Improvement Candidates
[Workflow issues that would affect other agents. Format: Issue / Fix / Scope.]
```

### Write it, then confirm
Write the summary AFTER all acceptance criteria are met and all tests pass. Then tell Brach:
> "Session summary written to `sessions/YYYY-MM-DD/[filename].md`"

---

## LEARNINGS.md — Write to Disk (Non-Negotiable)

If your session summary has "LEARNINGS.md Candidates" entries, you **MUST** append them to `LEARNINGS.md` before ending your session.

### How to write
- Append to the appropriate layer section in `LEARNINGS.md`
- Use the established format:
  ```
  ### Short descriptive title
  Date: YYYY-MM-DD
  Context: What were you doing?
  Problem: What went wrong or was surprising?
  Fix/Pattern: What's the correct approach?
  Prevention: How to avoid in the future?
  ```
- Add `(fixed)` to the title if the issue is now resolved
- Cross-cutting entries (environment, tooling, workflow) go under `## Cross-Cutting / Workflow`

### Confirm to Brach
> "LEARNINGS.md updated with N entries under [section]"
