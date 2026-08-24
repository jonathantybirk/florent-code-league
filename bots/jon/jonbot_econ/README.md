# jonbot_econ

Timing-preserving mining fork of `brynhildr@533601b`.

The Core's spawning, role selection, economy trigger, miner count, defensive
priorities, and adaptive chain planner are unchanged. The only behavioral change
is how a miner vacates a planned build tile: it steps inward onto the completed
conveyor network when possible instead of taking the first arbitrary free
cardinal step. This removes the step-away/step-back oscillation without baking in
map-specific routes.

Evidence at the server's 10 ms TLE:

- exact 21-21 mirror against the parent over 21 maps;
- 93-33 against `spar_econ`, `brokkr`, and `steward` over the same 21 maps and
  both seats, exactly matching the parent opponent-by-opponent (30-12, 33-9,
  30-12);
- the rejected static ore partition scored 90-36 on that panel and is not in
  this fork;
- the earlier round-zero mining fork scored 6-19 in its first five online
  ladderfarm series and is superseded.

The helper `_step_inward` is intentionally small and local to the generic mining
executor. There are no terrain gates or opening overrides in this candidate.
