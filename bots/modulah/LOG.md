# modulah log

## Status: NOT beating our own bots

`aegis` is **0/45** against `steward_hardened_reinforced`, `vidar` and `odin`
on the full 15-map official pool, both seats. The goal is not met.

**Measure on the full pool, never on a small panel.** The 6-map panel used
early on (duel, atoll, hive, jackpot, eider, saga) is four old-pool 12x12s and
flatters this bot badly — it reported 2184 collected and 200 core hp where the
real figures are 823 and 47. Every number in this file is full-pool.

| | full pool |
|---|---|
| wins vs top three | **0/45** |
| games survived | 7/45 |
| titanium collected | 823 (steward 788, vidar 4003, odin 2109) |
| harvesters @300 | 3.29 |
| first harvester | round 4 (field: 7) |
| core hp at end | 47 |

The opening is genuinely good — first Harvester at round 4 against the field's
7 — and the economy is level with steward. vidar out-collects us five to one.
The top three kill our Core around round 90-105 in every single game.

**The deployed online bot is untouched** — `v34
(steward_hardened_reinforced f1f2bda)`, team #12 of 109 at 1772. Nothing from
this branch has been submitted, and nothing should be until it beats the
flagship on this pool.

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

## Measured and rejected — the full record

All on the 15-map official pool, both seats, vs steward/vidar/odin. The
harness is deterministic (a repeat run reproduced 823.33 collected exactly),
so these are real differences, not noise.

| change | collected | hp end | survived | wins |
|---|---|---|---|---|
| **baseline (shipped)** | **823** | **47** | **7/45** | **0** |
| walking counter-battery | 1856* | — | — | 5* |
| Sentinels in standing ring | — | — | — | worse on every map |
| BFS navigation | 387 | 8 | 3/45 | 0 |
| BFS + bearing fallback | 472 | 19 | 4/45 | 0 |
| home-seat counter-battery | 375 | 12 | 2/45 | 0 |
| aggressive economic scale | 246 | 3 | 1/45 | 0 |
| ore chosen by chain cost | 777 | 15 | 4/45 | **1** |
| planned route from recorded walk | 112 | 0 | 0/45 | 0 |

\* measured on the old 6-map panel before it was found to be unrepresentative.

**The pattern.** Eight of nine measured worse. Every change that diverts a
Builder from mining — to counter-battery, to a distant seat, to a longer walk
— costs more economy than the threat it answers costs us. At this unit count
Builders are too scarce to spend on reacting, and out-mining plus mending
beats fighting back badly.

The one that produced a win (ore chosen by distance-to-Core, so chains are
short) also cut survival 7→4 and core hp 47→15. Reverted: one lucky matchup
against a bot closer to death everywhere else.

The planned-route attempt is the sharpest failure and worth understanding.
The idea was sound and cheap — the Builder has already walked from the Core to
the deposit, so the reverse of that walk is a route guaranteed passable and no
longer than the walk. Against `starter` it worked (archipelago 6,330 mined;
eider 10,960). Against the real field it collapsed to 112 titanium and 0
survivals with the HIGHEST harvester count yet recorded (3.64 at round 100).

Deposits opened, nothing delivered. Under pressure the Builder is interrupted
part-way along a rigid route and the remembered path goes stale — the tiles it
walked are no longer free, or it is no longer near them. The lay-behind
version is worse in principle and more robust in practice, because it only
ever commits to the one tile it is standing next to.

**The diagnosis that actually held up.** Replay attribution across four
losses: enemy GUNNERS deal 94-100% of all damage to our Core (archipelago
882/938, drumlin 490/504, nordkap 539/546, heart 504/504). Reach 3, so they
are planted inside our own back yard. And raising Harvester count pushed
harvesters@100 3.31 -> 4.13 while collected FELL 823 -> 246 — more Harvesters,
less titanium, because they are stranded. **Chain completion, not harvester
count, is the binding constraint.**

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
