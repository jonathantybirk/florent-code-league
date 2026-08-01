#!/bin/sh
# Deterministic opponents nobody else is editing. Codex owns undertow and
# jonbot and edits them live -- a measurement against a moving target is
# worthless, so they are informational only and never decide a change.
for o in lucas/strat1 lucas/claude_challenger_1 lucas/claude_challenger_2 \
         lucas/claude_challenger_3 jon/probes/v233_a jon/probes/v233_e; do
  printf "  vs %-28s " "$o"
  uv run python scratch/arena.py "$1" "$o" 2>&1 | head -1
done
