# Steward, hardened

`steward_reinforced` at `a8dc58a3f`, rebuilt around the defensive half of the
2.3.4 balance patch, two crashes, and a measurement defect. Steward's pathfinder
and launcher mechanics are unchanged apart from bug fixes.

fcode 2.3.6, the 21 official maps in both seats, 42 games a cell — the pool the
ladder plays. The engine is deterministic once the bot stops reading the clock
(see below), so these are exact, not sampled.

## Where it stands

| rank-stratified panel | vidar (1) | vidar_gg (19) | heimdall (33) | vigil (69) | tempest_r (~97) | mean |
|---|---|---|---|---|---|---|
| steward_reinforced (as taken) | 0.310 | 0.524 | 0.738 | 0.476 | 0.524 | 0.514 |
| **this bot** | **0.595** | **0.762** | 0.690 | **0.738** | **0.738** | **0.705** |

| top-18 vidar cluster | vidar | vidar_g_cap6 (8) | vidar_noring (10) | vidar_pg (17) | vidar_gg (19) | mean |
|---|---|---|---|---|---|---|
| **this bot** | 0.595 | 0.714 | 0.571 | 0.714 | 0.762 | **0.671** |

It beats every opponent on both panels. Against the current ladder leader,
`jon/skadi`, it draws 21–21, up from 0.405 two commits ago.

**On the live ladder, the first version of this bot (`@cdc552f`) already beat 125
of 146 opponents — 85.6% — at rank 20 with a 0.6684 win rate.** Its 21 losses
were almost all the vidar/skadi family plus `pantheon_replica_day3`,
`prospect_rushonly`, `steward@e55aab5`, `bastion` and `janus`. Every one of those
named matchups is now a win:

| former ladder loss | then | now |
|---|---|---|
| prospect_rushonly | 0.476 | 0.571 |
| pantheon_replica_day3 | 0.452 | 0.690 |
| steward@e55aab5 | 0.476 | 0.714 |
| bastion | 0.500 | 0.833 |
| janus | 0.524 | 0.619 |

## The defect that made everything before it unreliable

`_out_of_time` bounded the widest search by reading `get_cpu_time_elapsed()`,
which makes the bot's *decisions* a function of machine load. Identical code,
identical opponents, same seed, run twice: **11 different winners in 210
matches**. Every effect measured before that was sitting on that noise floor. It
is also backwards in production — the ladder machine is contended, so the search
that survives on an idle laptop is the one cut in rated games.

Bounds are deterministic now, and two runs of the final build agree on **84 of
84** matches. Everything below was re-measured after the fix, and every arm that
looked good on one panel was re-checked on a second — which caught two apparent
gains (`REPAIR_NETWORK` off, `BARRIER_INTO_THREAT` off) that reversed sign.

## What paid

| change | mean | worst |
|---|---|---|
| the guard mends on any damage | +11.0pp | +16.6pp |
| `TRAP_ENEMY_BUILDERS` off | +4.3pp | +7.1pp |
| BLITZ gets a guard and a miner | +3.8pp | — |
| the Sentinel home guard | +2.9pp | +4.7pp |
| `AVOID_THREAT_FOR_LOGISTICS` off | +2.4pp | +2.4pp |
| the second mender | +1.4pp | — |

**Mending is the whole bot.** The gate it replaces was `alarm >= 2` — the Core
below 300 of 500 HP — *and* FORTIFY maps only, so the Builder standing on the
Core watched it lose two fifths of its life before acting. Healing needs no sight
of the shooter, which is the point: a Builder sees r²=20 and a Sentinel shoots
from r²=32.

**BLITZ had no mender at all.** `_ROLES[BLITZ]` was `(0 economy, 3 attackers)`
with `_LAUNCHER_BUILDERS[BLITZ] = 0` — and the ring Builder *is* the mender. The
largest mechanic in the build simply did not exist on the maps where the enemy
attacker arrives soonest, which is why `showdown` and `sprint` lost 7 of 10.
Measured on those two maps: `(0,3)` no ring 0.350/0.000 → `(0,2)` + ring
0.600/0.250 → `(1,1)` + ring 0.650/0.500. Found by reading `jon/skadi`, which
reached the same table from ladder replays where an answered blitz was then
out-mined.

