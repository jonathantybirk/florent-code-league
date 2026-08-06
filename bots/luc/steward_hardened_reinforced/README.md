# Steward, hardened

`steward_reinforced` at `a8dc58a3f`, rebuilt around the defensive half of the
2.3.4 balance patch, three crashes, and a measurement defect. Lucas's pathfinder
and launcher mechanics are unchanged apart from bug fixes.

## Where it stands

**Internal ladder — this bot holds the entire top five of 154.** `@f1f2bda`,
6,426 matches against the full field:

| | |
|---|---|
| **opponents beaten** | **150 of 153 (98.0%)** |
| the only three it does not beat | **its own sibling versions** |
| win rate | **0.7901** |
| Nash core | split between `@a994296` and `@04300bf` — skadi and vidar displaced |
| floor (worst per-opponent rate) | 0.548, the best in the field |

Nothing in the field except copies of itself can hold this build. That is also
the ceiling on the "beat every bot on >80% of maps" target: a mirror matchup
converges to 0.5 by symmetry, and the top five entries are all mirrors of each
other. The best floor any bot has ever held here is 0.524, and the best
"fraction of opponents beaten on >80% of maps" is 0.470 — both records set by
this lineage.

**Live ladder** (new CI feed): `@c04e46e` is the active submission at **0.583**
game win rate over 36 matches (+15.9 Elo); newer builds run 0.600–0.640, against
skadi at 0.431–0.533 and `vidar@8b87da5` at 0.440. Team rating 1824 → 1836.

**Local panels**, 42 games a cell, 21 official maps, both seats:

| rank-stratified | vidar | vidar_gg | heimdall | vigil | tempest_r | mean | floor |
|---|---|---|---|---|---|---|---|
| as taken | 0.310 | 0.524 | 0.738 | 0.476 | 0.524 | 0.514 | 0.310 |
| **this bot** | **0.690** | **0.952** | **0.762** | **0.714** | **0.786** | **0.781** | **0.690** |

| hard panel (its five worst) | skadi | vidar_r3 | vidar_r2 | vidar | vidar_r1 | mean |
|---|---|---|---|---|---|---|
| **this bot** | 0.548 | 0.595 | 0.619 | 0.690 | 0.690 | **0.629** |

## What paid

| change | mean | floor |
|---|---|---|
| the guard mends on any damage | +11.0pp | +16.6pp |
| `REPLACEMENT_BANK_THRESHOLD` 110 → 260 | +8.1pp | — |
| `TRAP_ENEMY_BUILDERS` off | +4.3pp | +7.1pp |
| BLITZ gets a guard and a miner | +3.8pp | — |
| the Sentinel home guard | +2.9pp | +4.7pp |
| `AVOID_THREAT_FOR_LOGISTICS` off | +2.4pp | +2.4pp |
| late economic expansion + reserve 60 | +3.9pp | +4.7pp |
| Harvester recheck (deposit recovery) | — | +2.4pp |
| contest their belt when it is nearer | +0.9pp | +2.4pp |
| the second mender | +1.4pp | — |

Two of these only work because of each other. **Late economic expansion measured
−9pp when first tried and +2.0pp after the Harvester recheck landed** — before
it, a Harvester shot out of sight retired its deposit permanently, so extra
Builders arrived into an economy that could only decay and paid +20% each for
the privilege.

## The standing benchmark set

Built to answer specific questions, and re-run against each build. `bench.py`
in the scratchpad reads a stderr log with `DEBUG_BUILD`/`DEBUG_LAUNCH` on.

**Economy over time** — the one that found the deposit bug. Mean live Harvesters:

| round | 50 | 150 | 300 | 500 | 999 |
|---|---|---|---|---|---|
| ours, games won | 1.80 | 1.44 | 1.35 | 1.25 | 1.32 |
| ours, games lost | 1.62 | 0.98 | 0.52 | 0.13 | 0.12 |
| the vidar line | 1.88 | 1.96 | 1.29 | 0.88 | 0.69 |

It still decays, and that is **not** the binding constraint: adding miners loses
every time it is tried (see below). 90% of this bot's games end in a Core kill,
not the round-1000 tiebreak, so the economy funds pressure rather than winning
on its own.

**Launcher** — 369 served, 281 refused (43%). The refusals are the firing-line
check working as designed. Throws are honoured exactly or refused; there is no
silent redirect, and only **4.6% land ≥2 tiles** from the request (max 5), which
is the passenger acting after it lands.

