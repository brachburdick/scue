# Handoff Packet: RESEARCH-WAVEFORM-TRACKID

---
status: APPROVED
project_root: /Users/brach/Documents/THE_FACTORY/projects/DjTools/scue
revision_of: none
supersedes: none
superseded_by: none
---

## Dispatch
- Mode: ORCHESTRATOR DISPATCH
- Output path: `research/findings-waveform-trackid.md`
- Parallel wave: none

## Objective
Answer 7 specific research questions about Pioneer waveform data sources, track ID reliability on DLP hardware, and data flow architecture direction for SCUE's frontend screens.

## Role
Researcher

## Working Directory
- Run from: `/Users/brach/Documents/THE_FACTORY/projects/DjTools/scue`
- Related feature/milestone: FE-Live-Deck-Monitor, FE-Analysis-Viewer

## Scope Boundary
- Files this agent MAY read:
  - `AGENT_BOOTSTRAP.md`
  - `preambles/RESEARCHER.md`, `preambles/COMMON_RULES.md`
  - `LEARNINGS.md`
  - `research/request-waveform-trackid.md` — the research request with all 7 questions
  - `research/dlp-track-id-reliability.md` — existing research (if present)
  - `docs/ARCHITECTURE.md`
  - `docs/FUTURE_AUDIO_FINGERPRINTING (1).md`
  - `scue/bridge/messages.py`
  - `scue/layer1/usb_scanner.py`
  - `scue/layer1/storage.py`
  - `specs/feat-FE-live-deck-monitor/spec.md`
  - `templates/research-findings.md` — output template
- Files this agent must NOT touch:
  - Any code files (Researcher is read-only)
  - Any spec files
  - `docs/CONTRACTS.md`, `docs/interfaces.md`

## Context Files
- `AGENT_BOOTSTRAP.md` — read first
- `research/request-waveform-trackid.md` — the full research request with 7 questions, context, and "what a good answer looks like"
- `LEARNINGS.md` — known issues with beat-link, rbox, DLP hardware

## Interface Contracts
- None. Research is read-only.

## Required Output
- Write: `research/findings-waveform-trackid.md` (using `templates/research-findings.md` format)
- Write: session summary at `research/session-researcher-waveform-trackid.md`

## Constraints
- Use web search to find beat-link source code, Pioneer ANLZ documentation, pyrekordbox documentation, and Chromaprint/AcoustID documentation.
- Cite sources for every factual claim.
- Clearly label confidence levels: confirmed (tested/documented), likely (strong evidence), speculative (inference).
- Do NOT make architectural recommendations — present tradeoffs and let the Architect decide.
- Do NOT modify any code.

## Acceptance Criteria
- [ ] All 7 questions from `research/request-waveform-trackid.md` are answered
- [ ] Each answer includes source citation and confidence level
- [ ] Waveform format details are specific enough to evaluate parsing feasibility
- [ ] Track ID failure modes are documented with concrete scenarios
- [ ] Data flow tradeoffs are presented neutrally (not prescriptive)
- [ ] Session summary written per template
- [ ] Zero code changes

## Dependencies
- Requires completion of: none
- Blocks: Architect review of findings → possible ADRs or spec revisions

## Open Questions
- none
