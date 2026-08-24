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
