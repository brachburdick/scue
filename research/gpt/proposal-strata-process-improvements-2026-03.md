# Proposal: Turning STRATA Deep-Research Findings into an Actionable Strata Process

**Status:** Proposal  
**Date:** 2026-03-26  
**Source document:** `/Users/brach/Downloads/deep-research-report STRATA.md`  
**Related SCUE docs:** `docs/strata-pipeline.md`, `specs/feat-arrangement-engine/proposal.md`, `sections/strata.md`

## Executive Summary

The deep-research STRATA document is useful, but right now it is a research template, not an operating process. It describes strong method patterns:

- ship strong baselines quickly
- pursue frontier models in parallel
- treat Pioneer and rekordbox metadata as a privileged signal
- evaluate with both MIR metrics and show-control metrics
- plan experiments at low, medium, and high resource levels
- enforce reproducibility

Strata already has a runtime tier model and a real analysis engine:

- `quick` for fast heuristic analysis
- `standard` for stem-based analysis
- `live` and `live_offline` for hardware-driven analysis
- `deep` as a planned future tier

What is missing is the process layer between "new Strata idea" and "production tier behavior". Today the codebase has a pipeline, but not yet a standard way to:

- frame a Strata item
- choose the right input sources
- define required ArrangementFormula outputs
- run baseline and frontier lanes side by side
- evaluate improvements consistently
- decide which tier an approach belongs in

This proposal introduces **Strata Process v1**: a lightweight, repeatable workflow for turning each Strata problem or experiment into a bounded item with explicit constraints, artifacts, evaluation gates, and ship criteria.

## What the Research Document Is Actually Telling Us

The strongest reusable findings in the report are process findings, not only model findings.

| Research finding | What it means for SCUE |
|---|---|
| Use a two-track methodology | Every Strata item should have a fast baseline lane and a frontier lane from day one |
| Use fusion-first design | Hardware metadata should be planned as a first-class input, not added late |
| Use a shared evaluation scaffold | We need one standard scorecard for structure, layers, stability, and latency |
| Plan low/medium/high resource variants | Experiments should be scoped before implementation, not after results disappoint |
| Treat phrase analysis as weak supervision | Pioneer labels are valuable, but must not silently become ground truth |
| Emphasize reproducibility | Item-level manifests, configs, and result logs need to be required artifacts |

The report also implies a critical cultural shift:

**Strata should stop treating research, implementation, and evaluation as separate ad hoc phases. They should be one item workflow.**

## Current Gaps in the Strata Process

Based on the current Strata docs and code:

1. The runtime tiers are clear, but the development workflow for new Strata items is not.
2. The code stores formulas per `(fingerprint, tier, source)`, but experiments do not yet have a matching artifact structure.
3. `quick`, `standard`, `live`, and `live_offline` have concrete runtime roles, but there is no formal promotion rubric for when an idea belongs in one tier versus another.
4. `deep` exists as a planned tier, but there is no standard research lane that proves when "deep" is worth implementing.
5. There is no required item brief that locks down allowed inputs, required ArrangementFormula fields, and failure tolerance before work starts.
6. There is no standard benchmark pack or regression pack for electronic structure, layer activity, and live DJ perturbations.
7. Hardware metadata is clearly strategic in the codebase, but there is no explicit policy separating trusted anchors, weak labels, and derived labels.
8. Success criteria are still too easy to describe only qualitatively, which makes tier decisions harder than they should be.

## Proposal: Strata Process v1

### 1. Every Strata Item Starts with an Item Brief

Every new Strata problem or experiment should begin with a brief stored under a `gpt` path, for example:

`research/gpt/strata-items/<item-id>/brief.md`

Required fields:

- official statement
- why the item matters to downstream show control
- allowed inputs
- disallowed shortcuts
- required ArrangementFormula fields
- target tier candidate (`quick`, `standard`, `live`, `live_offline`, or `deep`)
- latency budget
- stability requirements
- failure tolerance
- primary metrics
- go / iterate / pivot rule

This is the single biggest process improvement because it forces scope definition before implementation.

### 2. Every Item Must Have Two Lanes: Baseline and Frontier

The research report's "two-track methodology" should become mandatory.