**Builder pacing** — of 89 Builders living 60+ rounds, **18% spend their last
sixty bouncing between three tiles or fewer** while moving in a third of them,
and **42% never move at all** (mostly menders standing on the Core, which is
their job). Real waste, but every attempt to convert it has measured negative.

**Build exposure** — 14.0% of buildings go into a known enemy turret's line, 88
of 90 of them the deliberate `built_blocker_gunner`.

## Three crashes a win rate cannot see

A crashed Builder is caught by the handler and returns, keeping its +20% of cost
scale and doing nothing for the rest of the game. Found by replaying 84 matches
with tracebacks on; now zero.

- `_escape_encirclement` guarded on `len(exits) > ESCAPE_MIN_EXITS`, which at 1
  lets `len(exits) == 0` reach `max()` over an empty list — the one case the
  function exists for raised `ValueError` instead. Builder id=31 idle from round
  68 to the end on quarry.
- `_build_launcher_breaker_gunner` was re-entrant: `_step` → breaker →
  `_move_cardinal_adjacent` → `_step` → `RecursionError`. Guarded per turn, not
  with `try/finally` — **the engine's validator rejects `finally` outright**.
- Inherited: `launcher.py` used `LAUNCH_RANGE_SQ` without importing it, and
  `_launch_enemy_away` is the first call every Launcher makes every round, so
  every Launcher died to `NameError` the first time an enemy came within radius
  2. Still present in `steward_reinforced`.

## The measurement defect underneath all of it

`_out_of_time` bounded the widest search with `get_cpu_time_elapsed()`, making
decisions a function of machine load: identical code, opponents and seed, run
twice, gave **11 different winners in 210 matches**. Bounds are deterministic
now and two runs agree on **84 of 84**. Every arm since is confirmed on two
panels, which caught five apparent gains that reversed sign on the second.

## Lucas's pathfinder and launcher, intact

Every live Launcher is an edge in the router, as written. A nearest-pads cap was
tried and removed. The cost was `_throw_landings` rebuilding an identical
121-candidate list for every pad tile popped off the BFS queue; memoising it,
the router BFS, the turret-lane map and `_no_go` per turn took the worst Builder
turn from **13,075 µs to ~4,300**, all behaviour-neutral.

That margin is not cosmetic: the tournament's own compliance stage failed two
earlier builds (`cdc552f` 29 timeouts, `deba9ec` 19) that `benchmarks.timing`
passed here with zero, because the ladder rates on DTU HPC at ~1.6× this
machine's turn cost.

## Measured and rejected

- **A standoff against a blocking bot: −11pp** at every setting. When a bot
  blocks the only route, `_step` already falls through to the launcher escape —
  build a pad and go over it. That costs a round and *solves* it; waiting costs
  a round and does not.
- **A cooldown before re-requesting a refused throw: −2.9pp.** A refusal hands
  back turret intel, so the next request is better informed, not a repeat.
- **Expansion Builders mining instead of attacking: −14pp**, on three different
  bases. This chassis wins by pressure.
- **The parked attacker −35pp**; `ATTACK_TURRET_CAP` 0 collapses it to 0.240
  where the same mechanic is +9.9pp on vidar.
- **Seat-aware play: inert.** The seat gap is real and large — 0.667 from seat A
  against 0.514 from seat B, against every opponent — but escalating defence,
  preferring range and declining duels all move nothing, because they tune
  `_defend_core`, which the any-damage mender now pre-empts.
- **Flank-when-idle: inert.** Kept on; the waste it targets is real.
- Also negative or inert: `REPAIR_NETWORK` off, `BARRIER_INTO_THREAT` off,
  `RING_MAX_SITES` 2, field Gunners off, `AMMO_TARGET` 60/90, belt patrol off,
  `NETWORK_CAP_EARLY` 6, `BLITZ_MAX_DISTANCE` 8, `CORNER_MARGIN` 1.

## Required behaviour

A conveyor this bot breaks gets a barrier in the hole on the next turn, ahead of
every other errand, with a four-tile leash to walk back. Cutting without
plugging is rented damage. Measured neutral on the hard panel and +2.4pp on the
stratified floor; in regardless.

## Compliance

`benchmarks.timing --maps all`: **0 turns over 10 ms**. Determinism: 84 of 84.
