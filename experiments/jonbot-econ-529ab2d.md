# jonbot_econ@529ab2d

Timing-preserving mining fork of ladderfarm's selected flagship,
`brynhildr@2f83111` (v109). A source diff against that exact commit contains
only the `_step_inward` mining primitive and the module name: Core spawning,
economy timing, miner count, combat, and defensive doctrine are unchanged.

The miner now vacates a future conveyor or Harvester tile through the completed
inward belt when possible instead of choosing the first arbitrary cardinal step.
This is the general fix for step-away/step-back movement without static routes.

Local evidence at 10 ms TLE:

- 90-36 against `spar_econ`, `brokkr`, and `steward` over 21 maps and both
  seats, 30-12 against each;
- exact source lineage verified against `2f83111`;
- ore-first expansion and a smaller Harvester reserve were separately tested
  and rejected at 90-36 and 18-24 in their paired panels.

This corrects the parent-selection error in `3c3a0d4`, whose v116 lineage scored
3-22 online and was never the ladderfarm flagship.

## First online round and relay ablations

Submission v119 scored 3-22 in its first five-series round: OpenSverige 5-0,
Torsko 5-0, 0033 5-0, I Stone 3-2, and gsxWins 4-1. The same five-opponent
slice also crushed the v116 lineage; v119 remains unpromoted pending broader
coverage.

Construction traces show one-miner chains already advancing near the
one-build/one-move limit. Three multi-miner variants were tested against the
same 90-36 baseline and rejected:

- static deposit partition on the v116 lineage: 90-36 versus 93-33;
- dynamic deposit reservations: 86-40;
- explicit disjoint relay chunks: 85-41.

The result supports the existing natural relay: miners converge, observe newly
built tiles, skip them, and continue adapting after damage or a new belt join.
Forcing either separate lanes or fixed chunks weakened it. A role-aware spawn
placement branch was also removed after all-map replay comparison found zero
changed spawn or activation timelines.
