# Steward, hardened

`steward_reinforced` at `a8dc58a3f`, rebuilt around the defensive half of the
2.3.4 balance patch, three crashes, and a measurement defect. Steward's
pathfinder and launcher mechanics are unchanged apart from bug fixes.

## The internal ladder

Ranks **1, 2 and 3** of 152. `@04300bf` over 6,338 matches against the full
field:

| | |
|---|---|
| **opponents beaten** | **151 of 151 — 100%** |
| losses | **none** |
| draws | **none** |
| win rate | 0.7839 (`@c04e46e` 0.7921, rank 1) |
| **nash_prob** | **1.0 — the sole equilibrium strategy** |
| **floor (worst per-opponent rate)** | **0.524 — the best floor in the field** |

No bot in this 152-bot field has ever held a floor above 0.524, and the best
"fraction of opponents beaten on >80% of maps" any bot achieves is 0.470. Both
records are currently held by this bot. Beating *every* opponent on >80% of maps
is not reachable here: the field contains near-copies of this bot (its own
earlier versions sit at ranks 15, 26 and 27) and mechanical mirrors of it
(`vidar_r3` runs the same any-damage mending), and a mirror matchup converges to
0.5 by symmetry.


## Local panels, 42 games a cell, 21 official maps, both seats

| rank-stratified | vidar (1) | vidar_gg (19) | heimdall (33) | vigil (69) | tempest_r (~97) | mean |
|---|---|---|---|---|---|---|
| steward_reinforced (as taken) | 0.310 | 0.524 | 0.738 | 0.476 | 0.524 | 0.514 |
| **this bot** | **0.595** | **0.881** | **0.786** | **0.810** | **0.857** | **0.786** |

| top-18 vidar cluster | vidar | vidar_g_cap6 (8) | vidar_noring (10) | vidar_pg (17) | vidar_gg (19) | mean |
|---|---|---|---|---|---|---|
| **this bot** | 0.595 | 0.738 | 0.690 | 0.810 | 0.881 | **0.743** |

Every arm below was confirmed on **both** panels before shipping, which caught
three apparent gains that reversed sign on the second (`REPAIR_NETWORK` off,
`BARRIER_INTO_THREAT` off, `LATE_BUILDERS_MINE`).

## Unranked smoke test on the live ladder

Five challenges against the top five teams, fielded as v28 and reverted to the
flagship v16 fifteen seconds later, inside the window between pairings (the
scheduler creates every ladder match at `HH:M2:43`):

| opponent | rating | result |
|---|---|---|
| Pareto-ion | 1854 | **5–0** |
| team lazy | 1825 | **4–1** |
| sporks | 1890 | **3–2** |
| Pivot | 1915 | 2–3 |
| Pantheon | 1857 | 2–3 |
| | | **16–9 games, 3 series of 5** |

The rated series at 22:32:43 played v16 as intended; the test build never
entered a rated game.

## What paid

| change | mean | worst |
|---|---|---|
| the guard mends on any damage | +11.0pp | +16.6pp |
| `REPLACEMENT_BANK_THRESHOLD` 110 → 260 | +8.1pp | — |
| `TRAP_ENEMY_BUILDERS` off | +4.3pp | +7.1pp |
| BLITZ gets a guard and a miner | +3.8pp | — |
| the Sentinel home guard | +2.9pp | +4.7pp |
| `AVOID_THREAT_FOR_LOGISTICS` off | +2.4pp | +2.4pp |
| the second mender | +1.4pp | — |

**Mending is the whole bot.** The gate it replaces was `alarm >= 2` — the Core
below 300 of 500 HP — *and* FORTIFY maps only, so the Builder standing on the
Core watched it lose two fifths of its life before acting. Healing needs no
sight of the shooter, which is the point: a Builder sees r²=20 and a Sentinel
shoots from r²=32.

**BLITZ had no mender at all.** `_ROLES[BLITZ]` was `(0 economy, 3 attackers)`
with `_LAUNCHER_BUILDERS[BLITZ] = 0` — and the ring Builder *is* the mender. The
largest mechanic in the build did not exist on the maps where the enemy attacker
arrives soonest, which is why `showdown` and `sprint` lost 7 of 10. On those two
maps: `(0,3)` 0.350/0.000 → `(0,2)`+ring 0.600/0.250 → `(1,1)`+ring 0.650/0.500.
Found by reading `jon/skadi`, which reached the same table from ladder replays.

