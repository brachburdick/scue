#!/usr/bin/env python3
"""CLI: 2D venue preview — visualize fixture output without real hardware.

Renders the abstract Layer 3 output as a colored 2D grid in the browser,
showing each fixture as a colored square at its configured position.
Essential for development and for users who want to preview before connecting hardware.

Usage:
    python tools/venue_preview.py [--venue config/venues/default.yaml]
    # Then open http://localhost:8001 in your browser

Status: STUB — not yet implemented (Milestone 4).
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def main():
    parser = argparse.ArgumentParser(description="2D venue preview server")
    parser.add_argument("--venue", default="config/venues/default.yaml",
                        help="Path to venue YAML file")
    parser.add_argument("--port", type=int, default=8001,
                        help="Port for preview server (default 8001)")
    args = parser.parse_args()

    print(f"venue_preview: not yet implemented — see Milestone 4")
    print(f"Would load: {args.venue}")
    print(f"Would serve preview at: http://localhost:{args.port}")

    # TODO(milestone-4): implement
    # 1. Load venue config
    # 2. Start a FastAPI server on args.port with a canvas-based preview page
    # 3. Connect to the running SCUE server via WebSocket
    # 4. Render each FixtureOutput as a colored square at the fixture's position


if __name__ == "__main__":
    main()
