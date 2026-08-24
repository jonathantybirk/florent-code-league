# Round-one and early-game information

> **Measured before the Aug 4 turret patch (fcode ≤ 2.3.3).** Everything below was
> measured when turrets were stronger. The 2026-08-04 balance pass (fcode 2.3.4)
> changed the Gunner to 25 HP (was 40), 20 Ti (was 10), +20% cost scaling (was
> +10%), 7 damage (was 10) and 4 ammo per shot (was 2), and the Sentinel to 40 HP
> (was 30) on a 2-round reload (was 3). That balance pass is the only rules change
> in 2.3.4, so conclusions here that do not turn on turret strength still stand —
> but every turret-heavy number needs re-measuring before it is trusted again.

Analysis pass: 31 July 2026.

This note separates three categories that should not be confused:

1. facts guaranteed by the rules or exposed by the runtime API;
2. observations about the current 15-map competition pool; and
3. inferences that remain valid without hardcoding a map name.

The reproducible pool analysis is in
`scripts/analyze_initial_information.py`; raw results are under
`analysis/initial-information/`.

## What is known before a match

The submitted program can be written with knowledge of the published rules and
announced map pool. The official match documentation says the pool is announced
at the beginning of the competition and may be updated between rounds.

Rule-level facts include:

- the map is a rectangular grid between 8x8 and 30x30;
- terrain is `EMPTY`, `WALL`, or `ORE_TITANIUM`;
- maps are symmetric by reflection or rotation;
- each team begins with one immobile 2x2 Core;
- matches last at most 1,000 rounds;
- the Core has vision radius-squared 36;
- Builder vision radius-squared is 20;
- only Builders move freely; current engine probes confirm all eight adjacent
  directions are legal;
- the initial shared communication store contains sixteen zero values; and
- each unit has private persistent `Player` state rather than a shared Python
  object.

The code is not directly given a map name. The runtime API exposes map width
and height, but has no `get_map_name()` or seed getter.

Knowing the published pool externally is different from observing the current
map in-game. A bot may use a pool as a prior or template database if that is
permitted, but any such logic should verify the template against live
observations and fall back safely when it does not match.

## What the Core receives on round zero

On its first `run(ct)` call, the Core can read:

- map width and height;
- current round (`0`);
- its team;
- its reported top-left position and known 2x2 footprint;
- its HP, unit id, entity type, and vision radius;
- team titanium, current scale, and every current build cost;
- team unit count;
- every in-bounds tile in its vision, with exact terrain type;
- every visible entity/building and its public properties;
- all twelve candidate footprint-adjacent spawn tiles through `can_spawn()`;
  and
- the previous-round communication snapshot, initially all zero.

Engine probing confirms that Core vision is the union of radius-squared 36
circles around its four footprint tiles, clipped to map bounds. It is not a
circle around only the reported top-left coordinate. On the standard pool this
reveals 65–108 tiles, depending on map boundaries and Core placement.

The Core is *not* directly given:

- the map name;
- unseen terrain or ore;
- the actual symmetry transform;
- the enemy Core position unless it happens to be visible;
- enemy plans or shared-store state;
- an exact safe/uncontested classification for unseen ore; or
- paths through unseen terrain.

## Official map constraints versus pool observations

Only the rule-level constraints should be assumed for future maps.

| Property | Rule guarantee | Current 15-map pool observation |
|---|---|---|
| Dimensions | 8–30 on each axis | 10x10 through 28x20/26x26 |
| Shape | Rectangular | Rectangular |
| Symmetry | Reflection or rotation | 10 rotational-only, 3 y-mirror, 1 x-mirror, Runestone supports both rotation and x-mirror |
| Ore count | No documented fixed count | 6–22 |
| Wall count | No documented fixed count | 0–64 |
| Core spawn ring | Adjacent passable tiles | All 12 legal initially on every standard map |
| Visible ore from Core | No fixed minimum documented | 1–4 own-side deposits |
| Visible walls from Core | No fixed minimum documented | 0–12 |

