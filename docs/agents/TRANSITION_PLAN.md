# SCUE Transition Plan — What to Do Right Now

> This document tells you exactly how to transition from your current 3-agent workflow
> to the new multi-agent architecture. Follow in order.

---

## Step 0: Create the Directory Structure

Run this in your SCUE project root:

```bash
mkdir -p specs sessions reviews research
```

Your project should now have:
```
scue-project/
├── docs/                    # (exists) Architecture, contracts, decisions, milestones
├── specs/                   # (new) Spec-driven development artifacts per feature
├── sessions/                # (new) Agent session summaries
├── reviews/                 # (new) Review reports  
├── research/                # (new) Research findings
├── ORCHESTRATOR_HANDOFF.md  # (exists) Your project summary — already done!
├── CLAUDE.md                # (exists) Project conventions
├── LEARNINGS.md             # (exists) Known pitfalls
└── ... (source code)
```

---

## Step 1: Save the Workflow Documents

Place these files from this session into your project:

| File | Save To |
|---|---|
| `ORCHESTRATOR_PROMPT.md` | `docs/agents/ORCHESTRATOR_PROMPT.md` |
| `AGENT_ROSTER.md` | `docs/agents/AGENT_ROSTER.md` |
| `HANDOFF_CONTRACTS.md` | `docs/agents/HANDOFF_CONTRACTS.md` |
| This file | `docs/agents/TRANSITION_PLAN.md` |

Add a pointer in your root `CLAUDE.md`:
```markdown
## Agent Workflow
For multi-agent workflow documentation, see `docs/agents/`.
```

---

## Step 2: Bug Triage Before New Work

Before starting Milestone 3 (Cue Generation), you should triage the existing bugs.
Based on your handoff document, here's the recommended priority:

### Priority 1: Bridge Device Discovery Bug
**Why first:** Layer 2 (cue generation) needs to be testable against live input. If the bridge can't discover devices, you can't run end-to-end tests with your XDJ-AZ. The workaround (raw status packets) works but limits what you can test.

**Agent to deploy:** Bridge (L0)
**Estimated scope:** Medium — likely a listener registration issue or XDJ-AZ-specific announcement packet handling

### Priority 2: Data/Schema Bugs  
**Why second:** If the data layer has integrity issues, cue generation will build on a shaky foundation.

**Agent to deploy:** Analysis (L1A) for data bugs, API agent for schema/validation bugs

### Priority 3: Frontend State Bugs
**Why third:** These are important but don't block Layer 2 development.

**Agent to deploy:** FE-State agent

### Priority 4: Traffic Indicator Flicker
**Why last:** Visual annoyance only, workaround in place.

---

## Step 3: Your First Orchestrator Session

Start a new conversation. Paste the **entire** `ORCHESTRATOR_PROMPT.md` as your first message.

Then send:

```
Here's the current project state:

[Paste ORCHESTRATOR_HANDOFF.md]

Current status:
- All previously completed work is stable
- ~110 backend tests passing
- Known bugs: [list which ones you've noticed most recently]
- I want to start transitioning to the multi-agent workflow described in docs/agents/
- Immediate priority: [your choice — bug triage first, or jump to M3 cue generation]

Questions I want your help with:
1. Given the bug situation, should I fix bugs first or start Layer 2?
2. For whatever we do first, generate the handoff packet for the first agent session.
```

The Orchestrator will then:
- Assess the situation
- Ask you clarifying questions about your priorities
- Generate the first handoff packet
- Tell you which agent to spin up and what to paste into it

---

## Step 4: Running an Implementation Session

When the Orchestrator gives you a handoff packet, here's the protocol:

1. **Start a new conversation.** Never reuse an existing one.
2. **First message:** Paste the handoff packet, then add:
   ```
   You are the [Agent Role] for SCUE. Your scope and constraints are defined above.
   
   Before starting, confirm:
   1. You understand the objective
   2. You understand what files you can and cannot modify
   3. You have questions about anything ambiguous
   
   Do NOT proceed with implementation until I confirm your understanding is correct.
   If anything in the spec or constraints is unclear, ask me NOW rather than assuming.
   ```
3. **Review the agent's understanding.** Correct any misunderstandings.
4. **Let it work.** The agent implements the task.
5. **Before closing:** Ask the agent to produce its session summary in the format from `HANDOFF_CONTRACTS.md`.
6. **Save the summary** to `sessions/[date]-[agent]-[task-slug].md`.

---

## Step 5: After Each Implementation Session

1. **Read the session summary yourself.** Check the "Decisions Made" and "Questions for Brach" sections.
2. **Update `LEARNINGS.md`** with any new pitfalls from the "LEARNINGS.md Candidates" section.
3. **Go back to the Orchestrator.** Paste the session summary and ask what's next.
4. **If the Orchestrator recommends a review:** Start a Reviewer session with the spec + session summary.

---

## The Communication Efficiency Guarantee

This workflow minimizes redundant reading because:

| Problem | How It's Solved |
|---|---|
| Re-reading entire project docs each session | Each agent gets only its scoped context slice via the handoff packet |
| Agent reads code outside its scope | Scope boundaries in the handoff explicitly list what's in and out |
| Context rot from long sessions | Each task is atomized to <30 min. Fresh agent per task. |
| Next agent doesn't know what previous agent did | Session summaries are structured artifacts, not conversation dumps |
| Agent infers instead of asking | Handoff includes "Open Questions for Brach" section. Agent system prompt says "ask, don't assume." |
| Orchestrator loses track of state | Session summaries feed back to Orchestrator. Milestone tracker stays current. |

---

## Maintaining the System

### After each milestone:
- Update `ORCHESTRATOR_HANDOFF.md` with new completion status
- Archive completed specs: `specs/[feature-slug]/` stays but tasks are all checked off
- Reviewer produces a milestone review report

### After each agent session:
- Save the session summary (non-negotiable)
- Update `docs/MILESTONES.md` task status
- Feed the summary back to the Orchestrator

### Weekly (or every ~10 sessions):
- Review `LEARNINGS.md` — prune anything that's been fixed
- Review `CONTRACTS.md` — ensure it reflects actual code
- Ask the Orchestrator for a status assessment

---

## Quick Reference: Agent Deployment Cheat Sheet

| I want to... | Deploy this agent | Feed it... |
|---|---|---|
| Investigate a technology choice | Researcher | Question + DECISIONS.md |
| Design a new feature's architecture | Architect | Research output + CONTRACTS.md + DECISIONS.md |
| Fix a bridge/protocol bug | Bridge (L0) | Bug report + CONTRACTS.md §L0 |
| Fix analysis pipeline issues | Analysis (L1A) | Bug report + ADR-008, ADR-010 |
| Fix real-time tracking issues | Tracking (L1B) | Bug report + ADR-006 |
| Build new cue generation logic | Cue Gen (L2) | Spec + plan + tasks from Architect |
| Fix/add API endpoints | API | Contract types + FE types |
| Fix store/data flow bugs | FE-State | Bug report + contract types |
| Build/fix UI pages | FE-UI | Design spec + component patterns |
| Design a new page's UX | UI/UX Designer | Data shapes + user goals |
| Review completed work | Reviewer | Spec + session summary + code diff |
| Figure out what to do next | Orchestrator | Latest session summaries + milestone status |
