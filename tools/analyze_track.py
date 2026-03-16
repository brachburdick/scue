#!/usr/bin/env python3
"""CLI tool for analyzing a single audio track.

Usage:
    python tools/analyze_track.py <audio_path> [options]

Options:
    --penalty FLOAT     Ruptures penalty (default: 5.0, lower = more sections)
    --skip-waveform     Skip RGB waveform computation
    --force             Re-analyze even if analysis exists
    --json              Output raw JSON instead of formatted table
    --tracks-dir PATH   Directory for JSON storage (default: tracks/)
    --cache-path PATH   SQLite cache path (default: cache/scue.db)
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from scue.layer1.analysis import run_analysis
from scue.layer1.models import analysis_to_dict


def main() -> None:
    """Run track analysis from the command line."""
    parser = argparse.ArgumentParser(description="Analyze an audio track")
    parser.add_argument("audio_path", help="Path to the audio file")
    parser.add_argument("--penalty", type=float, default=5.0,
                        help="Ruptures penalty (lower = more sections)")
    parser.add_argument("--skip-waveform", action="store_true",
                        help="Skip RGB waveform computation")
    parser.add_argument("--force", action="store_true",
                        help="Re-analyze even if analysis exists")
    parser.add_argument("--json", action="store_true",
                        help="Output raw JSON")
    parser.add_argument("--tracks-dir", default="tracks",
                        help="JSON storage directory")
    parser.add_argument("--cache-path", default="cache/scue.db",
                        help="SQLite cache path")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Verbose logging")
    args = parser.parse_args()

    # Configure logging
    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    audio_path = Path(args.audio_path)
    if not audio_path.exists():
        print(f"Error: File not found: {audio_path}", file=sys.stderr)
        sys.exit(1)

    analysis = run_analysis(
        audio_path=audio_path,
        tracks_dir=args.tracks_dir,
        cache_path=args.cache_path,
        ruptures_penalty=args.penalty,
        skip_waveform=args.skip_waveform,
        force=args.force,
    )

    if args.json:
        data = analysis_to_dict(analysis)
        # Exclude waveform from JSON output (too large)
        data.pop("waveform", None)
        print(json.dumps(data, indent=2))
    else:
        _print_summary(analysis)


def _print_summary(analysis) -> None:
    """Print a formatted summary of the analysis."""
    print(f"\n{'=' * 60}")
    print(f"Track:       {analysis.title}")
    print(f"Fingerprint: {analysis.fingerprint[:16]}...")
    print(f"BPM:         {analysis.bpm:.1f}")
    print(f"Duration:    {analysis.duration:.1f}s ({analysis.duration / 60:.1f}m)")
    print(f"Sections:    {len(analysis.sections)}")
    print(f"Beats:       {len(analysis.beats)}")
    print(f"Downbeats:   {len(analysis.downbeats)}")
    print(f"{'=' * 60}")

    print(f"\n{'Section':<12} {'Start':>8} {'End':>8} {'Bars':>5} {'Exp':>5} {'Conf':>6} {'Flags'}")
    print(f"{'-' * 12} {'-' * 8} {'-' * 8} {'-' * 5} {'-' * 5} {'-' * 6} {'-' * 20}")

    for s in analysis.sections:
        flags = []
        if s.irregular_phrase:
            flags.append("IRREGULAR")
        if s.fakeout:
            flags.append("FAKEOUT")
        flag_str = ", ".join(flags) if flags else ""

        print(
            f"{s.label:<12} {s.start:>7.1f}s {s.end:>7.1f}s "
            f"{s.bar_count:>5} {s.expected_bar_count:>5} "
            f"{s.confidence:>5.2f} {flag_str}"
        )

    print()


if __name__ == "__main__":
    main()