It would be unsafe to encode “most maps are rotational,” “the spawn ring is
always fully open,” or a fixed ore count as game rules. These are current-pool
statistics only.

## Generic round-one deductions

### 1. Exact map boundaries and Core geometry

Width, height, and Core position give:

- distance to every map edge;
- whether the Core is near a corner, side, or neither;
- the complete legal coordinate range;
- which directions have the most unexplored space; and
- a deterministic coordinate system shared by every unit.

This is enough to divide the map into exploration sectors without identifying
the map.

### 2. Visible local terrain graph

The Core can classify every visible tile and construct a local graph of:

- passable tiles;
- walls and local corridors;
- ore locations;
- legal Harvester staging tiles;
- candidate first conveyor routes; and
- Builder spawn tiles that maximize immediate progress or new vision.

A route entirely inside known space can be treated as proven. A route entering
unknown space is only a hypothesis.

### 3. Symmetry mask and enemy-Core candidates

For a rectangular map, the generally relevant transforms in the current rules
are:

- 180-degree rotation;
- reflection across the vertical axis (`mirror_x`); and
- reflection across the horizontal axis (`mirror_y`).

Each maps the known own Core footprint to one candidate enemy footprint. A
candidate can be eliminated immediately if:

- it overlaps our Core;
- it lies in visible space and no enemy Core is there; or
- two visible terrain tiles that the transform pairs have different terrain.

Do not select rotational symmetry merely because it is common in the current
pool. Maintain a three-bit possibility mask until observations eliminate
alternatives.

Across the current maps, this map-agnostic round-one procedure produces:

- **one enemy-Core candidate:** Crossfire, Duel, Sprint;
- **two candidates:** Longship, Pinch, Runestone; and
- **three candidates:** the remaining nine maps.

These examples demonstrate the method; the code should operate on the mask,
not on these map names.

### 4. Conditional mirrored information

For every still-possible transform, visible terrain implies a *conditional*
counterpart:

```text
if symmetry == T, then terrain[T(position)] == terrain[position]
```

If all surviving transforms agree that a coordinate is wall, empty, or ore,
that fact is logically certain even before a unit visits it. If they disagree,
retain the alternatives rather than committing one guessed map.

The same consensus rule applies to the enemy-Core position. Runestone, for
example, supports two symmetry descriptions but both yield the same enemy Core
coordinate, so the location is certain even though the transform label is not.

### 5. Immediate economic opportunity

The Core can count visible ore and compute exact routes that remain inside the
observed region. It can also estimate whether one or more Builders have
nonduplicating immediate jobs.

It cannot yet prove that a visible deposit is globally “uncontested” unless all
surviving symmetry/terrain possibilities make it closer or safer for us. A
near-Core ore is a high-confidence economic target, but “near us” and
“uncontested under every possible unseen map” are different claims.

## Current-pool fingerprint result—and why not to hardcode it

In the present 15-map pool:

- twelve maps have unique dimensions;
- Quarry, Runestone, and Vault are all 24x24;
- dimensions plus own Core coordinate uniquely identify all fifteen; and
- the complete round-one terrain observation is unique from both team
  perspectives on every map.

Therefore a lookup table could identify the current map before spawning. That
is a pool-specific shortcut, not a general strategic inference. It could fail
as soon as a map is added, edited, or replaced.

If template matching is ever used, prefer a data-driven and defensive form:

1. compare dimensions and Core coordinate;
2. verify every currently visible terrain tile;
3. keep multiple templates if several still match;
4. use only facts on which every matching template agrees; and
5. discard template mode immediately on a contradiction.

Jonbot's core economy and exploration should still work with zero matching
templates.

## What becomes knowable in the early game

### Builder timing

Engine validation shows that a Builder spawned on round 0 first acts on round
1. A store write made by that Builder on round 1 becomes visible to the Core on
round 2 because communication writes are buffered.

