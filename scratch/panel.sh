#!/bin/sh
# Deterministic opponents nobody else is editing, plus the version archives.
# Codex owns undertow and jonbot and edits them live, so a live run can be
# contaminated mid-flight; uw_v1/uw_v2 are frozen copies of those builds.
for o in lucas/strat1 lucas/claude_challenger_1 lucas/claude_challenger_2 \
         lucas/claude_challenger_3 jon/versions/probes/v233_a \
         jon/versions/probes/v233_e jon/versions/probes/v233_h \
         jon/versions/probes/uw_v1 jon/versions/probes/uw_v2; do
  printf "  vs %-24s " "$o"
  uv run python scratch/arena.py "$1" "$o" 2>&1 | head -1
done
