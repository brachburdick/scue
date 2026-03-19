# Protocol Improvement Proposals

> Project-specific observations for the next protocol review.
> Add entries here as you notice gaps, bugs, or ideas during sessions.
> These get promoted to the root protocol (or kept project-local) during review.
>
> **Last cleared:** 2026-03-19 (v1.6 protocol review)

---

<!-- Format: ### [Short title] -->
<!-- Date: YYYY-MM-DD -->
<!-- Context: What happened -->
<!-- Observation: What went wrong or could be better -->
<!-- Improvement: Proposed change -->

### Developer skipped session summary despite clear preamble instructions
**Date:** 2026-03-19
**Session:** 1.6.1 (FIX-STALE-DEVICES, feat-FE-BLT)
**Context:** Developer agent completed all acceptance criteria, passed validation and QA, but did not write a session summary. When prompted, the agent acknowledged the preamble instructions were "perfectly clear" (COMMON_RULES.md and DEVELOPER.md both state session summaries are non-negotiable). Summary was only written after operator intervention.
**Observation:** This is a recurrence of the v1.0 resolved BUG. The Validator Step 0 pre-check would have caught it downstream, but the Developer still didn't self-enforce. The SubagentStop hook fired `PreToolUse:Bash hook error` during recovery, suggesting the hook infrastructure may need review.
**Classification:** BUG (recurrence) — prompt-level rule failed; structural gate (hook) produced errors.
**Improvement:** (1) Investigate SubagentStop hook health — is it correctly blocking session completion when no summary exists? (2) Consider adding a redundant session summary reminder as the LAST line of the Developer preamble, not just in COMMON_RULES. (3) If this recurs after both fixes, the hook is the only reliable gate and prompt enforcement should be deprioritized.

---

<!-- Resolved 2026-03-19: 2 BLOCKERs + 2 OBSERVATIONs re: FE state-behavior gaps. -->
<!-- Changes applied to: COMMON_RULES.md §1, DEVELOPER.md (FE State Behavior Gate), -->
<!-- ORCHESTRATOR.md (FE State Behavior Check, Unresolved Operator Concerns, Designer -->
<!-- Invocation expansion, session checklist update), DESIGNER.md (UI State Behavior -->
<!-- Artifacts scope), templates/handoff-packet.md (State Behavior section), -->
<!-- templates/ui-state-behavior.md (new template). -->