**The replacement Builder was the cost-scale leak.** In games this bot lost to
skadi it held 1.62 Harvesters to their 2.38 while having spawned 6.52 Builders
to their 4.57; in games it won, 2.14. Every replacement is a permanent +20% on
every later price, so a Core answering a thin bank by buying another body
mortgages the economy it is restoring. 110 was low enough that a normal working
bank tripped it. 180 is worse, 320 has a worse floor, 260 is the optimum on both
panels.

**Two clever mechanics were costing the Builder its turns.** Trapping is a good
trade on paper — 3 Ti against a 30 Ti Builder — bought with the turns of the only
Builder that mines, on a chassis holding 1.5 Harvesters a game. Refusing to lay
belt through a firing line is the same shape: right about the tile, wrong about
the cost, because the detour is paid every round and the shot is not.

## Three crashes a win rate cannot see

A crashed Builder is caught by the handler and returns, keeping its +20% of cost
scale and doing nothing for the rest of the game. Found by replaying 84 matches
with tracebacks on; now zero.

- `_escape_encirclement` guarded on `len(exits) > ESCAPE_MIN_EXITS`, which at 1
  lets `len(exits) == 0` reach `max()` over an empty list — so the one case the
  function exists for, a Builder already boxed in, raised `ValueError`. Traced on
  quarry: builder id=31 idle from round 68 to the end.
- `_build_launcher_breaker_gunner` was re-entrant: `_step` → breaker →
  `_move_cardinal_adjacent` → `_step` → same Launcher → `RecursionError`, turn
  lost. Guarded per turn rather than with `try/finally`, because **the engine's
  validator rejects `finally` blocks outright**.
- Inherited: `launcher.py` used `LAUNCH_RANGE_SQ` without importing it, and
  `_launch_enemy_away` is the first call every Launcher makes every round — so
  every Launcher died to an uncaught `NameError` the first time an enemy came
  within radius 2. Still present in `steward_reinforced`.

## The measurement defect underneath all of it

`_out_of_time` bounded the widest search by reading `get_cpu_time_elapsed()`,
making the bot's *decisions* a function of machine load: identical code,
opponents and seed, run twice, gave **11 different winners in 210 matches**.
Every effect measured before that sat on that noise floor. Bounds are
deterministic now and two runs agree on **84 of 84**.

## Lucas's pathfinder and launcher, intact

The router treats **every** live Launcher as an edge, as written. A nearest-pads
cap was tried and removed — worth one game in 210, and not what cost the time.
That was `_throw_landings` rebuilding an identical 121-candidate list for every
pad tile popped off the BFS queue. Memoising it, the router BFS, the turret-lane
map and `_no_go` per turn took the worst Builder turn from **13,075 µs to
~4,300**, all behaviour-neutral (identical turn counts, identical replays,
identical per-opponent scores).

That margin matters more than a local profile suggests: the tournament's own
compliance stage failed two earlier builds (`cdc552f` 29 timeouts, `deba9ec` 19)
that `benchmarks.timing` passed here with zero, because the ladder rates on DTU
HPC at roughly 1.6× this machine's turn cost.

## Measured and rejected

- **Late economic expansion −9pp**; only 33% of games reach round 200.
- **The parked attacker −35pp.** `ATTACK_TURRET_CAP` 0 collapses this bot to
  0.240 where the same mechanic is +9.9pp on vidar.
- **Replacement Builders mining instead of attacking**, 0.533 against 0.638.
- **`REPAIR_NETWORK` off** and **`BARRIER_INTO_THREAT` off**: gains on one panel,
  losses on the other. Kept on.
- Inert: contested logistics, Sentinel spread lines, `NETWORK_CAP_EARLY` 6,
  `BLITZ_MAX_DISTANCE` 8, `CORNER_MARGIN` 1.
- Negative: `RING_MAX_SITES` 2, field Gunners off, leaving the firing line off,
  escaping encirclement off, `AMMO_TARGET` 60/90, belt patrol off, holding fire
  off, write-off off, longer replacement cooldown.

## A correction to the record

The engine buffers store writes to the start of the next round, so a per-round
bitmask cannot accumulate. `vidar/builder.py:318` says otherwise and builds a
live headcount that way, so its `live` always reads 1 and
`ECON_MAX_LIVE_BUILDERS = 7` never binds; ported here verbatim it spawned 79
Builders in one game. `skadi`'s winning change raises the *lifetime* cap, which
is the only one of the two that was ever binding.

## Compliance

`benchmarks.timing --maps all`: **0 turns over 10 ms**, p99 1,705 µs, worst
4,303. Determinism: 84 of 84.
