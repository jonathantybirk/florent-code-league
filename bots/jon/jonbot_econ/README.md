# jonbot_econ

Timing-preserving mining fork of ladderfarm's actual flagship,
`brynhildr@2f83111` (submission v109).

The Core's spawning, role selection, economy trigger, miner count, defensive
priorities, and adaptive chain planner are unchanged. The only behavioral change
is how a miner vacates a planned build tile: it steps inward onto the completed
conveyor network when possible instead of taking the first arbitrary free
cardinal step. This removes the step-away/step-back oscillation without baking in
map-specific routes.

Evidence at the server's 10 ms TLE:

- the file differs from `2f83111` only in `_step_inward` and the module name;
- 90-36 against `spar_econ`, `brokkr`, and `steward` over 21 maps and both
  seats (30-12 against each);
- the rejected static ore partition scored 90-36 on that panel and is not in
  this fork;
- the earlier round-zero mining fork scored 6-19 in its first five online
  ladderfarm series and is superseded.
- the mistakenly v116-based timing fork scored 3-22 in its first online round;
  v116 was a challenger, not the farm-selected flagship, and is superseded.

The helper `_step_inward` is intentionally small and local to the generic mining
executor. There are no terrain gates or opening overrides in this candidate.
