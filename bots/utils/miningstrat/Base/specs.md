# Mining strategy

## Purpose

`miningstrat` plans economic expansion from the team's current shared world
model. It decides which known titanium deposits are worth connecting, groups
accepted deposits into lanes, preserves already-built infrastructure, creates
bounded blind-exploration corridors, and assigns the resulting mining jobs to
the Builders currently available to mining.

The module is deliberately independent of a concrete bot. It consumes plain
domain objects and returns semantic plans/directives. The eventual integration
layer is responsible for translating `fcode` values and Global Communication
Store messages to and from these objects.

## In scope

- Selecting, deferring, and reconsidering known deposits.
- Comparing routes supplied by the pathfinding module.
- Grouping deposits into core-input lanes with configurable soft/hard capacity.
- Reusing existing lanes and committed construction.
- Planning bounded initial expansion before a deposit is known.
- Producing construction/exploration jobs.
- Deterministically assigning any number of available Builders to those jobs.
- Producing one immediately actionable directive for a calling Builder.
- Estimating activation rounds, construction spending, and planned Harvester
  flow for unfinished economic work.
- Reporting why a deposit was accepted or deferred, so policy is tunable from
  replay evidence rather than hidden in control flow.

## Explicitly out of scope

- Reading vision or constructing the shared map.
- Encoding, scheduling, or decoding GCS messages.
- Pathfinding and movement search.
- Inferring map symmetry or the enemy Core position.
- Detecting broken lanes or measuring expected/actual flow.
- Choosing which Builder an emergency, defence, rush, harassment, healing, or
  general-scouting module may take.
- Deciding what a Builder does after mining releases it.
- Executing `Controller` actions or checking `ct.can_*`.
- Combat planning, enemy-strategy classification, or global spending policy.
- Globally optimal Steiner-tree/TSP search.

The global role allocator supplies `available_for_mining=False` for Builders it
has taken. Mining reports per-Builder pre-emption costs but does not contest the
allocator's decision. A Builder with no mining job receives
`RELEASE_TO_GLOBAL_ASSIGNMENT`.

## Related modules

### Shared memory / internal map

The caller supplies the full team-known map: visible, revealed, and unrevealed
tiles; information age; observed or symmetry-inferred facts; buildings; and
deposit locations. `miningstrat` neither owns nor transmits this information.

### Pathfinding

The caller supplies a `PathOracle`. Its optimistic policy is assumed to treat:

- visible tiles as authoritative;
- revealed tiles as their last known state;
- unrevealed tiles as provisionally traversable until disproved.

Mining asks for routes and distance fields but never implements ordinary
obstacle search itself. Returned routes identify their unrevealed/stale content
so mining can penalize speculative commitment.

### Economy prediction

Viktor's operational expected flow is the flow of currently connected
Harvesters and is correctly zero while the first lanes are unfinished. Passive
income remains a separate schedule. Mining additionally returns *planned
future flow*: 2.5 Ti/round per planned Harvester beginning at its estimated
activation round. A global economy module may combine passive, operational,
actual, and planned values.

### Repair / maintenance

Repair is a separate future planner sharing the same world, lane, job, and
directive types. The previously agreed repair protocol is:

1. The flow monitor detects less-than-expected throughput at the outermost
   Core-visible conveyor.
2. The Core/GCS broadcasts that conveyor and all Harvesters believed to feed
   it, because a newly spawned repair Builder may not remember the old map.
3. The role allocator makes a Builder available for repair.
4. The repair planner reconstructs routes from at most four listed Harvesters
   to the known Core-visible endpoint.

This expansion planner does not detect or repair the failure.

## Public entry points

```python
planner = MiningPlanner(policy)

plan = planner.plan(context, previous_plan=None)
directive = planner.next_builder_directive(context, plan, builder_id)
```

Alternative strategies may replace individual planning stages without
forking the planner or changing these entry points:

```python
planner = MiningPlanner(
    policy,
    strategies=MiningStrategies(
        blind_expansion=my_opening,
        jobs=my_build_schedule,
    ),
)
```

