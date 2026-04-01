#!/usr/bin/env bash
# Renders all .puml files in docs/diagrams/ to .svg using a PlantUML server.
#
# Usage:
#   bash scripts/render-diagrams.sh
#
# Override server (e.g. local Docker):
#   PLANTUML_SERVER=http://localhost:8080 bash scripts/render-diagrams.sh
#
# Local server setup:
#   docker run -d -p 8080:8080 plantuml/plantuml-server:jetty

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
DIAGRAM_DIR="$PROJECT_ROOT/docs/diagrams"
SERVER="${PLANTUML_SERVER:-https://www.plantuml.com/plantuml}"

if ! command -v node &>/dev/null; then
  echo "Error: node not found. Install Node.js." >&2
  exit 1
fi

# Encode PlantUML source to URL-safe string using the npm package
encode_puml() {
  node -e "
    const encoder = require('$PROJECT_ROOT/frontend/node_modules/plantuml-encoder');
    const fs = require('fs');
    const src = fs.readFileSync('$1', 'utf8');
    process.stdout.write(encoder.encode(src));
  "
}

count=0
for f in "$DIAGRAM_DIR"/*.puml; do
  [ -f "$f" ] || continue
  encoded=$(encode_puml "$f")
  out="${f%.puml}.svg"
  curl -sf "${SERVER}/svg/${encoded}" -o "$out"
  echo "  rendered: $(basename "$out")"
  count=$((count + 1))
done

if [ "$count" -eq 0 ]; then
  echo "No .puml files found in $DIAGRAM_DIR"
else
  echo "Done: $count diagram(s) rendered to $DIAGRAM_DIR"
fi
