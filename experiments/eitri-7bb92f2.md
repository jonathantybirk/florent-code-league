# eitri@7bb92f2

Successor to the corrected lifecycle build `eitri@557b395`. It keeps the
shared completed-lane state and adds one generic contention rule: when a build
target has no building but cannot be entered, another bot occupies it. After
three failed placements the Builder at the construction stand yields one tile,
letting the occupant leave. Empty targets (including insufficient-resource
waits) never trigger the yield.

This fixes Bridge's permanent two-builder lock: one Builder stood on deposit
`(2,1)` while another retried the Harvester from `(2,2)` for the remaining 941
rounds. Bridge rises from 9,500 to 14,140 Ti, 66% to 98% of its perfect plan.

Full 53-map do-nothing comparison with the original Eitri:

- total titanium: 1,506,850 versus 1,469,620 (+37,230);
- executor ratio: 94% versus 91%;
- nine maps improve, zero regress;
- Sweden +12,960, Icefloe +6,210, Bridge +4,640, Royale +4,200,
  Longhouse +3,120, Fjordgate +2,410, Longship +1,970, Bifrost +1,080,
  and String +640.

The all-atlas 1-4-builder assignment test and focused mining tests pass 15/15.
The planner remains 85% of the capacity-aware terrain ceiling, so this is a
strict executor improvement, not a claim of overall optimality.
