# modulah log

## Status: 3/45 against our best three — still short, but moving

`aegis` on the full 15-map official pool, both seats, vs
`steward_hardened_reinforced`, `vidar`, `odin`.

| | early session | now |
|---|---|---|
| **wins** | 0/45 | **3/45** |
| titanium collected | 823 | **977** (steward 788) |
| conveyors built | 11.7 | **25.6** (steward 12.1) |
| harvesters built | 4.5 | 4.8 |
| enemy cores killed | never | **round 389** |
| first harvester | round 4 | round 4 (field: 7) |

**Measure on the full pool, never on a small panel.** The early 6-map panel is
four old-pool 12x12s and inflated this bot badly (reported 2184 collected and
200 core hp where the real figures were 823 and 47).

**The deployed online bot is untouched** — `v34
(steward_hardened_reinforced f1f2bda)`, team #12 of 109.

### What unlocked it: publishing connectivity

A Builder sees radius ~4.5 and cannot tell a conveyor that delivers from one
that is stranded. That single blind spot was underneath every economic failure
in this log. The Core can tell — `econ.py` already walks the network backward
every round — so `econ.network_frontier` publishes the connected tile furthest
out, in the threat word's spare bits (19–27), costing no slot.

**It invalidated four earlier negative results.** "More Harvesters collects
less titanium" was measured four times on a bot whose chains did not connect,
where each extra Harvester mined into nothing and bought cost scale for the
privilege. With connectivity published, both economic levers reverse:

| change | before fix | after fix |
|---|---|---|
| ECON_FLOOR 4 → 7 | — | survived 6→8, hp 30→37.6 |
| SPAWN_INTERVAL 12 → 6 | 246 collected, rejected | **977 collected, 3 wins** |

A negative result is only as good as the build it was measured on.

### Trap: `barriers_built` and the replay decoder both miss Barriers

`benchmarks` reports `a_barriers_built = 0` in every game, and the replay
decoder labels the entity `unknown{18}` — `BARRIER` is the one `EntityType`
neither of them names. On that evidence the Barrier screen looked like dead
code that had never fired, and it was one commit from being deleted as such.

