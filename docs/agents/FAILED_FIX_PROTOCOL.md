# Failed Fix Protocol

When a siloed agent attempts a fix and it fails (test still fails, regression introduced,
or the approach doesn't work), the agent **must** record a structured incident before
trying again or moving on.

## Incident Record Format

Append to `.agent/incidents.jsonl`:

```json
{
  "timestamp": "2026-03-25T14:30:00Z",
  "task_id": "bridge-reliability-001",
  "agent_silo": "python-backend",
  "bug_id": "update_position_unwired",
  "attempt_number": 1,
  "approach": "Wired adapter.on_beat to tracker.update_position() in main.py",
  "result": "failed",
  "failure_reason": "on_beat callback signature mismatch: expects (player_number, beat_within_bar, bpm) but update_position() expects (player_number, position_ms)",
  "files_modified": ["scue/main.py"],
  "tests_run": "python -m pytest tests/test_layer1/test_tracking.py -v",
  "test_output_summary": "3 passed, 1 failed: test_position_updates_on_beat",
  "next_hypothesis": "Need to compute position_ms from beat_within_bar + beat_grid before calling update_position()",
  "escalate": false
}
```

### Required Fields

| Field | Type | Description |
|-------|------|-------------|
| `timestamp` | ISO-8601 | When the attempt was made |
| `task_id` | string | Parent task reference |
| `agent_silo` | string | `"python-backend"` \| `"frontend"` \| `"java-bridge"` |
| `bug_id` | string | Descriptive slug for the bug |
| `attempt_number` | int | Which attempt this is (1-indexed) |
| `approach` | string | What was tried (1-2 sentences) |
| `result` | string | `"failed"` \| `"partial"` |
| `failure_reason` | string | Why it failed — be specific |
| `files_modified` | string[] | Files changed during the attempt |
| `tests_run` | string | Test command executed |
| `test_output_summary` | string | Key test results (pass/fail counts + failing test names) |
| `next_hypothesis` | string | What to try next |
| `escalate` | bool | Whether to request a researcher agent |

## Escalation Rules

1. **After 2 failed attempts** on the same `bug_id` → set `escalate: true`
2. When `escalate: true`, the orchestrator dispatches a **researcher agent** that:
   - Reads all incidents for that `bug_id`
   - Reads the relevant source files
   - Searches for related patterns in the codebase
   - Produces a diagnosis document at `specs/investigations/{bug_id}.md`
3. The original silo agent reads the diagnosis and tries one more time
4. **After 3 total failed attempts** (2 original + 1 post-research) → bug is marked
   **blocked** and deferred to the next session with a human

## Why This Exists

Agents get scope blindness when stuck in a fix loop. They apply increasingly desperate
patches without stepping back to question assumptions. The 2-attempt threshold forces
a pause and fresh perspective from a researcher who can look at the problem from a
different angle — checking git history, reading related code, searching for similar
patterns elsewhere in the codebase.