**Two clever mechanics were costing the Builder its turns.** Trapping walls an
enemy Builder in and puts a turret on the box — a good trade on paper, 3 Ti
against a 30 Ti Builder, bought with the turns of the only Builder that mines on
a chassis holding 1.5 Harvesters a game. Refusing to lay belt through a known
firing line is the same shape: right about the tile, wrong about the cost,
because the detour is paid every round and the shot is not.

## Two crashes a win rate cannot see

A crashed Builder is caught by the handler and returns, keeping its +20% of cost
scale and doing nothing for the rest of the game. Found by replaying 84 matches
with tracebacks on; both are now zero.

- `_escape_encirclement` guards on `len(exits) > ESCAPE_MIN_EXITS`, which at the
  shipped value of 1 lets `len(exits) == 0` through to `max()` over an empty
  list. The one case the function exists for — a Builder already fully boxed in —
  raised `ValueError` instead of handling it. Traced on quarry: builder id=31
  idle from round 68 to the end.
- `_build_launcher_breaker_gunner` was re-entrant: `_step` calls it when a
  Launcher blocks the route, it walks with `_move_cardinal_adjacent`, that calls
  `_step`, which meets the same Launcher — `RecursionError`, turn lost. Guarded
  with a per-turn flag rather than `try/finally`, because **the engine's
  validator rejects `finally` blocks outright**.

Inherited from the snapshot: `launcher.py` used `LAUNCH_RANGE_SQ` without
importing it, and `_launch_enemy_away` is the first call every Launcher makes
every round, so every Launcher died to an uncaught `NameError` the first time an
enemy came within radius 2. Still present in `steward_reinforced`.

## Lucas's pathfinder and launcher, intact

The router treats **every** live Launcher as an edge, as written. A nearest-pads
cap was tried and removed: it was worth one game in 210 and was not what cost the
time. That was `_throw_landings` rebuilding the identical 121-candidate list for
every pad tile popped off the BFS queue. Memoising it, the router BFS and the
turret-lane map per turn took the worst Builder turn from **13,075 µs to
4,507**. All three caches are behaviour-neutral — identical turn counts and
identical replays before and after — and they bought back enough headroom that
the siege search is now tuned on strength rather than on time.

## Measured and rejected

- **Late economic expansion −9pp**; only 33% of games reach round 200.
- **The parked attacker −35pp.** `ATTACK_TURRET_CAP` 0 collapses this bot to
  0.240 where the same mechanic is +9.9pp on vidar.
- **Replacement Builders mining instead of attacking: 0.533 against 0.638.** The
  ledger correlation that suggested it — losses spawn 7.5 Builders and hold 1.25
  Harvesters, wins spawn 5.6 and 1.63 — is not causal in that direction.
- **`REPAIR_NETWORK` off** and **`BARRIER_INTO_THREAT` off** both looked like
  gains on one panel and lost on the other. Kept on.
- Inert: contested logistics, Sentinel spread lines, `NETWORK_CAP_EARLY` 6,
  `BLITZ_MAX_DISTANCE` 8, `CORNER_MARGIN` 1.
- Negative: `RING_MAX_SITES` 2 (−8.1pp), field Gunners off (−6.7pp), leaving the
  firing line off (−4.8pp), escaping encirclement off (−7.2pp), `AMMO_TARGET` 60
  or 90, belt patrol off, holding fire off, write-off off.

## A correction to the record

The engine buffers store writes to the start of the next round, so a per-round
bitmask cannot accumulate. `vidar/builder.py:318` says otherwise and builds a
live headcount that way, so its `live` always reads 1 and
`ECON_MAX_LIVE_BUILDERS = 7` never binds. Ported here verbatim it spawned 79
Builders in one game. `skadi`'s winning change raises the *lifetime* cap, which
is the only one of the two that was ever binding.

## Compliance

`benchmarks.timing --maps all`: **0 turns over 10 ms**.
