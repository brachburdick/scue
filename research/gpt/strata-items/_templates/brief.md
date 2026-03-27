# Strata Item Brief: [ITEM-ID] — [Title]

**Status:** Draft | Active | Complete | Archived
**Date:** YYYY-MM-DD
**Author:**
**Target tier:** quick | standard | live | live_offline | deep

## Problem Statement

What arrangement analysis problem does this item address? Why does it matter to downstream show control?

## Allowed Inputs

| Bucket | Inputs | Notes |
|--------|--------|-------|
| Trusted anchors | (e.g., beat grid, beat number, tempo curve) | |
| Weak labels | (e.g., phrase analysis, cue points, waveform hints) | |
| Derived labels | (e.g., SCUE sections, layer activity) | |
| Forbidden truth leakage | (e.g., raw Pioneer phrases as gold reference) | |

## Disallowed Shortcuts

What approaches are explicitly out of scope or forbidden?

## Required ArrangementFormula Fields

Which fields in the output must be populated? (sections, transitions, patterns, stems, etc.)

## Latency Budget

- Quick: < ___s
- Standard: < ___s
- Live: < ___ms per update

## Stability Requirements

- Max boundary jitter: ___ beats
- Max label flip rate: ___/min
- Must pass perturbation suite: yes | no

## Failure Tolerance

What is acceptable degradation when inputs are missing or noisy?

## Primary Metrics

List the scorecard metrics this item is evaluated against.

## Baseline Lane

| Aspect | Detail |
|--------|--------|
| Method | |
| Expected timeline | |
| Exit condition | A measurable baseline exists and exposes real error modes |

## Frontier Lane

| Aspect | Detail |
|--------|--------|
| Method | |
| Expected timeline | |
| Exit condition | Candidate beats baseline on agreed scorecard |

## Resource Plan

| Level | Approach | Data needs | Compute needs | Timeline |
|-------|----------|------------|---------------|----------|
| Low | | | | |
| Medium | | | | |
| High | | | | |

## Go / Iterate / Pivot Rule

- **Go:** [criteria to ship]
- **Iterate:** [criteria to continue with adjustments]
- **Pivot:** [criteria to change approach fundamentally]
