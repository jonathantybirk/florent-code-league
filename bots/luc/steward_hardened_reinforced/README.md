# Steward, hardened

`steward_reinforced` as it stood at `a8dc58a3f`, rebuilt around the defensive
half of the 2.3.4 balance patch — and around a measurement defect that was
making the bot's own decisions depend on how busy the machine was.

Every number below is on fcode 2.3.6, the 21 official maps in both seats, 42
games a cell and 210 a row. The ladder plays the same pool, so this is the
distribution that counts.

## Against a rank-stratified panel

Opponents picked to span the ladder rather than to flatter the bot: their live
ladder ranks are 1, 19, 33, 69 and ~97 of 139.

|                               | vidar (1) | vidar_gg (19) | heimdall (33) | vigil (69) | tempest_r (97) | **mean** |
|-------------------------------|-----------|---------------|---------------|------------|----------------|----------|
| steward_reinforced (as taken) | 0.310     | 0.524         | 0.738         | 0.476      | 0.524          | 0.514    |
| **this bot**                  | **0.452** | **0.690**     | 0.643         | **0.571**  | **0.643**      | **0.600**|

**It beats everything from rank 19 down.** The only opponent still above it is
rank-1 `vidar`, and that gap has closed from 0.310 to 0.452.

That matters more than a mean, because the ladder's entire top 18 is `vidar`
variants. Against five of them:

| vs the top-18 vidar cluster | vidar | vidar_g_cap6 (8) | vidar_noring (10) | vidar_pg (17) | vidar_gg (19) | mean |
|---|---|---|---|---|---|---|
| this bot | 0.452 | 0.524 | 0.548 | 0.667 | 0.690 | **0.576** |

Four of the five, including two inside the top ten.

## The defect underneath the first attempt

`_out_of_time` bounded the bot's widest search by reading
`get_cpu_time_elapsed()`. That makes the *decisions* a function of machine load,
and it is not a small effect: **identical code, identical opponents, identical
seed, run twice, gave 11 different winners in 210 matches** and different round
counts in 23. Every effect measured on this bot was sitting on that noise floor,
and the first pass duly "measured" a 9.5pp gain from moving the threshold, which
was noise.

It is also backwards where it matters. The ladder machine is contended, so the
search that survives on an idle laptop is exactly the one that gets cut in the
games that count.

Both bounds are now deterministic — a round throttle on the siege-seat search
(`SIEGE_SEARCH_EVERY`) and a nearest-pads cap in the router (`PATH_MAX_PADS`) —
and the same two runs now agree on **84 of 84** matches, winners and round
counts alike. Everything below was then re-measured from scratch, so the numbers
are exact rather than approximate: a difference between two arms here is a real
difference, not a sample.

## What actually paid, on one-flag-off ablations

| removing | mean | worst | cost |
|---|---|---|---|
| — (shipping build) | 0.567 | 0.476 | — |
| the guard mending on any damage | 0.457 | 0.310 | **-11.0pp / -16.6pp** |
| the Sentinel home guard | 0.538 | 0.429 | -2.9pp / -4.7pp |
| the second mender | 0.553 | 0.476 | -1.4pp |
| the lane barrier ordered first | 0.562 | 0.476 | -0.5pp |

**Mending is the whole bot.** The gate it replaces was `alarm >= 2` — the Core
below 300 of 500 HP — *and* FORTIFY maps only, so the one Builder standing on
the Core watched it lose two fifths of its life before acting, and on a RUSH map
walked off to lay a Launcher ring while the Core died behind it. Healing needs
no sight of the shooter, which is the point: a Builder sees r²=20 and a Sentinel
shoots from r²=32, so the turret killing our Core is routinely invisible to the
Builder standing on it. At 4 HP for a flat 1 Ti, unaffected by cost scale, it is
the most efficient act in the game.

**Home defence buys Sentinels.** The Aug 4 patch put both turrets on the same
+20% cost scale, and that tax — not titanium — is what caps how many turrets a
game holds. Once the count is fixed by the tax, 10 Ti more a seat buys 1.71x the
damage, 1.6x the HP, 2.46x the range and a line terrain cannot block. Applied to
the two home-guard paths only; field turrets keep the Gunner, where reach buys
nothing and rotation is worth more.

## One repair, inherited

`launcher.py` used `LAUNCH_RANGE_SQ` without importing it, and
`_launch_enemy_away` is the **first call every Launcher makes every round** — so
every Launcher died to an uncaught `NameError` the first time an enemy came
within radius 2 (`run()` catches `GameError`; a `NameError` is not one). Present
in the snapshot this was taken from. Worth +1.4pp, and worth checking against
whatever `steward_reinforced` has become since.

## Measured and rejected

- **Late economic expansion: -9pp.** Vidar's largest economic mechanic. It does
  not transfer: only 33% of this bot's games reach round 200, and it is losing
  the ones that do not.
- **The parked attacker: -35pp.** Vidar ships a deliberately idle attacker on
  the finding that a Builder which never builds never raises the cost scale,
  worth +9.9pp there. `ATTACK_TURRET_CAP` 0 collapses this bot to 0.240. The
  clearest chassis-dependence result here: the same mechanic, +9.9pp on one bot
  and -35pp on another.
- **Mending harder is worse.** Dropping the second mender's trigger to the
  ordinary 50-HP alert costs 1.9pp of mean and 4.7pp of worst; widening its
  leash past 10 tiles changes nothing at all. The shipped thresholds are a
  measured optimum, not a default.
- **Sealing the Core on every doctrine: -0.4pp mean, -9.5pp worst.**
- **Faster home-turret escalation: +0.5pp**, one game in 210. Not shipped.
- **Sentinels shooting the supply line: neutral**, kept anyway — a turret
  declining a legal target is a defect whether or not a panel can price it. Not
  a gain and not cited as one.

## A correction to the record

The engine buffers store writes: *"a `write_store()` call becomes visible to all
units at the start of the next round"*. A per-round bitmask therefore **cannot**
accumulate — every unit reads the same snapshot, ORs its bit onto that same
stale value, and only the last writer survives.

`vidar/builder.py:318` says the opposite and builds a live headcount that way,
so its `live` always reads 1 and `ECON_MAX_LIVE_BUILDERS = 7` never binds.
Ported here verbatim it spawned **79 Builders in one game**. vidar is rank 1
*with that broken*, so it is opportunity there rather than a problem here.

## Compliance

`benchmarks.timing --maps all`: **0 turns over 10 ms**, worst 7,513 µs across
27,356 Builder turns — 25% headroom. Getting there without a clock meant
memoising the router and the turret-lane map per turn (both provably
behaviour-neutral: identical turn counts before and after) and throttling the
siege search. `SIEGE_SEARCH_EVERY` 4 scores better against the vidar cluster
(0.595/0.476) but puts one turn over the limit; 6 is the fastest setting that
passes, and 8 passes but drops two cluster matchups.

## Where it stands

Beats ranks 19 through ~97 on the stratified panel and four of the top-18 vidar
cluster. The goal is 80% of the field; a five-bot panel cannot certify that and
this does not claim it — the CI ladder is the only instrument that can, and
pushing this is what starts it.