Thus round 2 is the earliest centralized planner update containing active scout
information, although the Builder can react locally on round 1.

### Expanding observed terrain

Each moving Builder adds a radius-squared-20 observation around its current
tile. The team can progressively know:

- additional ore and walls;
- whether planned routes are actually connected;
- terrain contradictions that eliminate symmetry candidates;
- enemy infrastructure and Builder positions;
- local chokepoints and alternate paths; and
- whether a claimed ore remains available.

The knowledge map should distinguish at least:

```text
UNKNOWN / EMPTY / WALL / ORE / FRIENDLY_BUILDING / ENEMY_BUILDING
```

Unknown must not be silently treated as empty.

### Symmetry resolution

When a scout observes a tile whose terrain differs from the predicted value
under one candidate transformation, that candidate is eliminated. Scouts can
be directed toward coordinates where surviving candidates predict different
terrain, maximizing information gain rather than merely maximizing distance
from the Core.

Once only one enemy-Core coordinate remains—even if multiple equivalent
transform labels remain—attackers have a justified strategic target.

### Ore ownership and assignment

As terrain becomes known, Jonbot can improve from Euclidean guesses to:

- proven path distance through observed passable terrain;
- lower bounds through unknown terrain;
- likely enemy distance under every surviving symmetry;
- conveyor construction cost;
- expected time to first delivery;
- route exposure and chokepoints; and
- whether another Builder already owns a live claim.

“Safe ore” should therefore be a confidence level, not a permanent binary
label:

- **proven favorable:** closer under every surviving consistent world;
- **likely favorable:** closer under the best current estimates;
- **contested:** similar path/time for both sides; or
- **unknown:** insufficient terrain/symmetry information.

### General map classification

Without identifying a named map, early observations support continuous
features such as:

- area and aspect ratio;
- Core edge/corner distances;
- visible ore density;
- visible wall density;
- number and length of proven income routes;
- number of useful exploration frontiers;
- corridor width and local chokepoints;
- symmetry uncertainty; and
- estimated number of parallel economic tasks.

Builder count and strategy should depend on these features. For example, “four
known nonoverlapping economic jobs with long construction times” justifies more
Builders in a way that “this looks like Quarry” does not.

## Recommended round-zero/early protocol

### Core, round 0

1. Record dimensions, Core footprint, edge distances, resources, and costs.
2. Scan all visible terrain into a local knowledge map.
3. Initialize the three-bit symmetry mask and candidate enemy Core positions.
4. Eliminate candidates contradicted by visible terrain or occupancy.
5. Enumerate visible ore and proven local routes.
6. Create nonoverlapping exploration sectors/frontiers.
7. Spawn the first Builder at the tile best aligned with its assigned ore or
   information-gain frontier.
8. Publish compact strategy/assignment metadata for the following round.

### Builders, rounds 1+

1. Merge local observations into private persistent state.
2. Report discoveries through Builder-owned store slots.
3. Prefer assigned proven economic work when available.
4. Otherwise explore a distinct frontier, favoring symmetry-discriminating
   tiles and unseen coverage.
5. Claim ore with expiring leases before committing long travel.
6. Locally react to blocked paths and enemies without waiting for the Core.

### Core, rounds 2+

1. Read scout reports and update the global symmetry mask.
2. Resolve claims and reassign expired or completed tasks.
3. Spawn additional Builders only when reports expose enough parallel work or
   a distinct defensive/harassment requirement.
4. Shift from exploration toward economy, defense, or harassment as uncertainty
   falls and verified opportunities appear.

## Reproduction

```sh
uv run python scripts/analyze_initial_information.py
```

Outputs:

- `analysis/initial-information/round-one-observations.csv`
- `analysis/initial-information/round-one-observations.json`

Underscore-prefixed local fixture maps are intentionally excluded from the
standard-pool report.
