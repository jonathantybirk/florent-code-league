# Engine and tutorial mechanics audit

Audit date: 31 July 2026. Runtime under test: `fcode 2.2.0`.

`uv pip install --dry-run --upgrade fcode` reports no changes on the configured
package index, and `uv run fcode --version` reports `2.2.0`. The project is
pinned to that version in `pyproject.toml`.

## Engine-verified unit matrix

| Entity | Current behavior relevant to Jonbot |
|---|---|
| Core | 500 HP, 2x2, vision r2=36, spawn r2=2; only spawns Builders. A Builder spawned on round 0 first runs on round 1. |
| Builder | 40 HP, vision r2=20, all 8 adjacent moves; build range includes diagonals and its own tile. Building and moving in the same round is legal. Attack costs 2 Ti for 2 damage; heal costs 1 Ti for 4 HP. |
| Gunner | 40 HP, r2=13, 10 damage, 2 local ammo/shot, 1-round cooldown; directional ray and rotatable for 10 Ti. |
| Sentinel | 30 HP, r2=32, 18 damage, 10 local ammo/shot, 3-round cooldown; fixed facing and piercing line. |
| Launcher | 30 HP, r2=26 throw measured from Launcher, adjacent friendly-Builder pickup, 1-round cooldown, no ammo. |
| Harvester | 30 HP, produces stacks of 10 Ti on a 4-round cadence; physical routing is required. |
| Conveyor | 20 HP, cardinal facing, one 10-Ti stack held/moved per round. |
| Splitter | 20 HP, cardinal facing, 10-Ti stack capacity; one rear input and three round-robin outputs. |
| Barrier | 30 HP, blocks movement and line of sight. |

Base costs: Builder 30, Conveyor 3, Splitter 6, Harvester 20, Barrier 3,
Gunner 10, Sentinel 30, Launcher 20. Scaling is shared team-wide and depends
on living constructed entities.

## Stale tutorial claims

The local tutorial mirror is not authoritative for movement/build timing. Its
claims that Builders move only cardinally, cannot build on their own tile or
diagonally, and cannot build and move in one round are false in `fcode 2.2.0`.
The Core page's “active in the same round” claim is also false. The already
marked corrections about nonexistent global ammo,
`Position.cardinal_direction_to`, and `Direction.is_cardinal` remain valid.

Treat the executable engine as the source of truth: use `can_*` before acting,
and keep small probe/replay regressions for timing-sensitive assumptions.

## Opening planner implemented in Jonbot

Jonbot now buys two opening Builders by default and a third only when three
visible deposits or two live claims demonstrate parallel work. Builders use
stagger-safe ids and nonduplicating store claims. They score deposits by
`travel + harvester build + conveyor-line length`, commit only to a route
through observed terrain, build the Harvester first, and then lay a shortest
cardinal return line at up to one Conveyor plus one move per round. With no
proven economic job, they explore deterministic interleaved sectors.

This is an online heuristic, not globally optimal play under fog. The offline
planner remains an upper-bound benchmark. Later scoring should add enemy
exposure, defense reserve, trunk capacity, and remaining match horizon.

## Locating the enemy Core

Start with the Core footprints implied by 180-degree rotation, vertical
reflection, and horizontal reflection. Maintain a three-bit symmetry mask
rather than guessing the common map type.

Eliminate a transform whenever observed terrain disagrees with its paired
observed tile, or its predicted enemy-Core footprint is visible and contains
no enemy Core. Deduplicate coordinates because multiple transforms can imply
the same enemy location.

Scout priorities should be:

1. reachable tiles where surviving transforms predict different terrain,
   maximizing expected mask reduction per travel turn;
2. the nearest unresolved candidate Core footprint;
3. ordinary high-coverage exploration frontiers.

Builders report eliminated-mask bits or a directly seen enemy Core through
the store; the Core merges them next round. Once all surviving transforms
agree on one coordinate, attackers have a justified target without ever
identifying a map by name. Direct enemy sight always overrides inference.
