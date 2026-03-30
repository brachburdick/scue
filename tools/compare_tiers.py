#!/usr/bin/env python3
"""Compare Strata tier outputs for a given track.

Runs quick, live_offline, and hybrid tiers (where data permits) and
prints a side-by-side comparison of sections, patterns, transitions,
and energy narratives.

Usage:
    python tools/compare_tiers.py <fingerprint>
    python tools/compare_tiers.py --list          # list tracks with strata data
    python tools/compare_tiers.py --scan           # find tracks with both analysis + Pioneer data
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Project root
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scue.layer1.strata.models import ArrangementFormula, formula_from_dict
from scue.layer1.strata.storage import StrataStore


def find_eligible_tracks(tracks_dir: Path) -> list[dict]:
    """Find tracks that have both TrackAnalysis and Pioneer sidecar data."""
    eligible = []
    if not tracks_dir.exists():
        return eligible

    for fp_dir in sorted(tracks_dir.iterdir()):
        if not fp_dir.is_dir():
            continue
        fp = fp_dir.name
        has_analysis = any(fp_dir.glob("v*.json")) or (fp_dir / "analysis.json").exists()
        has_pioneer = (fp_dir / "live_pioneer.json").exists()

        if has_analysis:
            # Find audio path from latest analysis
            audio_path = None
            for vfile in sorted(fp_dir.glob("v*.json"), reverse=True):
                try:
                    data = json.loads(vfile.read_text())
                    audio_path = data.get("audio_path", "")
                    break
                except (json.JSONDecodeError, KeyError):
                    continue

            eligible.append({
                "fingerprint": fp,
                "has_analysis": has_analysis,
                "has_pioneer": has_pioneer,
                "audio_path": audio_path or "?",
                "can_hybrid": has_analysis and has_pioneer,
            })

    return eligible


def print_formula_summary(name: str, formula: ArrangementFormula) -> None:
    """Print a concise summary of an ArrangementFormula."""
    print(f"\n{'=' * 60}")
    print(f"  {name}")
    print(f"  tier={formula.pipeline_tier}  source={formula.analysis_source}")
    print(f"  compute_time={formula.compute_time_seconds:.2f}s")
    print(f"{'=' * 60}")

    print(f"\n  Sections ({len(formula.sections)}):")
    for s in formula.sections:
        layers = ", ".join(s.active_layers) if s.active_layers else "none"
        patterns = len(s.active_patterns)
        trans = len(s.transitions)
        print(f"    {s.section_label:12s}  {s.section_start:6.1f}s – {s.section_end:6.1f}s  "
              f"E={s.energy_level:.2f} ({s.energy_trend:8s})  "
              f"layers=[{layers}]  patterns={patterns}  transitions={trans}")

    if formula.patterns:
        print(f"\n  Patterns ({len(formula.patterns)}):")
        for p in formula.patterns:
            instances = len(p.instances)
            print(f"    {p.name:30s}  type={p.pattern_type}  instances={instances}  stem={p.stem}")

    if formula.transitions:
        print(f"\n  Transitions ({len(formula.transitions)}):")
        for t in formula.transitions:
            print(f"    {t.timestamp:6.1f}s  {t.type:20s}  "
                  f"delta={t.energy_delta:+.2f}  {t.description}")

    if formula.stems:
        print(f"\n  Stems ({len(formula.stems)}):")
        for st in formula.stems:
            spans = len(st.activity) if st.activity else 0
            print(f"    {st.stem_type:10s}  activity_spans={spans}")

    print(f"\n  Narrative: {formula.energy_narrative[:120]}...")
    print(f"  Complexity: {formula.arrangement_complexity:.3f}")


def run_comparison(fingerprint: str, tracks_dir: Path, strata_dir: Path) -> None:
    """Run all available tiers and compare."""
    from scue.layer1.strata.engine import StrataEngine

    store = StrataStore(strata_dir)
    engine = StrataEngine(tracks_dir=tracks_dir, strata_store=store)

    results: dict[str, ArrangementFormula] = {}

    # Try quick tier
    try:
        results["quick"] = engine.analyze_quick(fingerprint)
    except Exception as e:
        print(f"  [quick] FAILED: {e}")

    # Try live_offline tier
    try:
        results["live_offline"] = engine.analyze_live_offline(fingerprint)
    except Exception as e:
        print(f"  [live_offline] SKIPPED: {e}")

    # Try hybrid tier
    try:
        results["hybrid"] = engine.analyze_hybrid(fingerprint)
    except Exception as e:
        print(f"  [hybrid] SKIPPED: {e}")

    if not results:
        print("No tiers could be run. Check that analysis data exists.")
        return

    for name, formula in results.items():
        print_formula_summary(name.upper(), formula)

    # Print comparison table
    if len(results) > 1:
        print(f"\n{'=' * 60}")
        print("  COMPARISON SUMMARY")
        print(f"{'=' * 60}")
        header = f"  {'Metric':<25s}"
        for name in results:
            header += f"  {name:>12s}"
        print(header)
        print("  " + "-" * (25 + 14 * len(results)))

        metrics = [
            ("Sections", lambda f: len(f.sections)),
            ("Patterns", lambda f: len(f.patterns)),
            ("Transitions", lambda f: len(f.transitions)),
            ("Stems", lambda f: len(f.stems)),
            ("Complexity", lambda f: f"{f.arrangement_complexity:.3f}"),
            ("Compute time", lambda f: f"{f.compute_time_seconds:.2f}s"),
        ]
        for label, fn in metrics:
            row = f"  {label:<25s}"
            for name in results:
                val = fn(results[name])
                row += f"  {str(val):>12s}"
            print(row)


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare Strata tier outputs")
    parser.add_argument("fingerprint", nargs="?", help="Track fingerprint to analyze")
    parser.add_argument("--list", action="store_true", help="List tracks with strata data")
    parser.add_argument("--scan", action="store_true", help="Find tracks eligible for hybrid")
    parser.add_argument("--tracks-dir", type=Path, default=ROOT / "tracks",
                        help="Tracks directory (default: tracks/)")
    parser.add_argument("--strata-dir", type=Path, default=ROOT / "strata",
                        help="Strata output directory (default: strata/)")
    args = parser.parse_args()

    if args.scan:
        tracks = find_eligible_tracks(args.tracks_dir)
        if not tracks:
            print("No tracks found in", args.tracks_dir)
            return
        print(f"Found {len(tracks)} tracks:")
        for t in tracks:
            hybrid = "HYBRID-READY" if t["can_hybrid"] else "audio-only"
            name = Path(t["audio_path"]).stem if t["audio_path"] != "?" else "?"
            print(f"  {t['fingerprint'][:16]}  {hybrid:14s}  {name}")
        return

    if args.list:
        store = StrataStore(args.strata_dir)
        tracks = store.list_tracks()
        if not tracks:
            print("No strata data found in", args.strata_dir)
            return
        for t in tracks:
            tiers = ", ".join(f"{k}({','.join(v)})" for k, v in t["tiers"].items())
            print(f"  {t['fingerprint'][:16]}  {tiers}")
        return

    if not args.fingerprint:
        parser.print_help()
        return

    run_comparison(args.fingerprint, args.tracks_dir, args.strata_dir)


if __name__ == "__main__":
    main()
