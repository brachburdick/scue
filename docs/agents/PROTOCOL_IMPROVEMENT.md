# Protocol Improvement Proposals

Observations about the agent pipeline that should inform future tooling/hook changes.

---

## PIP-001: Session-end documentation gap

**Date:** 2026-03-24
**Observed by:** opus session (strata-reanalysis)
**Frequency:** Multiple times across sessions

### Problem
When an agent session ends, work products (code, tests, docs) are written but operational metadata often lags:
- `tasks.jsonl` statuses not updated (phases show "in_progress" when work is complete)
- `runs.jsonl` missing run records for completed work
- `state-snapshot.json` reflects session start, not end
- New agents read stale metadata and report incorrect project status

This happens because there is no definitive "end" to a session other than what the operator prompts. The agent doesn't know it's about to be shut down, so it doesn't proactively write landing docs.

### Examples
- Strata phases 2, 5, and 5b had run records but tasks.jsonl still showed `"status": "in_progress"` — a new agent reported them as active work when they were done.
- The reanalysis pass, source-aware storage, and pipeline documentation from this session were not captured in any run record or task status until the operator asked.

### Proposed Mitigations
1. **Hook enforcement:** The `audit-run-record.sh` hook already warns if no run record exists. Extend it to also check that no task is `in_progress` without a corresponding incomplete run record.
2. **Session-end prompt:** Add a hook or convention where the operator's "wrap up" / "save" / end-of-session signal triggers a mandatory documentation pass (task status updates + run record + state snapshot).
3. **Agent discipline:** Agents should update `tasks.jsonl` status to `"complete"` immediately when finishing a task, not batch updates at session end. The current pattern of "do all the work, update docs later" creates the gap.
4. **Reduce reliance on tasks.jsonl for status:** `runs.jsonl` is more reliable since agents write it on task completion. The state snapshot and task status could be derived from run records rather than maintained separately.

---

## PIP-002: Verification handoff for UI changes without live hardware

**Date:** 2026-03-24
**Observed by:** opus session (strata-reanalysis)

### Problem
When a session produces frontend UI changes that require live hardware data to verify (e.g., Pioneer-enriched tracks for the reanalysis button), the verification can't happen in the same session. The next agent needs:
1. What to verify
2. What hardware/data setup is needed
3. What the expected behavior is

Without this, the verification either gets skipped or the next agent has to reverse-engineer intent from code.

### Proposed Mitigation
Create a `.agent/verification-pending.md` file for cross-session verification handoffs. Format:
```
## [Feature name]
**Requires:** [hardware/data needed]
**Steps:** [what to do]
**Expected:** [what should happen]
```
The next agent reads this on session start (part of session protocol step 2).
