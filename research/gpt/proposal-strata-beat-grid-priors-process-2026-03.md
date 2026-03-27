# Proposal: Turning STRATA Augment Findings into Actionable Strata Process Improvements

**Status:** Proposal  
**Date:** 2026-03-26  
**Source document:** `/Users/brach/Downloads/deep-research-report STRATA augment.md`  
**Related SCUE docs:** `research/gpt/proposal-strata-process-improvements-2026-03.md`, `docs/strata-pipeline.md`, `docs/DECISIONS.md`, `scue/layer1/strata/live_analyzer.py`

## Executive Summary

The STRATA augment report makes a narrower and more actionable argument than the first STRATA research document:

- make time musical
- trust beat grids, but only after validation
- encode EDM-specific musical knowledge explicitly
- fuse priors and learned signals in beat/bar space
- evaluate not just accuracy, but stability under live conditions

SCUE is already partially set up for this:

- `quick` and `standard` already consume beat/downbeat-aligned analysis
- `pioneer_reanalyzed` already re-runs analysis using Pioneer beat grids
- `live` already builds Strata from Pioneer phrase analysis + beat grid + waveform

So the missing piece is not "add beat-grid data." The missing piece is a **process** for deciding:

- when a beat grid is trusted enough to constrain inference
- which EDM priors are explicit, soft, or hard
- how seconds-space and beat-space approaches are compared
- how grid failure modes are tested before promotion into a Strata tier

This proposal extends the earlier Strata Process v1 with a **Musical Time and Priors layer**. The main recommendation is:

**Treat beat-grid fusion and explicit musical priors as a governed Strata capability, not an ad hoc modeling trick.**

## What This Report Changes

The first STRATA proposal focused on general process discipline. The augment report adds a more specific operating model.

| Augment finding | Process implication for Strata |
|---|---|
| Beat/bar coordinates are the right control space for EDM | Every relevant Strata item should explicitly choose seconds-space vs beat-space, and justify that choice |
| Correct beat grids have huge leverage but can be wrong | Beat-grid trust scoring must become a required checkpoint |
| EDM priors improve labels and stability | Priors must be declared, versioned, and tested rather than buried inside heuristics |
| Structured decoding is a good fit | Strata needs a standard "emissions + constraints" experiment lane |
| Stability matters as much as labeling | Jitter, flip-rate, and false-positive metrics must become first-class |

## Current Strata State

The codebase already contains the raw ingredients:

- `docs/strata-pipeline.md` shows `quick` and `standard` operate over bars/downbeats.
- ADR-020 already formalizes reanalysis with Pioneer beat grids.
- ADR-021 already formalizes the `live` tier from Pioneer phrase analysis and beat grid.
- `live_analyzer.py` already maps Pioneer beat-grid and phrase data into a live ArrangementFormula.

What is still missing:

1. No explicit beat-grid trust model.
2. No item-level declaration of meter assumptions, grid source, or fallback behavior.
3. No shared registry of EDM priors, section grammars, or duration priors.
4. No required beat-space ablation against seconds-space baselines.
5. No standard grid-error sensitivity tests before shipping a beat-grid-dependent method.
6. No process distinction between "grid used for alignment", "grid used as soft prior", and "grid used as hard decoding constraint".

## Proposal: Strata Process v1.1 — Musical Time and Priors

### 1. Add a Musical Time Contract to Every Strata Item

Every new Strata item should add a required artifact:

`research/gpt/strata-items/<item-id>/musical-time.md`

Required fields:

- target coordinate system: `seconds`, `beats`, `bars`, or hybrid
- expected meter assumptions
- beat-grid source priority
- acceptable fallback behavior when no reliable grid exists
- whether downbeats are required or only beat spacing
- whether the grid is used for alignment, soft priors, or hard constraints
- latency/stability impact of grid dependence

This turns "we used the beat grid" into a precise engineering decision.

### 2. Add Beat-Grid Trust Scoring as a Required Stage

Before any Strata method uses a beat grid as a hard constraint, it must pass a trust stage.

Recommended trust tiers:

| Tier | Meaning | Allowed usage |
|---|---|---|
| A | Cross-validated and musically plausible | Hard constraints allowed |
| B | Present but not fully validated | Soft priors only |
| C | Estimated fallback or conflicting sources | Alignment aid only; no hard constraints |

Required checks:

