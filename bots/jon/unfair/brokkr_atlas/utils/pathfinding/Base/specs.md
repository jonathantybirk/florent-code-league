# Pathfinding

Ported from `bots/luc/steward_reinforced/builder.py` at `555c3ce`
("one pathfinder, one launch protocol"). `pathfinding.py` is the implementation;
`tests/test_pathfinding.py` the headless tests
(`.venv/bin/python -m pytest tests/test_pathfinding.py`).

## Why one search
The steward Builder had four BFS variants and they disagreed about whether a
Launcher hop counts as a step. A goal that is far when *choosing* and near when
*moving* keeps winning and losing, so the Builder was ferried back and forth.
Everything here is a thin view over a single `travel()`; target selection and
movement cannot disagree because they are the same computation.

## Safety is graph membership, not cost
Firing lines (`Terrain.threat`) and enemy Launcher pickup rings
(`Terrain.launcher_hazards`) are simply absent from the graph. Pricing them
instead of forbidding them, while another rule forbids them, is a livelock
(builder 66, rounds 43–end). `allow_fire=True` re-admits threat tiles for the
one caller (`safe_path`) that decides whether a walk through fire is survivable.

## API
| call | returns | use |
|---|---|---|
| `Terrain(width, height, blocked, threat, launcher_hazards, friendly_launchers, landing_blocked)` | per-turn board model | build once per turn from what the bot tracks |
| `travel(t, source, goals=None, hops, allow_fire, extra_blocked)` | `(dist, came_from)` | the BFS everything else wraps |
| `path(t, source, target, exact, ...)` | `[source, …, goal]` or `None` | full route; `exact=False` stops on any of the 8 tiles around `target` |
| `first_step(t, source, target, ...)` | next tile or `None` | non-adjacent result ⇒ route begins with a Launcher hop |
| `safe_path(t, source, target, exact, hops, survives)` | `(route, blocked_by_fire)` | clean route, else survivable route through fire, else refuse |
| `distance(t, source, goals)` | steps or `None` | nearest of a goal set |
| `distance_map(t, source)` | `{tile: steps}` | full flood for scoring candidates |
| `keeps_route_open(t, spot, source, target, exact, baseline)` | bool | "can we build here without walling ourselves in" |

Hops: a friendly Launcher adds edges from each tile of its 8-tile pickup ring to
every tile within range² 26 that is inside the map, not in `landing_blocked`
(defaults to `blocked`) and not in `threat`. A hop costs one step and is stored
as a normal `came_from` link; the caller detects it because consecutive path
tiles are not cardinally adjacent. `hops=False` for conveyor planning or when
pricing a throw against a walk.

`source` is always exempt from `no_go`: a unit standing somewhere forbidden
must still be allowed a move out.

## Differences from the steward original
- State lives in a `Terrain` value instead of attributes on the `Player`.
- `safe_path` takes a `survives(route_tail)` callback and returns
  `blocked_by_fire` instead of setting `p.blocked_by_fire`.
- `LAUNCH_HOPS_IN_PATHS` config flag dropped; pass `hops=False` instead.
- `blocking_launchers` / `route_baseline` not ported — they are steward-specific
  glue; `keeps_route_open` accepts the baseline set directly.