`MiningStrategies` exposes hooks for deposit selection, lane layout, job/build
scheduling, blind expansion, and Builder assignment. Missing hooks use the
current deterministic implementation exactly. Epochs, semantic directives,
income projection, pre-emption reporting, and diagnostics remain shared, so a
strategy variant only owns the decision it replaces.

`plan` may be called by the Core or by any unit with the complete input. For
performance, integrations should globally replan only after a meaningful map,
roster, economy, or construction revision. Ordinary Builder turns should call
`next_builder_directive`, which is bounded by the assigned job and a small
route lookup.

## Required input

`MiningContext` contains:

### Call and revision state

- current round;
- monotonically increasing map revision;
- monotonically increasing roster revision;
- map dimensions;
- own Core footprint and candidate adjacent Core inputs.

### World state

- a `WorldTile` for every known or planning-relevant tile (missing tiles are
  treated as unrevealed by blind-expansion scoring);
- knowledge state: `UNREVEALED`, `REVEALED`, or `VISIBLE`;
- terrain: unknown, empty, wall, or titanium ore;
- optional building snapshot: owner relation, kind, direction, HP;
- last observation round and whether the fact was inferred;
- all known deposits and their current occupant.

### Geometry supplied by other modules

- optional enemy Core footprint;
- `PathOracle` implementing route/distance queries under the chosen knowledge
  policy, including any symmetry assumptions owned by that module.

### Existing economy

- existing lane snapshots and their Core inputs;
- connected Harvesters and conveyor tiles;
- operational expected flow and optional actual observed flow;
- current titanium, passive-income schedule, current construction costs, and
  global titanium reserve which mining must not spend.

### Builders and ownership

- Builder ID, deterministic spawn index, position, HP, current assignment;
- whether the global allocator currently makes it available to mining;

### Strategic constraints

- mining enabled/disabled;
- exact set of Builders available to mining;
- forbidden/reserved construction tiles;
- whether new expansion is allowed;
- maximum additional Builders mining may request;
- minimum titanium reserve controlled by the global strategy.

### Previous plan

The previous `MiningPlan` supplies the preceding epoch and assignments, which
provide assignment continuity. Lane and job IDs are deterministic from the
current world state. Existing construction comes from `world`/`existing_lanes`
and is never discarded merely because a Builder was reassigned.

## Configuration

All uncertain strategic choices are fields of immutable `MiningPolicy`:

- blind expansion mode and length by map size;
- number and overlap of candidate headings;
- deposit payoff horizon and acceptance threshold;
- route, construction, unrevealed, stale-information, enemy-side, and
  contention weights;
- bonus for an existing network or shared route;
- lane soft/hard capacities and overload penalty;
- core-side diversity bonus;
- assignment switching/pre-emption penalty;
- bounded candidate-deposit and candidate-heading counts.

The supported blind modes are:

- `SCOUT_THEN_BACKFILL`: no speculative conveyors before finding ore;
- `BUILD_CORE_STUBS`: reserve short Core inputs, then scout;
- `BUILD_CONFIDENT_CORRIDORS`: commit a bounded prefix of selected optimistic
  exploration routes.

No policy field is a hidden hard-coded map name or public-map lookup.

## Deposit selection

For each currently usable known deposit, mining asks the path oracle for the
best route to a candidate Core input. A configurable integer score includes:

```text
planned Harvester value over payoff horizon
- current Harvester/conveyor construction cost
- route-length cost
- unrevealed/stale route penalties
- contested/enemy-side penalty
- lane overload penalty
+ existing-network/shared-route bonus
+ territorial advantage bonus
```

Very near deposits may be accepted through `always_accept_distance`. Existing
friendly Harvesters remain accepted. Enemy-occupied deposits are not expansion
targets. Deferred deposits retain a reason and are reconsidered after relevant
revisions.

This intentionally models Bean's dominant distance frontier while allowing
more aggressive ph/HTTP-like policies through configuration.

## Lane grouping

Accepted deposits are processed in descending score, then deterministic tile
order. A deposit first considers compatible existing/planned lanes. Compatibility
uses:

- matching Core input;
- route overlap with the lane's current route;
- incremental route cost;
- current Harvester count;
- soft/hard capacity.