| Lane | Purpose | Typical methods | Exit condition |
|---|---|---|---|
| Baseline lane | Prove the item is real and measurable quickly | MIR heuristics, beat-synchronous DSP, rule-based fusion, existing detectors | A measurable baseline exists and exposes real error modes |
| Frontier lane | Test whether a more advanced method meaningfully raises the ceiling | SSL embeddings, demix-assisted models, multi-task heads, long-context models | A candidate beats the baseline on the agreed scorecard |

Rules:

- No item starts with only a frontier plan.
- The baseline lane must finish first unless blocked by data availability.
- The frontier lane must justify extra compute with measurable gains, not intuition alone.

This keeps Strata from overcommitting to ML-heavy paths when a better heuristic or hardware-guided method would ship faster.

### 3. Add a Standard Input Fusion Plan

Each brief must explicitly classify inputs into four buckets:

| Bucket | Meaning | Examples |
|---|---|---|
| Trusted anchors | Timing or alignment signals we are willing to rely on | beat grid, beat number, playback position, tempo curve |
| Weak labels | Useful but noisy labels that can seed or constrain models | phrase analysis, cue points, waveform-derived hints |
| Derived labels | Labels computed by SCUE itself | sections, layer activity, transition types |
| Forbidden truth leakage | Signals we refuse to treat as gold truth for evaluation | raw Pioneer phrase labels used as final reference without review |

This is especially important for live and hardware-driven Strata work. The current codebase already treats hardware data as strategically valuable; the process should make that policy explicit.

### 4. Create One Shared Strata Scorecard

Every item should use the same scorecard structure, even if some fields are marked "not applicable".

Required metric groups:

- structure metrics
- layer metrics
- transition metrics
- stability metrics
- latency metrics
- human review notes

Suggested defaults:

| Metric group | Minimum required measures |
|---|---|
| Structure | boundary hit rate, label agreement, section-count sanity |
| Layers | F1 or mAP for active-layer detection, false-enter/false-exit count |
| Transitions | precision/recall for drop, breakdown, fill, layer enter/exit |
| Stability | boundary jitter, label flip rate, anti-flicker behavior |
| Latency | total analysis time, per-update latency for live paths |
| Human review | 5 to 10 representative tracks with notes on musical usefulness |

Important process rule:

**No Strata item is "better" unless it improves both research metrics and operational usefulness.**

That means we should stop relying on a single accuracy story when the downstream consumer is show control.

### 5. Define Tier Promotion Rules

The runtime tiers already exist. The process should define when a method belongs in each one.

| Tier | Process role | Promotion rule |
|---|---|---|
| `quick` | Default ship lane | Must be fast, interpretable, dependency-light, and stable enough for broad use |
| `standard` | Accuracy lane | Must materially beat quick on the scorecard and justify heavier compute |
| `live` | Performance lane | Must stay aligned under DJ operations and pass perturbation tests |
| `live_offline` | Replay/debug lane | Must reproduce live behavior from saved data closely enough for offline QA |
| `deep` | Research lane | Must prove repeatable value before it becomes a supported runtime tier |

Additional rules:

- `deep` should remain "research only" until it wins twice on the same scorecard against `standard`.
- `live` methods must pass a perturbation pack before shipping, even if offline accuracy looks excellent.
- `standard` should not absorb a method that only helps a narrow class of tracks unless that scope is declared.

This gives Strata a disciplined answer to "where does this idea belong?"

### 6. Require a Resource Plan Before Any Experiment Starts

The report's low/medium/high resource framing should become a mandatory planning table.

Every experiment should declare:

- low-resource version
- medium-resource version
- high-resource version
- data requirements
- compute requirements
- expected build time
- expected training time

This matters because Strata now spans heuristics, demixing, live hardware data, and future deep models. Without up-front resource scoping, the work will keep collapsing into "try the fanciest thing we can think of".

### 7. Add Reproducibility as a Required Deliverable

For each Strata item, require the following artifact set under a `gpt` path:

`research/gpt/strata-items/<item-id>/`

Recommended contents:

- `brief.md`
- `experiments.md`
- `dataset-manifest.md`
- `scorecard.md`
- `decision.md`

Minimum content rules:

- dataset IDs and split definitions are written down
- preprocessing choices are fixed
- config values are captured
- model and dependency versions are captured
- metrics are reported with date and run context
- known failure cases are logged with examples

This does not require a large new system. It only requires that experiment bookkeeping become part of the definition of done.

### 8. Add a Live Perturbation Pack