- source agreement across available inputs (`network`, `ANLZ`, `XML`, `audio-estimated`)
- downbeat plausibility
- drift detection over track duration
- half/double-tempo suspicion
- phrase/bar-length plausibility for EDM-like material

This should become the first gate in any beat-grid-dependent experiment.

### 3. Create a Priors Specification for Each Item

Every item that claims to use "musical knowledge" should declare it explicitly in:

`research/gpt/strata-items/<item-id>/priors.md`

Required sections:

- subgenre scope
- section taxonomy
- duration priors
- sequence/grammar priors
- pattern priors
- layer priors
- whether each prior is hard, soft, or diagnostic-only

Examples of priors this report points toward:

- 4/8/16/32-bar duration expectations
- intro → build → drop style ordering
- build signatures like snare acceleration and kick dropout
- drop signatures like bass and kick reintroduction
- layer expectations such as drum/bass suppression in breakdown-like spans

The process win here is auditability. We should be able to answer "which musical assumptions drove this result?" without reverse-engineering code.

### 4. Make Beat-Space Ablations Mandatory

The augment report strongly implies that beat-space modeling is powerful, but only if we can prove it.

Every relevant item should run these minimum comparisons:

1. seconds-space baseline
2. beat-synchronous baseline
3. beat-synchronous + priors
4. beat-synchronous + priors + structured decoding, if applicable

This avoids the common failure mode where beat-space complexity gets adopted because it feels musically correct, not because it wins on evidence.

### 5. Add a Standard "Emissions + Constraints" Experiment Lane

The report points repeatedly toward constrained decoding. Strata should treat this as a standard experiment family, not an exotic research branch.

Recommended lane definitions:

| Lane | Description | Typical fit |
|---|---|---|
| L0 | Heuristics only in beat/bar space | Fast baselines, quick tier candidates |
| L1 | Learned emissions only | Accuracy baselines, standard tier candidates |
| L2 | Learned emissions + soft prior features | Medium-resource fusion experiments |
| L3 | Learned emissions + constrained decoding | Stability-focused candidates for standard/live |

This gives each item a repeatable path from simple to structured methods.

### 6. Extend the Shared Scorecard with Musical-Time Metrics

The earlier process proposal added a general scorecard. This augment proposal should refine it.

Add these required fields whenever beat/bar modeling is in scope:

- boundary jitter in beats
- boundary off-grid rate
- label flip-rate per minute
- transition false positives per minute
- grid-source confidence
- outcome sensitivity to grid corruption

These metrics should sit alongside:

- HR.5F / HR3F or equivalent structure metrics
- label accuracy
- layer F1 / mAP
- latency

This is how we stop rewarding methods that look smart offline but flicker in performance mode.

### 7. Add a Grid Error Sensitivity Suite

Before promotion into `standard`, `live`, or `deep`, any beat-grid-dependent method should be tested against deliberately degraded grids.

Minimum scenarios:

- downbeat shifted by 1 beat
- half-tempo interpretation
- double-tempo interpretation
- gradual drift
- sparse missing grid regions
- conflicting source inputs

Expected outcome:

- trusted-grid methods should degrade gracefully
- hard-constraint methods should fail loudly, not silently hallucinate stable but wrong structure

This should become part of the same perturbation culture already needed for live DJ operations.

### 8. Add a Taxonomy and Subgenre Declaration Step

The report is very clear that EDM-specific taxonomies outperform pop-centric assumptions. That means every Strata item should declare:

- target subgenre(s)
- section vocabulary
- event vocabulary
- layer vocabulary
- whether the method is EDM-specialized or intended to generalize

Without this step, priors will keep drifting between generic pop assumptions and EDM-specific expectations without anyone noticing.

### 9. Add a Priors Promotion Rule for Runtime Tiers

Not every prior belongs in every tier.

| Tier | Priors policy |
|---|---|
| `quick` | Only cheap, interpretable priors with predictable failure modes |
| `standard` | May use richer priors, structured decoding, and stem-informed rules |
| `live` | Only priors that are robust to incomplete data and validated beat grids |
| `live_offline` | Should mirror live behavior closely for replay/debug |
| `deep` | Can test richer neural fusion, but cannot skip trust scoring or ablation rules |

This is important because priors are attractive precisely where the failure modes can be subtle.

### 10. Add Explicit Artifact Slots for Beat-Grid and Priors Work

