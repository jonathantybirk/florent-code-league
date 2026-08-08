# modulah log

## Status: NOT yet beating our own bots

`aegis` is **0/18** against `steward_hardened_reinforced`, `vidar` and `odin`
over 6 maps in both seats. It beats `starter` on the tiebreak. The goal is not
met.

What did move, same panel throughout:

| | beacon | aegis v1 | aegis now |
|---|---|---|---|
| wins vs top three | 0/12 | 0/18 | **0/18** |
| games survived | — | 7/24 | **9/24** |
| titanium collected | 937 | 786 | **2184** |
| harvesters @300 | — | 1.17 | **3.83** |
| first harvester | 3.5 | 30.5 | **3.5** (field: 6.5) |
| core hp at end | 39 | 142 | **200** |
| enemy cores killed | never | never | **round ~225** |

So: the economy is now competitive and we kill cores, but the top three still
kill ours around round 90 every time.

**The deployed online bot is untouched** — `v34
(steward_hardened_reinforced f1f2bda)`, team #12 of 109 at 1772. Nothing from
this branch has been submitted, and nothing should be until it beats the
flagship locally.

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

## Measured and rejected

- **Counter-battery by walking** — find a Sentinel seat near an enemy turret,
  walk a Builder to it. Lost on every axis (wins 6→5, collected 2121→1856,
  cores killed 233→never). The walk crosses the ground the siege covers.
- **`1/(1+d)` seat weighting** — replaced by betweenness. It cannot tell a
  corridor from a plaza, which is the whole question.

## Next, in priority order

1. **Why we die at round ~90.** Gunners reach 3 tiles, Sentinels 5. Steward
   shells from 5. Counter-battery from adjacent seats works but rarely
   triggers; the answer is probably a standing Sentinel ring sited *before*
   contact, not a reaction.
2. **Pathing.** `_step` is greedy and bounces; steward uses a BFS distance
   map. `worst_stall` is 62 rounds.
3. **Doctrine.** Steward branches RUSH/FORTIFY/BLITZ on Core-to-Core Chebyshev
   ≤ 6, measured over 138,785 matches. aegis has no opening at all.
4. **Bigger panel.** 6 maps is too noisy to resolve a 5pp change — steward's
   own log records five apparent gains that reversed sign on a second panel.

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
