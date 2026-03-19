#!/bin/bash
# SCUE Multi-Agent Workflow Setup
# Run from project root: bash setup-agent-workflow.sh

set -e

echo "=== SCUE Agent Workflow Setup ==="

# --- Directory structure ---
echo "Creating directories..."
mkdir -p docs/agents
mkdir -p specs
mkdir -p sessions
mkdir -p reviews
mkdir -p research

# --- Place workflow docs ---
# (Assumes you've saved the files from the orchestrator session)
# If the files are already in your project, adjust paths accordingly.

echo ""
echo "Directory structure created:"
echo "  docs/agents/     — Workflow docs (prompts, roster, contracts, transition plan)"
echo "  specs/           — Feature specs, plans, and task breakdowns"
echo "  sessions/        — Agent session summaries"
echo "  reviews/         — Review reports"
echo "  research/        — Research findings"
echo ""
echo "Next steps:"
echo "  1. Save these files into docs/agents/:"
echo "       ORCHESTRATOR_PROMPT.md"
echo "       AGENT_PREAMBLE.md"
echo "       AGENT_ROSTER.md"
echo "       HANDOFF_CONTRACTS.md"
echo "       TRANSITION_PLAN.md"
echo ""
echo "  2. Add the following to your root CLAUDE.md under a new section:"
echo ""
echo '     ## Agent Workflow'
echo '     Multi-agent workflow docs: `docs/agents/`'
echo '     Agent roster & scope definitions: `docs/agents/AGENT_ROSTER.md`'
echo '     Handoff format contracts: `docs/agents/HANDOFF_CONTRACTS.md`'
echo '     Session summaries: `sessions/`'
echo '     Feature specs & task breakdowns: `specs/`'
echo ""
echo "  3. Create per-layer CLAUDE.md files (context anchors for agents):"

# --- Create stub CLAUDE.md files for layers that don't have them yet ---
# Layer 2 and Layer 3 already have CLAUDE.md in the architecture doc's tree

for dir in "scue/bridge" "scue/layer1" "scue/api" "scue/network"; do
    if [ ! -f "$dir/CLAUDE.md" ]; then
        echo "     Creating stub: $dir/CLAUDE.md"
        mkdir -p "$dir"
        cat > "$dir/CLAUDE.md" << 'STUB'
# [Layer Name] — Agent Context

> This file provides domain-specific context for agents working in this directory.
> It supplements the root CLAUDE.md with layer-specific conventions, gotchas, and scope.

## Scope
<!-- What this directory contains and what agents working here should know -->

## Key Files
<!-- List the important files and their purposes -->

## Conventions
<!-- Layer-specific coding patterns, naming conventions, etc. -->

## Known Issues
<!-- Current bugs or quirks specific to this layer -->

## Testing
<!-- How to run tests for this layer, what test patterns to follow -->
STUB
    else
        echo "     Exists: $dir/CLAUDE.md (skipping)"
    fi
done

echo ""
echo "=== Setup complete ==="
echo ""
echo "Run the Architect session next to populate specs/ with agent-ready task breakdowns."
