# Trying to beat vidar: a negative result, and the levers it rules out

Measured 2026-08-06 on fcode 2.3.6. Panel: `odin`, `steward`, `prospect`,
`vigil`, `heimdall`, `gobbleglitch` (from `x/luc` and `elias_dev`), 6 official
maps, both seats, 72 games per cell. Harness: `tools/bench.py`.

**I did not beat vidar.** Everything below is what was tried and what it cost.

## First: vidar really is our best bot

Head-to-head, 3 maps both seats:

| pairing | result |
|---|---|
| vidar vs odin | **6-0** |
| vidar vs steward | **6-0** |
| vidar vs prospect | **5-1** |
| odin vs steward | 3-3 |
| odin vs prospect | 3-3 |

And against the full panel it scores **0.833** (60-12): odin 0.917, steward
0.750, prospect 0.750, vigil 0.667, heimdall 1.000, gobbleglitch 0.917. Its
weakest matchup here is vigil, which matches Lucas's own generated-map finding
that vigil is the binding constraint.

## The measurement trap: a mirror match measures nothing

`skadi` (a vidar fork) against vidar scored exactly 8-8 under three different
configurations. That is not noise -- it is structural:

| map | skadi as seat A | skadi as seat B |
|---|---|---|
| atoll | vidar wins | skadi wins |
| duel | vidar wins | skadi wins |
| fjord | vidar wins | skadi wins |
| hive | skadi wins | vidar wins |

**The winner is fully determined by map and seat.** On atoll/duel/fjord the
second-spawning team always wins; on hive the first always does. Bot identity is
irrelevant. Between two near-identical bots the engine's spawn-order advantage
decides everything, so head-to-head is worthless as a fitness signal and every
comparison below is made against the shared panel instead.

## Sentinels are the dominant lever, and they are already tuned

Disabling `sentinel.run` entirely: **0.778 -> 0.472** on a 3-opponent subset. So
Sentinels are worth ~0.31 of win rate and are the right place to look.

They are also already at their optimum. Everything tried moved it down or not at
all:

| change | result | vs 0.833 |
|---|---|---|
| `MAX_GUARD_SENTINELS` 2 -> 3 | 0.750 | **-0.083** |
| `MAX_GUARD_SENTINELS` 2 -> 4 | 0.764 | **-0.069** |
| `AMMO_TARGET` 120 -> 200 | 0.667 | **-0.166** |
| `AMMO_TARGET` 120 -> 320 | 0.597 | **-0.236** |
| `NETWORK_CAP_EARLY` 4 -> 5 | 0.806 | -0.027 |
| `NETWORK_CAP_EARLY` 4 -> 6 | 0.806 | -0.027 |
| surplus-titanium -> ammunition, threshold 400 | 0.750 | **-0.083** |
| surplus-titanium -> ammunition, threshold 1000/2000 | 0.833 | inert |
| `SIEGE_SENTINEL_BATTERY` 2 -> 3, 2 -> 4 | 0.833 | inert |
| `NETWORK_CAP_LATE` 8 -> 12 | 0.833 | inert |
| `ECON_MAX_LIVE_BUILDERS` 7 -> 9 | 0.833 | inert |
| `ECON_EXPAND_ROUND` 120 -> 80 | 0.833 | inert |
| `MIN_AMMO_FOR_SENTINEL` 40 -> 20 | 0.833 | inert |
| Sentinel targeting refinements (below) | 0.833 | inert |

Lucas's constants are confirmed correct from an independent direction. Guard
count 2, harvester cap 4 and `AMMO_TARGET` 120 are all genuine optima, not
leftovers.

## The two ideas that were principled and still did nothing

Both are in `bots/jon/skadi/sentinel.py` and both measured **exactly** 0.833.

**Hunt the mender when the siege stalls.** vidar already detects a stalled Core
siege (`core_stalled >= SIEGE_STALL_ROUNDS`) and looks away to the economy. By
its own arithmetic a stalled siege means a Builder is out-healing it, and that
Builder is 40 HP against the Core's 500 -- so reach for it anywhere in range
rather than only inside `BUILDER_PRIORITY_RADIUS_SQ` (r^2=20), since a mender
tending a Core we are shooting is next to *that Core*, not next to us.

**Prefer kills, and prefer untended targets.** A shot that kills is permanent; a
shot that wounds is a down payment their mender refunds at 4 HP for 1 Ti. So rank
economy targets by (can I finish it this shot, is a Builder adjacent to it, class
value, HP) rather than by (class value, HP).

Neither changed a single game. The most likely reason is that the economy-target
path is reached rarely on this panel -- consistent with `STARVE_THE_ECONOMY=False`
also measuring inert, while disabling Sentinels wholesale costs 0.31. **The
Sentinel value on this panel is coming from the guard role, not the siege role.**
That is worth knowing before anyone else spends time on siege targeting.

## The one real inefficiency found, and why exploiting it failed

Instrumented at round 600 on quarry: **scale 520%, 6,374 titanium banked, 120
ammunition, harvester cost 104 Ti**.

The reasoning looked strong. Cost scale is a live census (+20% per Builder and
per turret, +5% per Harvester, +1% per conveyor) so construction gets worse value
all game, while `convert_ammo` is 1:1 and completely immune to scale -- at 520% a
Sentinel's 18 damage still costs exactly 10 ammunition, so titanium spent on
shooting buys 5.2x what titanium spent on building does. And `AMMO_TARGET` is a
flat cap that stops converting at 120 however rich we are.

It measured **worse** (0.750 at a 400 threshold; inert above 1000). The bank is
apparently not idle in the way the snapshot suggests -- sweeping it starves
construction the economy still wants, and raising `AMMO_TARGET` directly is worse
still (0.667 at 200, 0.597 at 320). Converting titanium to ammunition beyond
vidar's existing floor is simply a bad trade on this panel, twice over.

## Builder-round utilisation

Measured with a per-unit tally of moved / acted / idle rounds:

| unit | idle | moved | acted | over |
|---|---|---|---|---|
| id=3 (first Builder) | **394 (66%)** | 142 | 64 | 600 rounds |
| id=744 (late economy Builder) | 8 (2%) | 280 | 112 | 400 rounds |

Late Builders are near-fully utilised. The 66% idle unit is the parked guard,
which Lucas measured as load-bearing -- repairing it costs 9.9pp of mean and
14.2pp of worst matchup. So this is a known, deliberate inefficiency and not a
lead. Anyone tempted by those 394 rounds should read vidar's README first.

## Where I would look next

Not at vidar's constants; that space is exhausted from two independent
directions now. The remaining candidates, in order:

1. **Generated maps.** vidar scores 0.750 on the pool and 0.579 off it, with
   vigil at 0.402. The pool is tuned-over ground and the final is not. There is a
   generator at `maps/generated/generate_maps.py` on `x/luc` but no committed
   `.map26` files on this branch, so nothing here measured off-pool at all.
2. **The guard role, not the siege role.** That is where the 0.31 lives, and the
   only lever tried there was the count.
3. **A mechanism, not a knob.** Every knob tested is at its optimum, which is
   what a local optimum looks like from the inside.