To make this process real, extend the earlier artifact layout:

```text
research/gpt/strata-items/
  <item-id>/
    brief.md
    musical-time.md
    priors.md
    experiments.md
    grid-validation.md
    scorecard.md
    decision.md
```

New artifact purposes:

- `musical-time.md`: time-base and grid policy
- `priors.md`: declared domain knowledge and how it is used
- `grid-validation.md`: trust score, source comparisons, and failure notes

## Recommended Process Changes to Current Strata Work

These are the concrete changes I would make to the Strata workflow right now.

### Change 1: Add a Beat-Grid Gate Before Reanalysis-Led Work

Current state:

- `pioneer_reanalyzed` exists
- `live` depends on Pioneer beat-grid data

Recommended process change:

- no item may claim beat-grid advantage until it logs grid trust and source provenance
- reanalysis comparisons should always record which grid source was used and whether it was validated

### Change 2: Stop Treating EDM Priors as Implicit Heuristics

Current state:

- some Strata behavior already bakes in EDM assumptions through section labels, drum patterns, and transition rules

Recommended process change:

- any new rule about build, drop, breakdown, kick dropout, snare roll, or duration expectation must be documented in `priors.md`
- each rule must be tagged as hard, soft, or diagnostic

### Change 3: Require Beat-Space vs Seconds-Space Evidence for New Methods

Current state:

- Strata already uses beat/downbeat-aware analysis, but not every improvement is explicitly justified against a seconds-based alternative

Recommended process change:

- every new method in this family must show whether beat-space actually helped
- if beat-space does not materially improve accuracy or stability, do not pay the complexity cost

### Change 4: Add Structured Decoding as a Named Option, Not a Hidden Implementation Detail

Current state:

- the augment report strongly recommends HSMM/CRF/Viterbi-style decoding for stable section inference

Recommended process change:

- treat "emissions + constraints" as a named design choice in experiment plans
- require explicit comparison against unconstrained decoding

### Change 5: Make Stability the Tie-Breaker for Live-Facing Work

Current state:

- the live tier already exists, but process-level evaluation still leans too hard on structure correctness alone

Recommended process change:

- for any live or live-adjacent item, stability metrics outrank small gains in offline label accuracy
- if a method improves HR.5F but worsens flicker, it should not be promoted to live-facing tiers

## Suggested Pilot Roadmap

### P0: Beat-Grid Governance

Goal:

- define source priority, trust tiers, and validation checklist

Deliverables under `research/gpt/`:

- `musical-time.md` template
- `grid-validation.md` template
- one pilot item filled out against existing Pioneer reanalysis data

### P1: Beat-Space Ablation

Goal:

- prove how much beat-synchronous modeling actually helps current Strata outputs

Questions to answer:

- does beat-space reduce boundary jitter?
- does it reduce flip-rate?
- does it improve build/drop precision?

### P2: Explicit EDM Priors in the Process

Goal:

- turn the current informal EDM assumptions into declared priors

Deliverables:

- first priors catalog for Strata section and transition logic
- classification of priors into hard / soft / diagnostic-only

### P3: Constrained Decoding Trial

Goal:

- test whether structured inference gives enough stability to justify the added complexity

Success rule:

- it must beat unconstrained decoding on both structure quality and stability

## Best Candidate Pilot Items

The strongest first pilots for this process extension are:

1. Build-up / drop boundary precision
2. Kick/bass dropout and re-entry interpretation across sections
3. Live section stability when Pioneer phrase analysis and beat-grid data are present but imperfect

These map cleanly onto the augment report's core thesis and onto Strata's existing architecture.

## Non-Goals

This proposal does not require:

- rewriting the current Strata engine immediately
- implementing HSMM/CRF now just because the paper trail says they are promising
- assuming every track should be treated as EDM
- promoting beat-grid constraints into runtime tiers before trust scoring exists

The first win is process clarity, not model maximalism.

## Bottom Line

The STRATA augment report is telling us to stop treating musical time and musical knowledge as informal background intuition.

For Strata, that becomes a process change:

1. declare the time base
2. validate the grid
3. declare the priors
4. compare beat-space against seconds-space
5. measure stability explicitly
6. only then promote the method into a runtime tier

That would turn the augment report from a strong research direction into a practical operating model for Strata development, while keeping all artifacts under `research/gpt/` as requested.
