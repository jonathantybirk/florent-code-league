# modulah log

## Status: NOT beating our own bots

`aegis` is **1/45** against `steward_hardened_reinforced`, `vidar` and `odin`
on the full 15-map official pool, both seats. The goal is not met.

**Measure on the full pool, never on a small panel.** The early 6-map panel is
four old-pool 12x12s and flatters this bot badly — it reported 2184 collected
and 200 core hp where the real figures were 823 and 47.

| | aegis now | steward |
|---|---|---|
| wins vs top three | **1/45** | — |
| titanium collected | **823–933** | 788 |
| harvesters @300 | **3.76** | 2.3 |
| first harvester | round 4 | 7 |
| launchers built | 1.9 | 1.7 |
| **first gunner** | **round 72** | **round 25** |
| games survived | 5/45 | — |
| core hp at end | 12 | 500 |

**The economy is no longer the gap — it is ahead of steward.** What remains is
that we are defenceless for the first ~70 rounds and die at 90–105.

**The deployed online bot is untouched** — `v34
(steward_hardened_reinforced f1f2bda)`, team #12 of 109 at 1772.

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
| **+ Barrier screening (kept)** | 823 | 5/45 | **1** |
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
faults by construction: the chain is attached to the Core from its first tile
so partial progress is never a liability, the Builder only ever has to reach
the tile beside the chain end rather than follow a route, and the Harvester is
built LAST so a stranded one cannot exist.

It collected 341. The reason is tempo, not correctness: the first Harvester
slipped from round 4 to round 8 and the team finished with 1.6 Harvesters
against 4.5, because nothing mines until the whole line is finished. Building
the route first is strictly safer and strictly slower, and on this map pool
slower loses by more than stranding costs.

Which closes the loop on chain-laying. Laying behind a wandering Builder
works but wastes conveyors; laying a frozen plan cannot survive being pushed
off it; laying outward is too slow to start. The remaining option nobody has
tried is to keep the current lay-as-you-walk and make the WALK straighter --
the chain is only crooked because the walk out was.

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
