# Economic harassment

## Purpose

`harassment` coordinates Builders which the global role allocator has already
assigned to economic harassment.  Its first implemented tactic mimics Bean's
observable `destroy -> occupy with barrier` sequence: select a valuable enemy
economic tile, approach it, destroy it, and deny immediate repair.

The package is independent of `fcode`, the Controller, GCS encoding, and a
concrete pathfinder.  Callers adapt those systems into immutable inputs and
execute the returned semantic directive.

## Implemented scope

- Represent the known enemy economy as a directed flow graph.
- Calculate the production disconnected by removing a candidate tile.
- Value denied flow, replacement cost, confidence, completion time, and one
  bounded nearby follow-up.
- Select a reachable adjacent staging tile through a supplied `PathOracle`.
- Deterministically assign any number of available harassment Builders.
- Re-score after every assignment so two jobs do not both claim the same
  marginal flow.
- Execute a stateless `approach -> verify/destroy -> block -> complete` action.
- Produce structured, verbosity-controlled diagnostics.

## Explicitly out of scope

- Deciding whether to harass, how many Builders to allocate, or when to attack.
- Taking Builders from mining, defence, repair, or healing.
- Reading vision, reconciling stale map facts, or communicating over GCS.
- Inferring conveyor/splitter flow direction from engine entities.  The caller
  supplies explicit `output_tiles`.
- Ordinary pathfinding or generic danger avoidance.
- Core containment, weapon construction, launcher construction/use, defender
  combat, and idle behaviour.
- Executing actions, checking `ct.can_*`, or choosing global spending policy.

These omissions are intentional extension boundaries, not hidden fallbacks.

## Input

`HarassmentContext` supplies:

- round plus map and roster revisions;
- dimensions;
- Builders already assigned/available to harassment;
- `enemy_economy`: explicit `EnemyEconomyNode`s with output edges, current or
  estimated HP, production rate, and confidence;
- enemy Core input/sink tiles;
- current tile occupants;
- visible/revealed state and which facts are inferred;
- tiles on which a barrier can currently be built;
- forbidden tiles and whether barrier spending is allowed;
- a `PathOracle` returning routes and ETA to exact staging tiles.

The graph should contain all known links needed to trace a Harvester to a Core
input. Missing or uncertain links remain the caller's map-estimation problem.
Confidence permits the planner to discount a node without pretending it is
certain.

## Target value

For each candidate, the planner removes it from the graph and finds Harvesters
which were connected before removal but not afterward:

```text
immediate value = confidence * (
    disrupted flow * denial horizon * flow weight
    + replacement cost * replacement weight
)

completion time = route ETA + attacks required + barrier action

score = (immediate value + discounted nearby follow-up) / completion time
```

The follow-up is bounded to one target within `followup_radius`. Its disrupted
flow is calculated after the first target is already removed, preventing the
same disconnected Harvesters from being counted twice. This is a small local
look-ahead, not TSP or unrestricted search.

After assigning one Builder, its target is removed from the graph for the next
assignment. The remaining Builders therefore receive marginally useful work.

## Builder directives

`next_builder_directive` returns exactly one of:

- `MOVE`: next route tile toward the staging tile;
- `ATTACK`: destroy the currently visible enemy economic target;
- `BUILD_BARRIER`: occupy the now visibly empty target tile;
- `WAIT`: barrier spending is temporarily disallowed;
- `REPORT_COMPLETE`: our barrier now occupies the target;
- `REQUEST_REPLAN`: observations or reachability invalidated the job;
- `RELEASE_TO_GLOBAL_ASSIGNMENT`: no active harassment assignment.

The integration validates and executes the directive. A failed engine action
must update the map/revision and replan; the module does not call Controller.

## Performance

The map is at most 900 tiles. Candidate count is bounded by policy (default
32), follow-up depth is exactly one, graph reachability is iterative and
cycle-safe, and assignment is deterministic. Full planning should run on the
Core after a meaningful revision. Ordinary Builder turns call only
`next_builder_directive`.

## Extension seams

- `block_core` should be a separate action because it values spawn, movement,
  and lane denial rather than only economic flow.
- Launcher walking/flight/setup choices should later be alternative approach
  options returned with ETA. Launcher eviction is a separate local combat
  action.
- Forward weapon opportunities can be reported to the global attack planner;
  this package must not silently convert harassment into a full attack.