The report correctly emphasizes that live DJ audio is not the same problem as offline analysis. Strata needs a permanent perturbation pack for methods that claim to work in live or hardware-guided contexts.

Minimum perturbation scenarios:

- tempo shift
- loop engage/disengage
- cue jump or hot cue jump
- pitch change
- FX-altered audio with stable beat grid
- missing or delayed metadata

For live-facing work, this pack should be as important as benchmark accuracy.

### 9. Add a Gold Set for Electronic Music Structure

The report repeatedly points to ambiguity, long-tail labels, and electronic-specific structure. Strata needs a small internal gold set that reflects its real domain.

Recommended first pass:

- 15 to 25 tracks
- mixed energy profiles
- build, drop, breakdown, fakeout, and fill examples
- a subset with Pioneer metadata captures
- human-reviewed notes on section boundaries, active layers, and transition meaning

This can be small. The process win comes from making it canonical and reusing it for every item.

### 10. Require a Decision Note at the End of Each Item

Every Strata item should end with a short decision note:

- ship
- iterate
- pivot
- archive

Required justification:

- what won
- what lost
- what tier the result belongs in
- what evidence supported that call
- what follow-up work remains

This keeps the research log from turning into a pile of disconnected findings.

## Proposed Artifact Layout

I recommend the following structure for future Strata process work:

```text
research/gpt/
  proposal-strata-process-improvements-2026-03.md
  strata-items/
    <item-id>/
      brief.md
      experiments.md
      dataset-manifest.md
      scorecard.md
      decision.md
```

This stays compatible with the existing `research/gpt/` pattern and keeps all process artifacts under a `/gpt/` folder as requested.

## How This Fits the Current SCUE Strata Architecture

This proposal does not require a rewrite of the current engine.

It fits the current system because:

- `docs/strata-pipeline.md` already defines runtime stages and tuning knobs.
- `sections/strata.md` already defines ownership and invariants.
- the existing storage model already separates results by tier and source.
- the arrangement proposal already assumes multiple tiers and multiple consumers.

The missing piece is operational discipline around experiments and promotions.

In other words:

- the runtime pipeline is already ahead of the process
- this proposal brings the process up to the level of the codebase

## Immediate Adoption Plan

### Phase 1: Lightweight rollout this week

1. Adopt the item brief format for every new Strata problem or experiment.
2. Require baseline and frontier lanes in planning.
3. Create one shared scorecard template and use it even if some metrics are manual at first.
4. End each item with a one-page decision note.

### Phase 2: Evidence-building over the next 2 weeks

1. Assemble the first internal electronic-structure gold set.
2. Define the first live perturbation pack.
3. Backfill scorecards for the most active Strata items.
4. Decide what "deep tier" must prove before implementation work starts.

### Phase 3: Process hardening after 3 to 5 items

1. Review which metrics were genuinely useful.
2. Simplify the brief if it is too heavy.
3. Promote the scorecard and artifact rules into the default Strata workflow.
4. Decide whether any parts should become code-level helpers or CLI tooling.

## Recommended First Pilot Items

If we want to test this process immediately, the best pilot items are:

1. Electronic functional labels beyond generic section labels
2. Layer activity accuracy under stem bleed and dense mixes
3. Live alignment stability under tempo changes, loops, and Pioneer metadata gaps

These three cover the core Strata tension:

- offline structure
- arrangement/layer semantics
- live robustness

If the process works for those, it is probably good enough for the rest of the Strata backlog.

## Non-Goals

This proposal does not recommend:

- rewriting the current Strata engine first
- blocking heuristics until a deep model exists
- treating Pioneer phrase analysis as gold truth
- implementing the deep tier before a promotion rubric exists
- moving all current tuning knobs into config as part of this process work

Those may become good follow-ups, but they should not be prerequisites for improving the process.

## Bottom Line

The research document already contains the right strategic ideas. The real opportunity is to turn them into a repeatable operating model for Strata.

The highest-value changes are simple:

1. make every Strata item explicit
2. require baseline and frontier lanes
3. standardize input-fusion policy
4. evaluate with one shared scorecard
5. promote methods into tiers using clear rules
6. log decisions and artifacts under `research/gpt/`

That gives SCUE a Strata process that is fast enough for iterative engineering, rigorous enough for research, and grounded in the real constraints of live show control.
