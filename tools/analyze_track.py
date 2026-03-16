#!/usr/bin/env python3
"""CLI: analyze a single audio track and print the result.

Usage:
    python tools/analyze_track.py <path_to_audio> [--penalty FLOAT] [--json]

Output: section list printed to stdout, or full JSON with --json flag.
"""

import argparse
import json
import sys
from pathlib import Path

# Allow running from the project root without installing the package
sys.path.insert(0, str(Path(__file__).parent.parent))

from scue.layer1.analysis import run_analysis


def main():
    parser = argparse.ArgumentParser(description="Analyze an EDM track and print sections")
    parser.add_argument("audio_path", help="Path to WAV or MP3 file")
    parser.add_argument("--penalty", type=float, default=5.0,
                        help="Ruptures change-point penalty (lower = more sections, default 5.0)")
    parser.add_argument("--json", action="store_true",
                        help="Output full JSON result instead of formatted table")
    args = parser.parse_args()

    if not Path(args.audio_path).exists():
        print(f"Error: file not found: {args.audio_path}", file=sys.stderr)
        sys.exit(1)

    print(f"Analyzing {args.audio_path} ...", file=sys.stderr)
    result = run_analysis(args.audio_path, ruptures_penalty=args.penalty)

    if args.json:
        # Remove large waveform array from CLI output by default
        output = {k: v for k, v in result.items() if k not in ("waveform",)}
        print(json.dumps(output, indent=2))
    else:
        print(f"\nBPM: {result['bpm']:.1f}")
        print(f"Sections ({len(result['sections'])}):")
        print(f"  {'Label':<12} {'Start':>8} {'End':>8} {'Conf':>6}")
        print(f"  {'-'*12} {'-'*8} {'-'*8} {'-'*6}")
        for s in result["sections"]:
            dur = s["end"] - s["start"]
            print(f"  {s['label']:<12} {s['start']:>8.1f} {s['end']:>8.1f} {s['confidence']:>6.2f}  ({dur:.0f}s)")


if __name__ == "__main__":
    main()