The soft capacity defaults to four but is not a hard invariant. Beyond it, an
overload penalty is paid; beyond hard capacity, a new lane is required.
Splitters are representable in inputs and outputs but are never inserted by the
initial planner unless a later policy explicitly enables them.

## Blind expansion

When accepted deposits do not occupy all mining Builders, the planner produces
bounded exploration corridors from viable Core inputs toward non-overlapping
unrevealed regions. A corridor contains:

- target region/heading;
- optimistic route;
- committed prefix allowed by the blind mode and length budget;
- speculative suffix which may be replaced after new visibility;
- assigned construction frontier.

The planner never commits beyond the configured blind budget and never builds
indefinitely merely because no deposit has appeared.

## Jobs and mixed Builder counts

The plan is expressed as independent jobs:

- build a Harvester;
- build/extend a lane route;
- explore a mining corridor.

Any number of Builders can be available. Jobs are greedily assigned by:

1. job priority and value;
2. Builder-to-job route cost;
3. assignment-switch penalty;
4. spawn index and entity ID.

If an emergency removes two Builders, their unfinished jobs remain in the
plan's unassigned pool. The remaining Builders are reassigned on the next
roster revision. Built tiles remain committed. If all Builders are removed,
the plan remains valid but inactive.

The Core should broadcast authoritative role changes with an assignment epoch
and effective round. GCS timing is outside this module; `plan.epoch` and each
directive's epoch allow the integration to reject stale work.

## Output to the Core

`MiningPlan` and its `CoreMiningDirective` report:

- desired total mining Builders and whether another Builder would be useful;
- active planned-lane and accepted-deposit counts;
- next expected spend and minimum reserve;
- operational and planned future flow;
- activation/spending schedule;
- assignments, jobs, deposit decisions, and construction routes;
- per-Builder pre-emption status.

The request to spawn is advisory. Mining never spawns, spends, converts ammo,
or overrules the global strategy.

## Output to a Builder

`BuilderDirective` contains:

- plan/assignment epoch;
- job and lane ID;
- objective;
- exactly one primary semantic action;
- optional fallback;
- completion/replan reason.

Action types are `MOVE`, `BUILD_CONVEYOR`, `BUILD_HARVESTER`, `WAIT`,
`REPORT_COMPLETE`, and `RELEASE_TO_GLOBAL_ASSIGNMENT`. The integration validates
the action through `ct.can_*` and performs it. An invalid directive causes a
map revision/replan; mining never calls the Controller.

## Performance contract

The game allows 10 ms CPU per unit turn on maps of at most 30x30 (900 tiles).

- Full planning is event/revision-driven, not repeated by every Builder every
  ordinary round.
- Core/enemy distance fields and route queries are supplied/cached by the path
  module.
- Candidate deposits/headings are bounded by policy.
- Lane construction is greedy with bounded local comparisons; no exponential
  subset search is performed.
- Ordinary directive lookup inspects only the assigned job and its route.

The implementation exposes no unbounded search and uses deterministic ordering
throughout, making replay comparisons reproducible.

## Diagnostics

`MiningPolicy.verbosity` controls structured diagnostics:

- `0`: no diagnostic events;
- `1`: planning lifecycle, warnings, and soft-capacity events;
- `2`: every deposit score, lane choice, job creation, assignment, corridor,
  and Builder action.

Planning events are retained in `MiningPlan.debug_events`, sent to the optional
`debug_sink`, and emitted through Python logging at `DEBUG`. Per-turn Builder
action events occur after the immutable plan exists, so they go to the sink and
logger rather than being appended to the old plan. Each event has a stable
event name plus structured data suitable for replay traces.

## Implementation layout

- `model.py`: dependency-free enums, immutable snapshots, protocols, plans,
  and directives.
- `strategies.py`: optional stage hooks for alternative opening/economy
  strategies.
- `planner.py`: deterministic deposit, lane, corridor, job, assignment, and
  next-action logic.
- `__init__.py`: the public import surface.

The package deliberately has no `fcode`, Controller, GCS, combat, repair, or
concrete pathfinding dependency. The future bot integration should adapt those
systems to `MiningContext` and translate returned semantic actions.
