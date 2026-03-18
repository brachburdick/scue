# Protocol Improvements

Append-only log of ideas for improving the multi-agent workflow.
When a pattern emerges during a session, record it here for future protocol revisions.

---

### Orchestrator should have delegation heuristics
Date: 2026-03-17
Context: Traffic blocker investigation. The Orchestrator identified the root cause (missing `device_found` replay on WebSocket connect) and implemented the fix directly in `scue/bridge/adapter.py` instead of generating a handoff packet for a Developer agent.
Observation: The fix was a single-method addition to one file with no architectural decisions — appropriate for inline resolution. But the Orchestrator had no explicit criteria for when to self-resolve vs. delegate.
Improvement: Add a decision gate to the Orchestrator preamble: before fixing a bug, evaluate (1) scope (single file vs. multi-file), (2) complexity (mechanical fix vs. design decision), (3) risk (isolated change vs. cross-layer impact). If the task is single-file, mechanical, and isolated, the Orchestrator may resolve inline. Otherwise, delegate to a Developer agent with a handoff packet.
Reference: `docs/bugs/layer0-bridge.md` entry "Devices empty despite active player_status messages" and `sessions/2026-03-17/orchestrator-day-summary.md`.

### Incorporate positive feedback into agent prompts
Date: 2026-03-17
Context: Agents complete tasks but receive no signal about quality beyond pass/fail from the Validator.
Observation: Reinforcing good patterns (concise session summaries, clean diffs, proactive LEARNINGS updates) would help agents maintain high-quality habits across sessions. Currently the prompts are purely instructional — they say what to do but never acknowledge when something was done well.
Improvement: Add a `## Feedback from Last Session` section to handoff packets when applicable. Include specific praise ("Your session summary format was exactly right — keep using that structure") alongside any corrections. Consider adding a `praise` field to `templates/validator-verdict.md` for the Validator to call out what went well, not just what failed.

### Guided question scripts for session consistency
Date: 2026-03-17
Context: Different agent sessions ask questions in different formats and at different points, making it harder to compare sessions or automate orchestration.
Improvement: Create structured question templates (e.g., "session-start checklist", "blocked-decision template", "scope-change request") with predefined answer formats. Agents would use these templates when they need input, ensuring consistent structure across sessions. This could live in `templates/` as `agent-questions.md` or be embedded in each role's preamble as a "when you need to ask" protocol. Benefits: easier to parse agent output programmatically, consistent decision records, and reduced ambiguity in handoff packets.
