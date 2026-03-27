# Strata Item Brief: 001 — Live Section Stability

**Status:** Draft
**Date:** 2026-03-26
**Author:** Brach / Claude
**Target tier:** live, live_offline

## Problem Statement

When Pioneer phrase analysis and beat-grid data are present but imperfect (tempo changes, loops, cue jumps, delayed metadata), the live Strata tier can produce unstable section labels — boundaries shift, labels flip between frames, and transitions appear/disappear. This undermines downstream show control, which needs stable arrangement context to drive lighting cues.

The goal is to measure and improve section stability under realistic DJ operations, using the evaluation harness and perturbation suites built in Phases 1-4.

## Allowed Inputs

| Bucket | Inputs | Notes |
|--------|--------|-------|
| Trusted anchors | Beat grid (Tier A only), beat number, tempo curve | Grid must pass trust scoring |
| Weak labels | Pioneer phrase analysis, cue points, waveform-derived hints | Pioneer labels are seeds, not ground truth |
| Derived labels | SCUE section labels from quick/standard tiers | For comparison only |
| Forbidden truth leakage | Raw Pioneer phrases used as gold reference without review | Must use human-reviewed gold set |

## Disallowed Shortcuts

- No treating Pioneer phrase labels as ground truth for evaluation
- No hardcoding section sequences (must work with arbitrary arrangements)
- No ignoring perturbation suite results to ship faster

## Required ArrangementFormula Fields

- `sections` (with stable `section_label`, `energy_level`, `energy_trend`)
- `transitions` (with correct `type`, stable `timestamp`)
- `grid_trust` (must be populated)

## Latency Budget

- Live: < 100ms per update
- Live_offline: < 500ms total

## Stability Requirements

- Max boundary jitter: 2 beats
- Max label flip rate: 0.1 per minute
- Max transition false positive rate: 1.0 per minute
- Must pass DEFAULT_GRID_PACK perturbation suite
- Must pass DEFAULT_LIVE_PACK perturbation suite

## Failure Tolerance

- Tier B grid: method should degrade gracefully (wider boundaries OK, no hallucinated structure)
- Tier C grid: method should fall back to energy-only analysis, not produce confident wrong labels
- Missing metadata: at least first phrase must anchor the analysis

## Primary Metrics

- `stability.boundary_jitter_beats`
- `stability.label_flip_rate`
- `stability.transition_false_positives_per_minute`
- `structure.boundary_hit_rate` (must not regress vs current live tier)
- `grid.grid_trust_tier`

## Baseline Lane

| Aspect | Detail |
|--------|--------|
| Method | Current LiveStrataAnalyzer as-is (direct Pioneer phrase → section mapping) |
| Expected timeline | 1 session to establish baseline scorecard on gold set |
| Exit condition | Baseline scorecard exists, error modes documented |

## Frontier Lane

| Aspect | Detail |
|--------|--------|
| Method | LiveStrataAnalyzer + grid trust gating + temporal smoothing (hysteresis on label changes) |
| Expected timeline | 2-3 sessions |
| Exit condition | Candidate beats baseline on stability metrics without regressing boundary_hit_rate |

## Resource Plan

| Level | Approach | Data needs | Compute needs | Timeline |
|-------|----------|------------|---------------|----------|
| Low | Add hysteresis (min 2 consecutive frames to change label) | 5 tracks with Pioneer data | None (heuristic) | 1 session |
| Medium | Grid-trust-gated priors (soft constraints from EDMPriors when grid is Tier A/B) | 10 tracks with Pioneer data | None | 2 sessions |
| High | Temporal HMM smoothing on section labels | 15+ tracks, training data | Moderate (HMM fitting) | 4+ sessions |

## Go / Iterate / Pivot Rule

- **Go:** Frontier beats baseline on all 5 primary metrics, passes both perturbation packs
- **Iterate:** Frontier improves stability but regresses boundary_hit_rate — tune tolerance thresholds
- **Pivot:** Temporal smoothing does not help — investigate whether Pioneer phrase data quality is the bottleneck, not the method