Removing it is what proved otherwise: **wins 3 → 2, core hp at end 23.8 →
12.6, games survived 5 → 3.** The replays carry 1–3 `unknown{18}` entities a
game on our side; those are the Barriers, doing exactly the job they were
built for (30 hp soaking a Gunner's 7 damage, five shots for 3 Ti).

Two lessons, both cheap to repeat: a metric reading zero is not evidence a
feature is dead until you have checked the metric exists AND resolves the
entity, and the fastest way to test whether code matters is to delete it and
measure.

### The blitz threshold: 6 transfers, 9 does not

Core-to-core Chebyshev distance is the one predictor of opponent behaviour
available at round 0 — from the pool's rotational symmetry, needing no
scouting and impossible for the opponent to disguise. Every damage-based
signal fails because it only exists after the damage starts, by which point a
30 Ti Sentinel cannot be placed in time.

Measured across the official pool: fjordgate 5, meander 8, antler 9,
lighthouse 9, everything else 10–20. Steward's threshold is 6, measured on a
different bot, so it was re-tested rather than inherited:

| threshold | wins | collected | new blitz maps |
|---|---|---|---|
| **6** (fjordgate only) | **4/45** | **983** | — |
| 9 | 3/45 | 665 | meander 0/6, antler 0/6, lighthouse 0/6 |

All three added maps lose outright and the economy damage costs an odin
tiebreak on top. Six is right for this bot too — at eight or nine tiles an
attacker arrives with nothing behind it, exactly as steward's own note said.

### Where the wins actually come from

Per-opponent, 30 games each (15 maps, both seats):

| build | odin | vidar | steward |
|---|---|---|---|
| **shipped** | **3/30** | 0/30 | **0/30** |
| home counter-battery | 1/30 | **2/30** | 0/30 |

**All our wins are against odin, and we are 0/30 against steward.** Two of the
three are round-1000 tiebreaks — when we survive, we win. So survival against
steward and vidar is the whole remaining problem.

Counter-battery *moves* wins rather than adding them: it bought the first
victories ever recorded against vidar and lost two odin tiebreaks, because 30
Ti a Sentinel cut collected 977 → 842. Gating it on actually taking damage
changed nothing (`max_burst` is already non-zero whenever a turret is
positioned), so the two are genuinely a trade, not a tuning error.

That is the shape of the "advanced conditional logic" the top teams show: the
right answer differs by opponent, and a single fixed policy leaves wins on the
table either way.

**Three gates were tried to get both, and none worked:**

| gate | fires when | result |
|---|---|---|
| `burst > 0` | a turret is merely POSITIONED | always true — trades odin for vidar |
| `dhp <= -2` | sustained hp loss | never coincides with holding GUARD (menders are assigned first) — no-op |
| `hp < 400` | accumulated damage | fires too late to place a Sentinel — no-op |

The two "no-op" gates produced numbers byte-identical to the ungated build,
which is how you can tell they never fired at all.

The reason none work is timing, not signal quality. Counter-battery is only
worth 30 Ti if the Sentinel is standing *before* the damage lands, and every
signal that distinguishes a real siege from posturing is by definition only
available *after* it starts. Adapting to the opponent needs a predictor
available early — their opening shape, not their damage output.

### The ladder's actual standard

sporks (#1, 2117) and Pantheon (#2) build **41–97 conveyors** a game, first
conveyor on round 1–6, first Sentinel by round 5–19, and end games on a Core
kill at rounds 117–346. We are at 25.6 conveyors and a first Gunner around
round 76. Infrastructure volume is the meta; steward is not the standard.

### Limits found, in order

1. **Ore discovery.** Raising ECON_FLOOR past 7 changes nothing — the team
   only builds ~4.8 Harvesters. Builders cannot find more ore, so the economy
   caps well below the leaders' 7–17.

   Broadcasting an ore BEARING was tried (3 bits of direction + 3 of distance
   from the Core anchor, in the Builder word's spare bits — Viktor's chunking
   idea, on the grounds that exact coordinates are unnecessary for something
   far away). It measured **worse**: wins 3→1, collected 977→533, survived
   5→2. A bearing sends a Builder several rounds across the map to ground that
   may hold nothing by the time it arrives, and the walk costs more than the
   deposit is worth. Exact coordinates would need 12 bits against 8 spare, so
   a second slot; whether that pays is untested.
2. **First turret at ~round 76** against the leaders' round 5–19.

   Retested on the repaired economy (a standing Gunner as soon as one
   Harvester works, no threat required — the same change rejected five times
   on the broken build). It is now **close to worth it**:

   | | shipped | early defence |
   |---|---|---|
   | wins | **3/45** | 2/45 |
   | collected | 977 | **1098** |
   | core hp at end | 23.8 | **38.4** |
   | games survived | 5/45 | **6/45** |
   | first gunner | 76 | **63** |

   Better on every proxy, one fewer win. Not shipped, because wins is the
   objective and proxies do not get to overrule it — but this is the closest
   any defensive change has come, and it should be the first thing retried
   after the next economic gain.

3. **Builders are not dying** (0–1 deaths a game, mean life 81–93 rounds) and
   the economy is now at parity with steward: 5 Harvesters and 29–46 conveyors
   against its 3–4 and 34–38. Every game still ends `core_destroyed` at round
   ~100. The remaining gap is defensive, not economic, and not attrition.
3. SPAWN_INTERVAL 3 with a smaller bank overshoots: wins 3→1, survived 5→1.
   Six is the measured optimum.

## Bugs found, in order of how much they cost

Each produced plausible behaviour and none was visible in a win rate.

1. **Mined literally zero.** `_mine` re-anchored `trail` to the current
   position every turn, so the conveyor branch was unreachable.
2. **Turrets never fired a single shot** in a whole match — four standing, 60
   ammo, 8–11 visible targets. They were Sentinels, whose facing is permanent
   (`can_rotate` is Gunner-only), sited by approach-betweenness at corridors
   nobody used.
3. **One Harvester per Builder, forever.** A miner that finished its route
   kept re-laying instead of opening another deposit, so we lost tiebreaks in
   games we had already survived.
4. **Role rank was not dense** — slots claimed scattered, so a Builder on slot
   9 ranked 5 and never fell inside a two-role mix. Every Builder read MINER
   at `dhp = -16`.
5. **Menders unbounded** — 4 Builders all mending a 16/round rush, no turret
   ever built.
6. **Ammo never converted**, so turrets were decoration.
7. **Exploration was "first legal cardinal"** — walk north into a wall, vibrate.

## Measured ledger — 20 changes, 5 helped

Full pool, both seats, vs steward/vidar/odin. Harness is deterministic (a
repeat run reproduced 823.33 collected to the decimal).

| change | collected | survived | wins |
|---|---|---|---|
| baseline | 823 | 7/45 | 0 |
| **+ rear-corner ore ranking** | 878 | 6/45 | **1** |
| **+ Launcher (ferry Builders)** | **933** | 4/45 | 0 |
| **+ consume the published turret map** | 933 | 5/45 | 0 |
| **+ Barrier screening** | 823 | 5/45 | **1** |
| — removing it, to check | 979 | 3/45 | 2 |
| **+ connectivity broadcast** | 568 | 6/45 | 2 |
| **+ blitz doctrine (kept)** | **983** | 5/45 | **4** |
| blitz threshold widened to 9 | 665 | 3/45 | 3 |
| siege role (kept, off by default) | 809 | 7/45 | 1 |
| turret map, all 8 facings (bug) | 256 | 1/45 | 0 |
| BFS navigation (all movement) | 387 | 3/45 | 0 |
| BFS + bearing fallback | 472 | 4/45 | 0 |
| BFS for the guard's walk only | 596 | 6/45 | 1 |
| home-seat counter-battery | 375 | 2/45 | 0 |
| aggressive economic scale | 246 | 1/45 | 0 |
| planned route from recorded walk | 112 | 0/45 | 0 |
| unconditional early guard | 491 | 5/45 | 0 |
| guards from top ranks | 261 | 3/45 | 0 |
| opening turret, zero walk | 305 | 4/45 | 0 |
| opening turret + Launcher economy | 213 | 2/45 | 0 |
| workforce capped at 4 builders | 763 | 6/45 | 0 |
| opening spawn burst (3 fast) | 522 | 2/45 | 0 |
| chain-length cap (neutral) | 821 | 5/45 | 1 |
| planned route, de-looped walk | **27** | 1/45 | 0 |
| supply line grown outward | 341 | 2/45 | 1 |
| deposits capped to 4 tiles | 660 | 4/45 | 0 |
| chains join nearest friendly sink | 307 | 4/45 | 1 |
| scouts round-robin sightings | 660 | 5/45 | 0 |
| scouts, idle Builders only | 691 | 4/45 | 0 |
| walking counter-battery | — | — | worse |
| Sentinels in standing ring | — | — | worse |

### The team's scouting proposal, measured

Implemented from the thread: Lucas's round-robin precise coordinates plus
Viktor's periodicity, as one mode bit in the Builder word — a Builder reports
its own destination most rounds and an enemy sighting every 4th, staggered by
slot so the team sweeps continuously. No extra store slot, which matters
because slots are the scarce resource (one writer each, forced by the engine).

The conditional it enabled was the right shape: buy a turret when a SCOUT sees
a Gunner going up, rather than when our own hp starts falling. That is not
building on a timer — five timer variants each lost 300–700 titanium — because
nothing is bought unless something was actually seen.

It still lost: **660 collected, 0 wins** against the 823/1 baseline. The first
version also displaced the ferry target (the Launcher routes by reading
published targets), blinding it a quarter of the time and pushing the first
Gunner from round 72 to 84. Restricting sightings to Builders with no
destination fixed the ferry and recovered only 691.

Worth knowing for the group: the idea is sound and the encoding works, but
this bot cannot convert early warning into anything, because it still cannot
AFFORD the turret when the warning arrives. Warning is not the missing
ingredient — spare titanium at round 30 is. Reverted rather than left in.

**What worked were the two structural additions** — a Launcher (the only way
to move a Builder faster than walking) and a Barrier screen (3 Ti soaking five
Gunner shots). **What never worked was scheduling defence earlier**: five
separate routes, every one paying 300–700 titanium for ~15–28 rounds of turret
timing.

### The one result that reproduces every time

**Raising the Harvester count always LOWERS titanium collected.** Four
independent routes:

| change | harvesters@300 | collected |
|---|---|---|
| baseline | 3.76 | **823** |
| workforce capped at 4 | — | 763 |
| aggressive economic scale | — | 246 |
| opening spawn burst | **3.93** (highest ever) | 522 |

More Harvesters, less titanium, every time. The Harvesters are not the
problem — the routes behind them never connect. A Builder laying one conveyor
per step across a 26x26 map abandons more chains than it finishes.

Capping deposits to a route we can finish (8 tiles) measured **neutral**
(821), which places the fault in the LAYING, not in the distance: the
short-route deposits were already being picked by the rear-corner ranking.
The remaining fix is a Builder that plans a route and lays it in one
uninterrupted trip. **That has now been attempted properly and it also
fails.**

The plan was to record the walk out, remove the excursions (a unit-tested
de-looper: `A B C D C B E F` -> `A B E F`), then walk the simplified route
home laying each tile at its true successor's bearing -- which fixes bends,
where laying-as-you-walk must choose a facing a turn before it knows where the
route goes.

The de-looper is correct and the mechanism half-works: one archipelago match
mined 990 and won on the tiebreak. Across the pool it collected **27**. It
also shipped with a bug worth recording -- the loop exited on the last route
tile without ever laying it INTO the Core, so every chain stopped one tile
short: 12 conveyors a game and literally zero titanium delivered. Fixing that
took the pool from 0 to 27, which is the measure of how far off the rest of it
still is.

Why it fails is now the interesting question, and it is not the plan: it is
that a Builder cannot FOLLOW a frozen route. It gets blocked, shoved, or
shot off the path, and every deviation invalidates the plan it is carrying.
A route that must be walked exactly is the wrong abstraction for a unit that
does not control where it can stand. Growing the line OUTWARD from the Core was then tried, which fixes both known
faults by construction. It collected 341: the first Harvester slipped round 4
to 8 and the team finished on 1.6 Harvesters against 4.5, because nothing
mines until the line is done. Strictly safer, strictly slower.

### What the top of the ladder actually does

Replays of sporks (#1, 2117) vs Pantheon (#2, 2025), per game:

| | conveyors | harvesters | first conveyor | first turret |
|---|---|---|---|---|
| sporks | **97** / 41 / 38 | **17** / 7 / 4 | round **1**–6 | sentinel @5–19 |
| Pantheon | 22 / 13 / 8 | 2–3 | round 5–10 | gunner @36 |
| **aegis** | **11** | 4.5 | ~8 | gunner @**72** |

**Infrastructure volume is the meta.** The #1 team lays 97 conveyors in a game
where we lay 11, starts laying on round 1, and has a Sentinel up by round 5.
Their games end on a Core kill at rounds 117–346, so this is not a
turtle-and-tiebreak strategy — the economy funds a kill.

This reframes everything below. aegis out-collects *steward* but steward is
not the standard; the ladder leaders build an order of magnitude more
logistics than either of us.

### CORRECTION: the chains are not crooked, they barely exist

An earlier version of this file blamed wasteful, wandering chains. **A replay
audit says the opposite.** Conveyors actually built against conveyor tiles
*needed* to connect the Harvesters that exist:

| map | harvesters | conveyors built | tiles needed |
|---|---|---|---|
| archipelago | 7 | 14 | **28** |
| drumlin | 4 | **4** | **40** |
| nordkap | 3 | 4 | **17** |

Chains are not wasteful, they are **absent**. On drumlin four Harvesters share
four conveyors against forty tiles of need. Most Harvesters have no route home
at all, which is the entire content of "more Harvesters, less titanium"
measured four separate times: those Harvesters were never connected to
anything.

This also kills the "make the walk straighter" idea the previous version of
this file ended on — a staircase and an L-path have identical Manhattan
length, so a straighter walk cannot shorten a chain. That conclusion was
wrong.

Capping deposits to a route we finish was tried at both 8 tiles (neutral, 821)
and 4 tiles (worse, 660 — near ore runs out and Builders idle). So refusing
distant deposits is not the answer either. **The Builder needs to keep laying
until the route is done rather than being pulled off it.** Traced on drumlin:
only the FIRST chain a Builder lays ever gets built. After that it walks home
over its own existing conveyors, `can_build_conveyor` fails on every occupied
tile, and it arrives having built nothing — stranding every Harvester after
the first.

Routing to the nearest friendly conveyor instead of to the Core fixed that in
isolation (drumlin vs starter: 0 → 9,510 mined) and still lost on the pool at
307, with the highest infrastructure yet (14.7 conveyors, 5.3 Harvesters,
harvesters@300 3.98). The reason is the next layer down: any friendly conveyor
counts as a sink, so Builders join each other's *unconnected* chains and build
a web that never reaches the Core.

**The missing primitive was connectivity, and publishing it worked.** A
Builder cannot tell a delivering conveyor from a stranded one; the Core can,
because `econ.py` already walks the network backward every round for the
arrival schedule. `econ.network_frontier` returns the connected tile furthest
from the Core and it rides in the threat word's spare bits (19–27) rather than
costing a slot.

Builders now extend the CONNECTED network instead of guessing:

| | baseline | connectivity broadcast |
|---|---|---|
| wins | 1/45 | **2/45** |
| core hp at end | 12 | **30** |
| games survived | 5/45 | **6/45** |
| conveyors built | 11.7 | **19.4** |
| enemy cores killed | never | **round 676** |

Titanium collected fell (823 → 568) and everything that decides games improved.
That trade is the point: the earlier 823 was banked by a bot that died, and
`collected` was never the objective.

This is the first time published information has changed an outcome rather
than decorating one. The scouting experiment failed because early warning
unblocked no decision; connectivity unblocks a decision a Builder physically
cannot make alone.

### The gap, measured

aegis already **out-collects steward** (878 vs 788) and still loses every game.
The difference is entirely military timing:

| | aegis | steward |
|---|---|---|
| first gunner | round 77 | **round 25** |
| gunners built | 3.4 | 4.4 |
| launchers built | 0.0 | 1.7 |
| harvesters built | 4.4 | 2.3 |
| builders spawned | 5.6 | 3.7 |

Traced on archipelago: a guard takes the role at round 26 and **never places
anything** — picks a seat, walks, stalls after 8 rounds, re-picks. The first
turret arrives at 73, from a different Builder.

**Four independent routes to an earlier turret were tried and all cost more
than they returned**, in order of how directly they attacked the problem:

| route | first gunner | collected |
|---|---|---|
| baseline | 77 | 878 |
| earlier guard assignment | 62 | 491 |
| guards from top ranks | 54 | 261 |
| BFS routing to the seat | 74 | 596 |
| opening turret, zero walk, no roles | **49** | **305** |

The last one has no walk, no seat search across the map, no commitment to
stall, and spends the opening bank while it is still full — and it still costs
500 titanium. `can_build_gunner` is also False on every tile around the Core,
verified, so a Builder is required and the Core cannot do it itself.

The conclusion is not about scheduling. **aegis cannot afford an early turret
and steward can**, because steward's opening is more efficient overall: it
reaches the same board position on 2.3 Harvesters and 3.7 Builders where we
need 4.4 and 5.6. Buying defence earlier is not the fix; needing fewer
Builders to hold the same economy is.

## Next, in priority order

The ledger says stop adding combat behaviour and fix the supply line.

1. **Chain completion.** The measured binding constraint. Routes are laid one
   conveyor per step as a Builder walks home, so they are slow, fragile, and
   follow the Builder's wander rather than a plan. Plan the route first, then
   lay it — and prefer deposits whose route is short, which produced the only
   win so far.
2. **Survive the Gunner siege.** 94-100% of Core damage is enemy Gunners at
   reach 3. Every reactive answer tried has cost more than it saved, so the
   answer is probably structural: enough standing defence bought early from a
   working economy, not a Builder despatched on contact.
3. **Doctrine.** All 15 official maps are rotationally symmetric, so the enemy
   Core is our Core rotated 180° about the map centre — available at round 0
   from map dimensions alone. steward branches RUSH/FORTIFY/BLITZ on
   Core-to-Core Chebyshev ≤ 6, measured over 138,785 matches. aegis has no
   opening at all.

## Engine facts (measured, not from docs — the docs contradict themselves)

- Conveyors move **once per round, after every unit has acted**
  (`distribute_resources` between the unit loop and `update_cooldowns`).
- A stack `h` hops out is credited at `T+h`. Verified at h=1; congestion is
  arbitrated by `edge_priority` (per-edge LRU + uniform random tie-break).
- A Splitter with one accepting output delivers **identically to a Conveyor**
  (144 stacks each over 575 rounds). Weight is 1/k over *accepting* outputs.
- A Conveyor pointing at bare ground **holds its stack forever**.
- Store writes land **next round**, invisible to later-id units in the same
  round → one writer per slot is forced.
- Turrets are **line weapons**: Gunner 3 cardinal / 2 diagonal, Sentinel 5 / 4
  (`dist_sq` 25 / **32**). Core vision 36 — sees everything that can shoot it,
  margin 4. **Only Gunners can rotate.**
- Core vision is the **union** of radius-6 discs over the 2×2 footprint (140
  tiles, not 113). Walls do not occlude.

## Layout

`lib/` is canonical; `vendor.py --check` detects drift into the bot dirs.
`diag` re-verifies the engine facts (8/8) — run it after every fcode bump.
Read econ with `comms.arrivals_from_now()`, never `unpack_econ()`.
