# Steward, hardened

`steward_reinforced` as it stood at `a8dc58a3f`, rebuilt around the defensive
half of the 2.3.4 balance patch. fcode 2.3.6, the 21 official maps in both
seats, 42 games a cell and 210 a row — the pool the ladder plays.

## Against a rank-stratified panel

Opponents chosen to span the ladder rather than to flatter the bot; their live
ranks are 1, 19, 33, 69 and ~97 of 139.

|                               | vidar (1) | vidar_gg (19) | heimdall (33) | vigil (69) | tempest_r (97) | **mean** |
|-------------------------------|-----------|---------------|---------------|------------|----------------|----------|
| steward_reinforced (as taken) | 0.310     | 0.524         | 0.738         | 0.476      | 0.524          | 0.514    |
| **this bot**                  | **0.500** | **0.738**     | 0.643         | **0.643**  | **0.667**      | **0.638**|

It beats every opponent below rank 1 and draws rank-1 `vidar` dead level, from
0.310. Against five of the top-18 `vidar` cluster — which is what the ladder's
whole top end is made of — it takes four and draws `vidar`: 0.500, 0.595, 0.619,
0.667, 0.738, mean 0.624.

**Where it still loses: Jon's `skadi` beats this bot 25–17 (0.405).** That is the
honest standing. `skadi` is `vidar` plus two constants, and `vidar` is a far
stronger chassis than the `steward` this was required to start from — but it is
ahead, and two of the three biggest gains below came from reading its notes.

## The one that mattered most, and it came from skadi's README

`_ROLES[BLITZ]` was `(0 economy, 3 attackers)` with `_LAUNCHER_BUILDERS[BLITZ] =
0` — no miner, and **no ring Builder at all**.

The ring Builder is this bot's mender: the Builder that stands on the Core and
heals it, worth 11.0pp of mean and 16.6pp of the worst matchup on a one-flag-off
ablation, the largest single mechanic in the build. BLITZ was the one doctrine
that did not have it, on exactly the maps where the enemy attacker arrives
soonest. That is why `showdown` and `sprint` were the worst maps in the ledger
at 7 losses in 10 apiece.

Measured on those two maps, both seats, five opponents:

| BLITZ roles | mean | worst |
|---|---|---|
| `(0, 3)`, no ring Builder — as taken | 0.350 | **0.000** |
| `(0, 2)` + ring Builder | 0.600 | 0.250 |
| **`(1, 1)` + ring Builder — shipped** | **0.650** | **0.500** |

Jon reached the same table from the other end, tracing ladder replays where the
blitz was answered and the survivor simply out-mined a bot holding zero
Harvesters at round 120. Both halves are real: the guard is what stops the Core
dying, the miner is what wins the game that follows.

On the full panel this is worth +3.8pp of mean and it is what took `vidar` from
0.452 to a draw.

## What else paid, on one-flag-off ablations

| removing | mean | worst | cost |
|---|---|---|---|
| — (shipping build) | 0.567 | 0.476 | — |
| the guard mending on any damage | 0.457 | 0.310 | **-11.0pp / -16.6pp** |
| the Sentinel home guard | 0.538 | 0.429 | -2.9pp / -4.7pp |
| the second mender | 0.553 | 0.476 | -1.4pp |
| the lane barrier ordered first | 0.562 | 0.476 | -0.5pp |

The mending gate this replaces was `alarm >= 2` — the Core below 300 of 500 HP —
*and* FORTIFY maps only, so the Builder standing on the Core watched it lose two
fifths of its life before acting. Healing needs no sight of the shooter, which is
the point: a Builder sees r²=20 and a Sentinel shoots from r²=32.

Home defence buys Sentinels because 2.3.4 put both turrets on the same +20% cost
scale, and that tax caps how many turrets a game holds; once the count is fixed
by the tax, 10 Ti more a seat buys 1.71x the damage, 1.6x the HP and 2.46x the
range. Field turrets keep the Gunner, where reach buys nothing.

## The pathfinder and the launcher are Lucas's, unchanged

The router treats **every** live Launcher as an edge, exactly as written. A
nearest-pads cap was tried while chasing the turn limit and has been removed: it
was not what cost the time, and it was worth one game in 210.

What cost the time was `_throw_landings` rebuilding the identical 121-candidate
list for every pad tile popped off the BFS queue — hundreds of times a turn, the
same answer each time. Memoising it per turn (with the router BFS and the
turret-lane map) took the worst Builder turn from **13,075 µs to 4,507** against
a 10,000 limit. All three caches are provably behaviour-neutral: identical turn
counts and identical replays before and after.

One repair: `launcher.py` used `LAUNCH_RANGE_SQ` without importing it, and
`_launch_enemy_away` is the first call every Launcher makes every round — so
every Launcher died to an uncaught `NameError` the first time an enemy came
within radius 2 (`run()` catches `GameError`; a `NameError` is not one). Worth
+1.4pp. Still present in `steward_reinforced`.

## The measurement defect underneath all of it

`_out_of_time` bounded the widest search by reading `get_cpu_time_elapsed()`,
which makes the bot's *decisions* a function of machine load: identical code,
identical opponents, same seed, run twice gave **11 different winners in 210
matches**. Every effect here was sitting on that noise floor. It is also
backwards in production — the ladder machine is contended, so the search that
survives on an idle laptop is the one cut in rated games.

Bounds are deterministic now (`SIEGE_SEARCH_EVERY`), and two runs of the final
build agree on **84 of 84** matches, winners and round counts alike. Everything
above was re-measured after the fix, so a difference between two arms is a real
difference rather than a sample.

With the caches in place the throttle costs nothing at any setting, so it is
tuned purely on strength: 1 gives the best mean (0.662) but loses to `vidar`; 6
gives 0.638 and draws it, taking four of the vidar cluster to 1's three. Shipped
at 6, because the ladder's top 18 are all vidar variants.

## Measured and rejected

- **Late economic expansion: -9pp.** Only 33% of this bot's games reach round
  200, and it is losing the ones that do not.
- **The parked attacker: -35pp.** `ATTACK_TURRET_CAP` 0 collapses this bot to
  0.240, where the same mechanic is +9.9pp on vidar. The clearest
  chassis-dependence result here.
- **Mending harder is worse.** Dropping the second mender to the 50-HP alert
  costs 1.9pp mean / 4.7pp worst; widening its leash past 10 tiles is inert.
- **Sealing the Core on every doctrine: -9.5pp worst.**
- **Faster home-turret escalation: +0.5pp**, one game in 210. Not shipped.

## A correction to the record

The engine buffers store writes to the start of the next round, so a per-round
bitmask cannot accumulate — every unit reads the same snapshot and only the last
writer survives. `vidar/builder.py:318` says otherwise and builds a live
headcount that way, so its `live` always reads 1 and `ECON_MAX_LIVE_BUILDERS = 7`
never binds. Ported here verbatim it spawned 79 Builders in one game. Worth
noting that `skadi`'s winning change raises the *lifetime* cap, which is the only
one of the two that was ever binding.

## Compliance

`benchmarks.timing --maps all`: **0 turns over 10 ms**, worst 5,348 µs across
25,616 Builder turns — nearly half the limit spare.
