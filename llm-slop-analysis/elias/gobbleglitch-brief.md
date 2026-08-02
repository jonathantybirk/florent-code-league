# GobbleGlitch — design brief

Successor to AutistimusPrime. Written against `fcode 2.3.3`, the 21-map pool, and the four exploit hunts
of this session. Every number below is either quoted from a hunter's engine run or recomputed here from
the `.map26` files; where I recomputed something the hunters asserted, I say so and give both figures.

Companion documents: `ground-truth.md` (engine claims), `game-objects.md` (constants), `backlog.md`
(what already failed), `exploits/HARNESS.md` (how to probe without losing the data).

---

## 1. What GobbleGlitch is for

### The verdict: rewrite the control flow, port four named subsystems

**Rewrite.** Not because 3 500 lines is distasteful, but because the adversarial audit proved that at this
size *we cannot see our own bot*, and every one of the three engine-assumption reversals left fossils that
survived 210 games of play without anybody noticing.

The audit (`bots/cand/audit`, 5 opponents × 42 mirrored games) found **twelve named counters at exactly
zero**:

| Counter | What it gates | Executions in 210 games |
|---|---|---|
| `T_sentinel` | `_run_sentinel`, 23 lines | 0 — **unreachable by construction**, `bot/` contains no `build_sentinel` call anywhere |
| `R_build_conveyor_ok/no`, `R_build_harvester_ok/no` | two arms of the rush executor, 9 lines | 0 — `siege.plan` has emitted only `("gunner",…)` since 2.3.3 |
| `R_clearray` | `_clear_ray`, 16 lines | 0 |
| `G_friendly` | the friendly-in-ray hold-fire guard | 0 — twelve lines of docstring for a branch that has never fired |
| `G_cantfire`, `G_exc`, `S_cantfire`, `E_capped`, `E_noanchor` | error and cap paths | 0 |

and five more below 0.2 per game: `_hold_home`'s fortify branch (**8 barriers in 210 games**),
`_snipe` (~81 lines, **31 shots in 210 games**), `_repair_chain` (25, all against one opponent),
`R_heal` (8), and the `STEP_SEEK` rung of the builder ladder (**2 in 210 games**).

Add `bot/atlas.py`: 335 lines that `identify()` fails on for 6 of 21 maps (G65), which is 29% of the pool.
Conservatively **~665 lines — 19% of the codebase — is inert or actively wrong**, and none of it was
visible until somebody built an instrumented fork and played 210 games to find it.

Three things make this an argument for rewrite rather than for a cleanup pass:

1. **The dead code is structural, not incidental.** `_run_sentinel`, the conveyor/harvester rush arms and
   `_clear_ray` are precisely the fossils of the ammo-model change (G52/G53), the builder-radius reversal
   (G50 → G59) and the Sentinel-arc reversal (G15). A refactor preserves the shape that hid them. The next
   engine bump will deposit a new layer in the same place.
2. **The concealment was cheap to defeat and nobody defeated it.** `_run_sentinel` was unreachable because
   no call site exists. One `grep build_sentinel bot/` answers that in a second. Nobody ran it, because at
   2 755 lines in a single file nobody holds a model of the whole.
3. **The audit trail has already failed in public.** `bot/main.py:157` reads `BUILDERS = 3`, directly under
   a comment block whose own sweep table concludes *"Six is the pick"* (`4 → 19-11 | 5 → 22-8 | 6 → 23-7 |
   7 → 27-3`). Nothing in the file explains the change. A constant and its justification have drifted apart
   inside the same comment block.

### The risk, priced honestly

The current record — 83% on published maps, 69% on unseen — is real and a rewrite puts it at stake. But the
audit tells us what carries it: **one geometric event.** Roughly 30 of every 32 wins per 42 games are
`core_destroyed` at turn 25-52, and the telemetry shows those kills are made at range 1, on the victim's own
Core ring (`siege.STANDOFF_PENALTY = 6` per tile of standoff makes range 1 always preferred, and range 1
onto a 2×2 footprint *is* a ring tile by definition). That event lives in `siege.rank`, `_plan_rush`,
`_run_rush`, `_rush_walk` and `_bfs_step` — call it 400 lines.

**Port those. Discard the rest.** The risk is bounded to one subsystem, and the subsystem is the one with
the strongest evidence in the repo.

### What else to port, and what to delete outright

| Port | Why |
|---|---|
| The runtime siege planner's geometry (`siege.py`), **minus the ore-adjacency filter** | It is the measured win condition. G57 already killed ore adjacency: a forward Gunner kills a 500 HP Core on a map with **zero ore tiles**, funded entirely by `convert_ammo`, for ~162 Ti. The filter now discards most legal firing positions for no benefit. |
| BFS / nav-field movement | `levers.md` records this as the dominant term of the last rewrite, and it was on nobody's list. |
| The 16-slot store protocol | Cross-unit state has no other channel (G20, M07). |
| The damage-quantum detector | Already written in `tools/apply_detector_2_3_3.py`, measured over 270 games, **never shipped**. See §4. |

| Delete | Why |
|---|---|
| `bot/atlas.py`, all 335 lines | Returns `None` on 29% of the pool (G65). The runtime planner *is* the unseen-map path (backlog N1) — keep one code path, not two, so the unseen case is the case we test every game. |
| `_snipe`, `_clear_ray`, `_run_sentinel`, the conveyor/harvester rush arms, the friendly-in-ray guard | Measured zero or near-zero over 210 games. |

**Hard cap: 900 lines across all files.** `tempest_fast` — the bot actually on the ladder — is 782
non-comment lines. `vanguard`, which beats the entire field, is 1 389. Neither needs 2 755 in one file.

---

## 2. The exploit shortlist

Ranked by (expected effect) / (implementation cost). Every entry states its evidence class. **`LAB` means
it was only ever demonstrated on a generated arena against a scripted victim** and has no real-game result
behind it; **`FIELD` means it fired in a match against a bot from `bots/rivals/`**; **`ARITH` means it is a
property of the map files or the constants, recomputed here.**

---

### Tier 1 — build these first. Cheap, general, and the evidence is arithmetic.

#### E1. Retire spent units and buildings — `LAB` mechanism, `FIELD` waste measurement
**~15 lines. The highest effect-per-line in any of the four reports.**

The cost scale is a **live-entity census**, not a cumulative counter, and it refunds the moment an entity
leaves the board — by `self_destruct()`, by `destroy()`, or by dying to damage.

- `gg_econ`: scale walked 130 → 150 → 170 → 190 → 210 on builds, then **210 → 190 → 170 → 150 inside one
  round** as three builders self-destructed.
- `gg_dest`: `destroy()` on our own buildings gives back conveyor −1pp, conveyor −1pp, barrier −1pp,
  harvester −5pp, with `dTi=0` and **`cd=0` throughout — three destroys in a single round**.
- `a2count` walked it back to baseline exactly: `sent u3 s146 | -harv u3 s141 | -splt u3 s140 | -sent u2 s120`.
- `a2scale` proved death does it too: `gun=131 … DEAD r8 scale=130.0`.
- `gg_misc`: a **turret** can self-destruct (gunner, 130 → 120).

**What it buys, from real-game telemetry.** The audit measured `V_built` = **3.2-3.8 Launchers built per
game** for `W_ferry` = **1.6-1.9 actual throws**. Each Launcher is +10 percentage points of *permanent*
global cost scale (G07). Destroying each one the round after its throw recovers **~20-35pp per game**. At
200% scale a Gunner costs 20 Ti instead of 10 and a builder 60 instead of 30; the cumulative cost of twelve
builders is **756 Ti, not 360**.

Two hunters proved this independently (Area 2 F4/F5, Area 3 (e)) and it is documented behaviour
(`game-rules-resources.txt:21`), so it will not be patched. **No bot in `bots/rivals/` calls `destroy()` or
`self_destruct()` at all** — `get_scale_percent` appears in `undertow` and `vanguard` only inside DEBUG log
strings.

*Honest limit:* the scale arithmetic is lab-measured; the win-rate consequence is inferred. The waste it
recovers, however, was measured in 210 real games.

#### E2. One definition of "occupied", and it must include bodies — `FIELD`
**~5 lines of code, but it is an architecture rule, not a patch.**

`bot/main.py:1191`: `occupant = self._building_at(ct, bpos)` — and nothing else. `_bot_at` exists 600 lines
away and is never consulted here. A Builder Bot is not a building, so a parked enemy body passes the
occupancy check, the executor walks adjacent, `can_build_gunner` refuses, the branch spends the round and
returns `True`, and `rush_stuck` is never touched.

Measured consequence, `a4sit` (six builders parked on ring tiles, never moving or building again):

```
R_build_gunner_ok        4   across 42 games
R_build_gunner_no    47695   (1 136 per game)
games with ZERO gunner  41/42
```

**One 30-titanium body, never moved again, deletes the entire offence for 1 000 rounds.** This is the
largest single measured effect anywhere in the four reports.

Note carefully what this is *not*: `a4sit` loses **0-42 to `tempest_fast`, 0-42 to `vanguard` and 0-42 to
`mistral`** — everyone else shoots a 40 HP body in four shots. It exploits one defect in one bot. Per the
standing principle we build **the immunity, never the tactic**.

The fix is not just consulting `_bot_at`. It is that the planner (`siege.rank`, strict: any building in the
ray discards the site) and the executor (permissive: buildings ignored entirely) hold two different
definitions of "occupied" in two different files. Give them one, in a shared module, and price a blocked
lane as **three shots of work** (a 30 HP barrier at 10 dmg/shot) rather than as infinity.

#### E3. Occupy our own Core ring — `LAB` for the denial, `FIELD` for the survival delta
**~70 lines.**

A Core whose ring is fully occupied by buildings cannot be shot by any Gunner or Sentinel from anywhere on
the board. `a4ring` on arena `ringlab`, sweeping `can_fire_from` over every buildable tile within 6 × 8
facings:

```
ringocc  0/12  -> 38 sites, 46 (pos,facing) pairs can fire at the Core
ringocc 12/12  -> 0 sites,  0 pairs
```

The geometry is exact: a 2×2 footprint is bounded by exactly 12 tiles; every cardinal or diagonal line
ending on a footprint tile passes through one of them; a building both blocks the line and absorbs the
shot; and a turret cannot be sited on an occupied tile.

**Correction nobody reported — the ring is not always 12 tiles.** All three hunters who touched this
(Area 2 F7 `ring=12`, Area 3 bonus "all 12 tiles", Area 4 M1 `12/12`) used lab arenas with interior Cores.
Recomputed over the real pool:

```
ring tiles per map-side: min=5  max=12  mean=10.3
5-tile rings: bridge, jackpot, string, sweden, vase  (Core flush against a map edge, G64a)
```

So the cost model "12 barriers, ~36 Ti, +12pp" is **wrong on 5 of 21 maps** — there it is **5 barriers,
~15 Ti, +5pp**, and those are exactly the wall-dense maps G64 added and the bot was never tuned on. Compute
the ring at runtime; never hardcode 12.

**What it actually buys, split honestly:**
- *Against any turret-based attacker* (`FIELD`): median death turn moves `tempest_fast` 33 → 42,
  `vanguard` 44 → 58, `undertow` → 68. That is 10-15 rounds. It is arithmetic: 12 barriers = 360 HP =
  ~36 Gunner shots.
- *Against a rusher of AutistimusPrime's shape* (`FIELD`): its core kills fall from 30-34 per 42 games to
  **2**, and 38 of 42 games end with it having built zero gunners while banking 2 550-9 647 titanium.

**Do not quote the "38 → 0" and the "10-15 rounds" together without the distinction.** The zero is a
statement about a *sealed* ring against a turret that never shoots the barriers. Against an attacker that
treats a blocked lane as a target, the ring is **armour, not a wall** — `a4fort3` still went 0-42 against
`tempest_fast`, `vanguard` and `mistral`. It converts core-death losses into 1 000-round games; it only
converts those into wins if the economy can take the tiebreak (see §4, ECONOMY).

Depends on **E9** (`destroy()` hot-swap) so the ring can host the terminal conveyor G02 requires without
opening for a single frame.

---

### Tier 2 — measurable, bounded cost, general by construction.

#### E4. Site the siege turret as a Sentinel where the Gunner is starved — `LAB` + `ARITH` (recomputed)
**~60 lines.**

The Sentinel's ray **is never blocked by walls or units** — a single-tile line, 5 cardinal (r²≤25) / 4
diagonal (r²≤32), and it chooses which tile of its 5 to hit. This is documented
(`docs/official/docs/game-rules-turrets.txt:83`) so it will not be patched, and it is recorded nowhere in
`ground-truth.md`. `gg_fort` on arena `sentbox`: a Sentinel **sealed on all four sides** (walls N/S, our own
barriers E/W) destroyed the enemy Core through 1 barrier and 2 walls — `winner: A, core_destroyed, turn 94`.
Its `can_fire` was simultaneously `True` on the Core 5 tiles away, on an empty tile, on a wall tile and on
our own barrier.

The corollary that matters most: **G10/G11 does not apply to a Sentinel.** A 3-Ti conveyor in a Gunner's
lane neutralises a 10-Ti turret; a Sentinel cannot be screened, jammed or blocked by anything, by them or
by us.

**I recomputed the map arithmetic independently** (over all 21 `.map26` files, 42 sides, excluding walls,
ore and both footprints as turret sites):

```
TOTAL over 42 map-sides:  gunner = 1228   sentinel = 1886   (+54%)
```

which reproduces Area 3's 1 222 / 1 886 to within six tiles. But the flat +54% is the wrong decision rule.
**The uplift is concentrated exactly where the Gunner is starved:**

| map | gunner | sentinel | uplift | |
|---|---|---|---|---|
| showdown | 30 | 60 | **+100%** | NEW |
| bridge | 11 | 20 | **+82%** | NEW |
| sweden | 16 | 28 | **+75%** | NEW |
| longship | 36 | 62 | +72% | |
| vase | 14 | 24 | **+71%** | NEW |
| string | 10 | 17 | **+70%** | NEW |
| … | | | | |
| pinch, quarry | 36 | 48 | +33% | |

**Five of the six maps G64 added to the pool are in the top eight by uplift**, and four of the five
lowest-Gunner-count maps in the pool are new maps. The Sentinel is not a general damage upgrade — it is the
answer to the wall-dense maps the bot has never been tuned on.

**Also recomputed, and it confirms Area 3 independently:** walking from our own spawn ring, a Sentinel
firing position is reached **sooner than a Gunner position on every single map in the pool** — by 1 to 7
rounds, mean 3.2 (string 13→6, sprint 5→0, atoll 16→12, aurora 35→31, vase 6→2).

**Narrow bonus, reported accurately as narrow.** On `sprint` and `showdown` only, a Sentinel built on our
*own* Core spawn ring already bears on the enemy Core — sprint tile (3,3) firing NE at range 4 (d²=32, the
diagonal maximum); showdown tiles (6,5) and (6,6) firing EAST at range 4. Zero walking, zero exposure. Two
maps of twenty-one. Take it when the map offers it; do not build a doctrine on it.

*Honest cost:* 30 Ti + 20pp, 10 ammo per shot, 6 dmg/round against the Gunner's 10 dmg/round for 2 Ti.
**2.8× worse per titanium and 1.7× slower.** Buy it for reach and unjammability, never for damage. A Core
kill is 28 shots ≈ 280 Ti of ammo over 84 rounds versus a Gunner's ~110 Ti over 50.

*Also honest:* naturally wall-shielded Sentinel spots are rare — 82 across 42 map-sides, and 12 of 21 maps
have none. The pillbox has to be built from our own barriers, which a Gunner grinds through in 3 shots.

#### E5. The damage-quantum archetype detector — `FIELD`, and already written
**~40 lines, and the code exists in `tools/apply_detector_2_3_3.py`. It has never shipped.**

The current `EV_HURT` bit claims that any hit point lost *proves* a fed enemy turret. That rested on two
premises 2.3.3 killed: old G13 (a builder cannot attack an adjacent tile — **reversed**, G59) and "our own
turrets check team before firing" (**never true**, G10, and now it bites because turrets have ammo).

Measured over **270 games**: 86.9% of every hit point we lose comes from an enemy **builder**, 12.7% from
an enemy turret, 0.4% from our own turret shooting our own buildings. **52% of `EV_HURT`'s latches were
caused by something that is not a turret.**

The repair is the quantum. `BUILDER_BOT_ATTACK_DAMAGE = 2`, `GUNNER_DAMAGE = 10`, `SENTINEL_DAMAGE = 18`
are pairwise distinct, and a cross-tab of **229 damage events** against the source the replay independently
proves is **perfectly diagonal**: 192 hits of exactly 2, all from an adjacent enemy builder; 37 hits of
exactly 10, all from an enemy Gunner; **zero off-diagonal**. The *size* of a hit names its source.

Full design in §4.

#### E6. The Launcher ferry, but only when a route model proves the saving — `FIELD` (one map) + `ARITH` (recomputed)
**~50 lines. `heapq` works in the sandbox (G35).**

The throw arcs over walls and Core footprints (G48); legal targets are exactly the disc r²≤26 minus
non-passable tiles; a thrown builder lands on zero cooldowns and can act the same round **provided the
Launcher's entity id is lower** (G46 — build the Launcher first).

Engine-verified on `sweden`: `gg_ferry` reached a tile adjacent to the enemy Core on **round 15**; the
identical walking control `gg_walk` reached the same tile on **round 44**.

Area 1 modelled 4-11 rounds saved on all 21 maps against the target "a tile adjacent to the enemy Core".
**I re-derived it against the target that actually matters** — the nearest *firing position* on the enemy
Core, worst of the two sides, Dijkstra with hop edges at 2 rounds + 20 Ti:

```
one-hop saving to a GUNNER firing position:  min=0  max=34  mean=6.6
>= 3 rounds on 20 of 21 maps;  >= 5 rounds on 14 of 21
sweden 34   runestone 9   string 9   aurora 10   pinch 7   showdown 0
```

The claim survives the stricter test at a slightly lower magnitude. Good.

**Where the hunters disagree, and how it resolves.** Area 1 calls the ferry its biggest find. Area 4
measured the ferry *already in the bot* (`_vault`) as its biggest scale leak: **3.2-3.8 Launchers built per
game for 1.6-1.9 throws**, ~35pp of permanent global scale, and 54-274 launcher-turns per game otherwise
idle. Both are right. The synthesis is the specification:

> **Hop only when a Dijkstra over observed terrain proves ≥4 rounds saved, and `destroy()` the Launcher
> the round after the throw (E1).** Un-gated opportunistic hopping is the single largest cost-scale leak
> in the current bot.

The backlog lists "launcher ferry for our own rusher" as correctly dropped. That was measured on the
**15-map pool, before `sweden` existed**, against the ore-adjacency doctrine G57 has since voided. Re-open
it — under the gate above, not as it was.

---

### Tier 3 — mechanism proven, doctrine unproven. Build behind a flag, measure before believing.

#### E7. The sealed kill box — `LAB` for the kill loop, `FIELD` for the interceptions
**~80 lines.**

Cell C with its four cardinal neighbours = 3 barriers + our own Gunner facing C. The occupant cannot move,
and C is the *first* tile of the Gunner's ray so nothing blocks the shot. The Launcher (built first, so its
id is lower) feeds C from up to d²≤26 away. `gg_kbox3` on `glopen`, **no terrain feature required**:

```
r15 GOBBLE id4 -> cell     r16 SHOT 40->30    r17 30->20    r18 20->10    r19 10->0 DEAD
… sustained r15 -> r35: 5 kills, 20 shots, 8 Ti of ammo per 40 HP builder, barriers finished at 30/30/30
```

Against real rivals (`gg_lfort2` vs `tempest_fast`, `vanguard`, `undertow`, `mistral` × 5 maps): **39
rewinds, 5 gobbles into the cell, 4 confirmed kills of rival builders it was never tuned against.**

**The siting rule is the proven part and it refutes the obvious instinct.** `gg_lfort` put the Launcher on
the Core ring tile nearest the map centre: **zero throws in 43 rounds.** Re-sited 3-4 tiles out it
intercepted immediately. The reason is measured, not guessed: a Gunner reaches a Core footprint tile from
r²≤13, so rival builders stop **3-5 tiles short** and never come to our ring. `gg_scout` over 20 matches
found that none of the 20 best Launcher tiles is on the Core ring; all are Chebyshev 3-5 out, toward the
map centre.

**Why it is Tier 3 and not Tier 1.** 0 wins in 20 games. Mean +5.6 turns of survival, median ~+1.5, with
regressions on two matchups (vanguard/quarry −7, undertow/quarry −4). M01 says treat anything under ~10
turns as noise. It also costs **39 Ti + 23pp of global cost scale**, which fights E1 directly. And it
cannot hold a line: 1 kill per 4 rounds against a Core that spawns 1 builder per round. It is an economic
weapon — 8 Ti of ammo against 30 Ti × rising scale of theirs — not a wall.

#### E8. The harvester tap — `LAB` for the split, `FIELD` for the opportunity, one leaky `FIELD` result
**~40 lines.**

Harvester round-robin is **team-blind**. Arena `para`, scripted victim with harvester + 4-conveyor chain:

```
control (noop)          a_collected=0     b_collected=2470
one parasite head       a_collected=1230  b_collected=1240    exactly 50/50
two heads, one trunk    a_collected=1640  b_collected=830     exactly 2:1  (and we won on titanium_collected)
```

Each orthogonally adjacent resource-accepting building gets an equal share regardless of team. A harvester
has 4 slots and the owner needs ≥1, so **maximum theft is 3/4**. Economically it is a harvester that costs
3 Ti instead of 20 and needs no ore tile — while halving theirs.

The bounds are clean and all three negatives were measured: **diagonals do not feed** (0 vs 2 470);
**barriers do not receive** (2 470, bit-identical to control); **a dead-end tap jams after exactly one
stack** (2 460 vs 2 470). Theft requires a real drain terminating on our own Core footprint (G02).

*Opportunity is real:* `a2spy` over 6 maps × 4 rivals found rival harvesters in vision from round 8-36, and
**14 of 17 had free orthogonal slots**. Three different rivals independently harvest the same tile (5,5) on
`sprint`, so the target is not opponent-specific.

*Delivery is the problem, and this is why it is Tier 3.* The end-to-end probe `a2sprint` banked 70 Ti
against `undertow` and **0 against `jonbot`, `vanguard`, `tempest_fast` and `mistral`** — it lost its Core
before the belt earned. And the tap must reach our own footprint: I measured the minimum belt for our *own*
nearest ore at **1-6 conveyors, mean 3.0**; a tap on a contested harvester is further than that.

**Build it only in the form Area 2 itself proposed: route the economy trunk so it grazes contested ore
tiles, and take the taps when they are free.** Do not build a belt for the purpose.

#### E9. `destroy()` hot-swap — `LAB`, enabling primitive
**~5 lines.**

`destroy()` costs **zero action cooldown**, is unlimited within a turn, refunds no titanium, and the tile is
rebuildable the same turn. `a4swap`: `cd0=0 can_destroy=True | cd_after_destroy=0 built_same_turn=yes
cd_after_build=1 occ=True`. `denyapi` destroyed and rebuilt in one round; `a2count` landed three destroys in
one round with `cd=0` throughout.

Not a weapon. It is the dependency that lets a fully sealed Core ring host the terminal conveyor G02
requires **without ever opening a lane for one frame**, and it is half of E1.

Also proven and worth knowing: **`destroy()` and `heal()` are NOT team-blind**, unlike every turret API.
`a2destroy`: `cdes=False | chl=False | DES!Game:Cannot destroy | HEAL!Game:Cannot heal | FIRE=None`. Only
`fire` crosses teams. That cuts both ways and mostly ours: **any building of ours standing on a tile they
want is unremovable by them except by shooting it.**

---

### Tier 4 — proven in a lab, do not build

#### E10. Conveyor interception — `LAB`, contrived
Arena `inject`: our two 3-Ti conveyors took `a_titanium_collected=2480` against the victim's `0`, out of a
theoretical 2 490. Owning **one** tile inside an enemy belt steals 100% of everything upstream, not a share.

The most spectacular number in the session and the least likely to occur. The victim was scripted to build
its belt *into* tiles we already owned. Route-to-that-tile in a real game requires either squatting it
before they lay the belt, or killing the conveyor with a Gunner and rebuilding ours there. Record the
mechanic; do not plan around it.

#### E11. Locking the enemy spawn ring — `LAB`, win-more
`ringlock` vs `spawnwatch` on arena `close`: `ring=12 r0:12 r10:10 r20:6 r30:2 r40:0 … LOCKED_AT=36`, and
the opponent produced zero further builders for 962 rounds, for 66 Ti total. Barriers are legal on enemy
ring tiles (`gg_ringblock`: `canbar=True|bar=5`).

Both hunters who tested it independently killed it: `tempest_fast` spawns its entire army before ~round 10,
so a round-36 lock costs it nothing; and on `close` a lone builder laying barriers had our Core destroyed
at turn 15-35 by **all five** real rivals. It is a mid-game lock for a bot that already has board control.

---

## 3. The dud list

Re-proposing any of these is the main way effort gets wasted here. Each line ends with the observation that
killed it.

| # | Idea | What killed it |
|---|---|---|
| 1 | **`CORE_ACTION_RADIUS_SQ = 8` unlocks Core actions at range** | `gg_c1` scanned every capability query over the full 8×8 offset block from the Core: `can_spawn` lights up exactly the 12-tile r²≤2 ring and **every other query is False on every tile** — barrier, conveyor, gunner, harvester, heal, destroy, fire. There is no pull radius either (a lone harvester at d²=4, 8, 9 collected 0, 0, 0). It is a dead constant. |
| 2 | **The Splitter** | `gg_belt1` (conveyor) collected **2490**; `gg_belt2`, byte-identical but for a splitter, collected **2490**. Double price, same throughput, and since ammo is global the Core is the only sink in the game, so a three-output building has nothing to serve. `frontier`/`lockin`/`luc1` still carry splitter→turret feeding code dead since 2.3.3. |
| 3 | **Cost-scale baiting** | Scale is a live census and refunds on **death** as well as on voluntary destroy (`a2scale`: `gun=131 … DEAD r8 scale=130.0`). You cannot permanently inflate an opponent's prices. Worse: every enemy building we kill makes their next build **cheaper**. |
| 4 | **Pushing an opponent to the 50-unit cap** | Only Core, Builder Bot, Gunner, Sentinel and Launcher count. Barriers, conveyors, splitters and harvesters do not (`base u2 \| harv u2 \| splt u2`). We cannot make an opponent build turrets, so there is no lever. *(Useful in reverse: our barrier/conveyor denial spam never competes with our own army for cap.)* |
| 5 | **Ray jamming as permanent denial** | G11 already records that the 2.3.3 Gunner destroys the blocker and advances. And both strong rivals team-guard explicitly — `tempest_fast/gunner.py` compares `get_team(target_id) != get_team()`; `vanguard/gunner.py:31` returns on a friendly. A barrier in the lane is still a **2:1 ammo sink** (6 Ti of their ammo for our 3 Ti), but that is a trade, not a lock. |
| 6 | **A barrier next to an enemy harvester as free denial** | `a2barr`: `b_collected=2470`, bit-identical to control. Barriers are not resource-accepting. |
| 7 | **Diagonal parasite slots** | `a2diag`: `a=0, b=2470`. A harvester has 4 slots, not 8, and fewer against a wall or edge. |
| 8 | **A dead-end parasite conveyor as an economy killer** | `a2deny`: `a=0, b=2460` against control 2 470. Worth **exactly one 10-Ti stack**, then the harvester round-robins past it forever. |
| 9 | **Team-blind `destroy()` / `heal()`** | `a2destroy`: `cdes=False \| chl=False \| DES!Game:Cannot destroy \| HEAL!Game:Cannot heal`. Only `fire` crosses teams, at 2 dmg for 2 Ti — 10 attacks and 20 Ti to remove a 3-Ti conveyor. Use a Gunner (2 shots, 4 ammo). |
| 10 | **"Park a Launcher on our own approach and rewind the siege"** | Refuted twice, independently. (a) On the Core ring it intercepts nothing: `gg_lfort` built at r7, **zero throws by r43**. (b) Even throwing every single round it does not defend the Core: with the Launcher on, mean enemies inside its pickup ring fell 4.51 → 1.09, but mean enemies **orthogonally adjacent to our Core footprint went 1.00 → 0.99**. One Launcher owns 8 tiles and 1 throw per round. That is the entire defensive footprint. |
| 11 | **Throwing an enemy into a Gunner's ray as a kill** | Worth **exactly 10 damage**. `gg_kbox`: 7 throws, 6 shots, **0 kills** — every victim walked out, and it moves *before* us because enemy builders spawned early carry lower entity ids. Displacement only kills when the destination immobilises. |
| 12 | **One rotating Gunner covering two approaches** | Rotation is a flat 10 Ti and adds 0pp — good for **re-aiming a static defence a few times**. As a coverage strategy it is 5 Ti/round for 5 dmg/round = **1 Ti per damage, five times worse than a static gunner's 0.2**, plus one lost firing round per swap. |
| 13 | **The zero-conveyor harvester** — *my addition, and it kills a genuine finding* | Area 3 proved a harvester orthogonally adjacent to a Core footprint delivers **2500** with no belt at all, beating the 2 490 of a harvester+chain. Real and unreachable: I checked all 21 maps × 2 sides and **zero of 42 have ore orthogonally adjacent to a Core footprint.** Nearest ore is Chebyshev 2-6. Minimum belt over the pool is **1-6 conveyors, mean 3.0**. |
| 14 | **`a4sit` (parking bodies on firing tiles) as a tactic** | 0-42 vs `tempest_fast`, 0-42 vs `vanguard`, 0-42 vs `mistral`, median death turn 33-44. It exploits one defect in one bot. Build the immunity (E2), not the tactic. |
| 15 | **Free wall-shielded Sentinel pillboxes** | Only 82 naturally shielded spots across 42 map-sides, and **12 of 21 maps have none**. The pillbox must be built from our own barriers. |
| 16 | **`get_nearby_units()` as an army count** | Not a dud — a **correctness trap**. The stub says "ids of all units"; it returns **Cores and turrets too** (`NEARBY_UNITS 3:BUILD 1:CORE 9:LAUNC`). Filter on `get_entity_type(id) == EntityType.BUILDER_BOT`. Report as a documentation bug. |

### Where a hunter over-generalised, and the correction

Area 3 concluded *"the parasite conveyor does not siphon… G43 is mostly answered and mostly negative"*,
from a probe where the tap dead-ended into bare ground (2 490 against a 2 500 baseline). Area 2 ran **both**
cases and got the same dead-end result (2 460 vs 2 470) **and** the 50/50 and 2:1 splits when the tap
drained to its own Core. **Area 2 is right and Area 3's phrasing would have killed a real mechanic.** The
distinction is whether the drain terminates on a Core footprint tile — which is just G02, and G02 was
already in the register.

---

## 4. Architecture

### The three postures — what each one actually does

The current `_arbitrate` docstring gets the clock right and should be preserved verbatim as a design
constraint: *"a posture decided at round R is published at R+1, read by a builder at R+2, and whatever it
buys is standing perhaps twenty rounds after that. So the postures may differ in SCALE and must never
differ in EXISTENCE."* Every subsystem's minimum version is built unconditionally; the posture only says
how much more.

#### RUSH — the primary win condition, and the only one with a strong evidence base

Rounds 0 to ~25, default posture.

1. **Target: a firing position on the enemy Core footprint, at range 1 where the map allows it.** Range 1
   onto a 2×2 footprint is a ring tile by definition, and the telemetry says this is where ~30 of every 32
   wins are made.
2. **Route: Dijkstra over observed terrain**, with launcher-hop edges (any bot-passable tile at d²≤26,
   cost 2 rounds + 20 Ti), taken **only when the model proves ≥4 rounds saved** (mean 6.6, §E6).
   `heapq` is available (G35). Build the Launcher **before** the rusher moves so its id is lower (G46), and
   `destroy()` it the round after the throw (E1).
3. **Turret choice is a map decision, not a taste decision.** Gunner when a Gunner position is reachable and
   its lane is clear — 10 dmg/round for 2 Ti is unbeatable. Sentinel when Gunner positions are few or the
   lane is contested: +54% positions overall, +70-100% on the wall-dense maps, reached 1-7 rounds sooner
   everywhere, and unjammable (§E4). On `sprint` and `showdown`, check the own-ring Sentinel first.
4. **Fund it from `convert_ammo` at the Core.** G57: a forward Gunner kills a 500 HP Core on a map with
   **zero ore**, for ~162 Ti out of a 500 Ti opening bank. Delete every remaining ore-adjacency
   consideration from siting.
5. **Give up on a firing tile only on repeated failure at the same tile** — never on a timer. The measured
   `BUILD_PATIENCE` regression (29-13 against 31-11) came from abandoning tiles that were merely waiting to
   be funded. That is a different condition from a tile that is permanently illegal, and the two must be
   distinguished by *why* `can_build_*` refused, not by how long it has refused.

#### DEFENCE — the missing half, and the cheapest correct counter to our own attack

Triggered by the detector below, but its minimum version is unconditional.

1. **Occupy our own Core ring, from round 0, as the highest-priority build.** Compute the ring size at
   runtime — it is 5 tiles on bridge, jackpot, string, sweden and vase, 12 elsewhere (§E3).
2. **Close it in cycle order, not raster order.** The ring tiles form a closed orthogonal cycle, so the
   pattern "brick i−1, brick i+1, step out, brick i" from seats 0/3/6/9 closes it by round 10 — two rounds
   before a rusher's first Gunner arrives. Fort v1 used raster spawn order and reached 6/12 by round 6,
   losing the contested column; the ordering of the **spawning** mattered more than the ordering of the
   bricking.
3. **Occupy with conveyors facing outward into the trunk wherever the economy needs a terminal**, barriers
   elsewhere. G02 forces the terminal conveyor onto one of the 8 non-corner ring tiles anyway, so the ring
   and the belt want the same tiles. `destroy()` hot-swaps between them at zero cooldown (E9).
4. **Brick before healing.** `_hold_home` currently heals first, and its fortify branch fired **8 times in
   210 games** while the alarm was up for 1 127 rounds and `_heal` returned first in 944 of them. Healing
   loses on arithmetic: 4 HP per 1 Ti against a fresh 30 HP barrier at ~4 Ti, or 7.5 HP per titanium — and
   unlike a heal, a barrier also stops the ray.
5. **No Launcher on the ring.** 3-5 Chebyshev out, toward the map centre (§E7).
6. Be honest internally about what this is: **armour worth 10-15 rounds**, plus a near-total shutdown of any
   attacker that requires a ring tile. It buys the game; it does not win it.

#### ECONOMY — the second win condition, and the structural hole in the current bot

This is the posture that does not exist today and it is why the fortified probes could not convert.

The audit's most damning economic number: against `a4fort3`, AutistimusPrime banked up to **9 647 titanium
and collected ZERO in 15 of 42 games**. It forces the 1 000-round game and then cannot win the tiebreak it
forced. `C_spawn` is 3.0-3.7 builders per game and `O_harv` is **0.67-0.83 harvesters built per game** — the
whole economy is one chain.

1. **`titanium_collected` ranks first in the tiebreak (G03), and only stacks landing on a Core footprint
   tile count (G01/G02).** Banked titanium is the *third* key. A bot that banks 9 647 and collects 0 loses
   to one that collects 10.
2. **Build three or more chains, not one.** I measured the minimum belt for the nearest ore per map-side:
   **1-6 conveyors, mean 3.0**. On `duel`, `fjord`, `skerry` and `string` it is **one conveyor**. A second
   chain is ~23 Ti (harvester 20 + belt) and the current bot builds 0.67-0.83 harvesters per game.
3. **Never start a chain you cannot prove reaches the Core over observed terrain** (backlog N5, the L2 half
   of vanguard's `plan_line`: *"unknown ground is not permission to spend titanium"*). A chain one tile
   short scores exactly zero.
4. **Route the trunk so it grazes contested ore.** Free harvester taps (§E8) when the geometry offers them,
   never a belt built for the purpose.
5. **Harvesters block movement (G42).** A 20 Ti building is also a wall, including our own corridors.

### The archetype detector

**Key on the damage quantum, not on hit points lost.** The three attack damages are pairwise distinct and
the cross-tab over 229 events against replay-proven sources is perfectly diagonal (§E5), so the *size* of a
hit names its source.

```
EV_MELEE        net loss of exactly  2   -> an enemy Builder Bot is beside us
EV_TURRET_HURT  net loss of exactly 10   -> a fed enemy Gunner
                net loss of exactly 18   -> a fed enemy Sentinel
EV_HURT         any other loss           -> contact, and nothing more
```

Three rules on top:

1. **State the ambiguity rather than hiding it.** These are net per-round deltas, so this is strong
   evidence and not proof: `HEAL_AMOUNT = 4` means a Gunner hit plus two friendly heals also nets −2, and
   five builders chewing the same tile also net −10.
2. **Add the bit that beats the quantum on the clock.** Being hit is a *late* signal — measured against
   `undertow`, their first turret exists at round 30 and lands its first shot at 31, our Core is dead by 60,
   and a posture decided at 31 stands as a barrier around round 43. What is early is the enemy **builder
   that walks in to build the turret**, and the Core sees it for free: it acts first every round, never
   moves, and one `get_nearby_entities` around its own footprint answers "is somebody setting up on top of
   us" directly. `EV_HOME_THREAT` = an enemy Builder Bot or turret inside r²≤25 of our Core anchor (a
   Gunner reaches a footprint tile from r²≤13, so r²=16 covers everything that can already shoot, and the
   extra ring is the walk-in).
3. **Price it so DEFENCE is reachable by exactly two routes and no other**: a turret-sized hit, or an enemy
   on our doorstep. Everything else is corroboration and must not sum to the threshold. `EV_INTRUDER` and
   `EV_DEEP` fire in 90-100% of games against any opponent that spawns a builder at all — a threshold they
   can reach between them is not a detector, it is "DEFENCE unless the enemy is inert".

And one API correction the detector depends on: **`get_nearby_units()` returns buildings**, including Cores
and turrets. Filter on `get_entity_type(id) == EntityType.BUILDER_BOT` or the detector counts the enemy
Core as an army.

### Keeping the line count low enough that dead code cannot hide

The audit is the specification here. Twelve counters sat at zero for 210 games because nothing in the build
process could see them.

1. **Hard cap: 900 lines total.** `tempest_fast` is 782 non-comment lines and is what is on the ladder;
   `vanguard` is 1 389 and beats the field. If GobbleGlitch needs 2 755, the design is wrong.
2. **One file per role, ≤150 lines each, plus one shared geometry module.** A role file over 150 lines is
   doing two jobs. `bot/main.py` at 2 755 lines holds 70 methods and is the reason nobody has a model of it.
3. **One definition of "occupied", in the shared module, used by planner and executor alike — buildings
   AND bodies.** The worst defect in the current bot exists because those are two different definitions in
   two files ~600 lines apart (§E2). Price a blocked lane as three shots of work, not as infinity.
4. **No branch ships without a counter, and the counters gate the release.** `bots/cand/audit` already
   exists. Make it a build step, not an archaeology project: any branch at zero after 42 mirrored games is
   **deleted, not documented**. The 24 lines of `_run_sentinel` and 12 lines of docstring on `G_friendly`
   are what "documented instead" looks like.
5. **No capability without a call site — enforce with one grep.** `_run_sentinel` was unreachable because
   `build_sentinel` appears nowhere in `bot/`. `grep -L 'build_sentinel' bot/*.py` answers that in a second
   and nobody ran it.
6. **Every tuned constant carries the sweep that set it, or it is deleted.** `BUILDERS = 3` under a table
   concluding "Six is the pick" is the audit trail failing where anyone could read it.
7. **Delete the atlas.** 335 lines, stale on 6 of 21 maps (G65). One code path — the runtime one — so the
   unseen-map case is the case exercised every single game rather than a fallback nobody tests.
8. **Occupancy memory must expire out of vision.** `self.occupied` currently clears only while a tile is
   visible, so one glimpsed enemy building permanently deletes every lane through it in the strict pass.
   That single bug is the entire reason the permissive fallback exists, and the permissive fallback is what
   proposes tiles the executor cannot take.

---

## 5. The generalisation requirement — a hard gate

> **No capability ships unless it holds (a) on unseen maps and (b) against at least three different rivals,
> both measured mirrored.** Not "was tested against". *Holds against.* A capability that is neutral on two
> rivals and positive on one has not passed.

### Why unseen maps

The current bot wins **83% on published maps and 69% on unseen ones**. That 14-point gap *is* the
memorisation, and the history says the gap can be total rather than partial: before the runtime siege
planner, AutistimusPrime scored **zero core kills on every unseen map**, because `atlas.identify()` returned
`None` and `RUSH_MAPS` never matched — the attack **silently disabled itself** while the known-map record
looked healthy. Nothing crashed and nothing logged. G65 says the same failure is live again today on the six
maps added since.

**The mistral result is the specific reason the gate is hard rather than advisory.** We lose to mistral on
unseen maps and not on published ones. That is not a matchup quirk — mistral is 767 non-comment lines with
no map data at all, so its performance is *identical in kind* on both map sets. Ours is not. When a
map-blind opponent overtakes us the moment the maps change, the difference between the two columns is
entirely ours, and it is a measurement of how much of our record is lookup rather than capability. Any new
capability measured only on the published pool is measured on the side of that gap where we cannot tell the
two apart.

`tools/unseen.py` and `tools/evaluate.py` already exist and already label the known column as
memorisation. Make them the gate, not the report.

### Why three rivals

Every one of this session's most attractive findings would have read as a triumph from a single matchup:

| Finding | One rival | Three rivals |
|---|---|---|
| `a4sit` — park bodies on firing tiles | Deletes AutistimusPrime's offence: **1 kill in 42 games** | **0-42** vs tempest_fast, **0-42** vs vanguard, **0-42** vs mistral |
| `a2sprint` — the harvester tap end to end | vs undertow: banked **70 Ti** with no legal source but theft | vs jonbot, vanguard, tempest_fast, mistral: **0, 0, 0, 0** — Core destroyed first |
| `gg_lfort2` — the kill-box fort | undertow/duel **+48 turns**, vanguard/sweden **+33** | vanguard/quarry **−7**, undertow/quarry **−4**, **0 wins in 20** |

The three strong rivals differ in the ways that matter: `tempest_fast` spawns its entire army before round
10 (so spawn denial costs it nothing), `vanguard` replans when blocked (so occupancy tricks do not stick),
`undertow` is slow to contact (so it leaks to economic attacks nobody else leaks to). A capability tested
against one of them is tested against one of those three shapes.

### The noise floor, and what to report instead

M01: **±2-4 games per 30-game sweep** for anything that perturbs pathing, and the pool is now 21 maps × 2
sides = 42 games. Deterministic does not mean low-variance across code changes.

- Treat anything under **~5 games** or **~10 turns of survival** as noise. The kill-box fort's +5.6 mean
  turns over 20 games is inside it and must be reported as "mechanism proven, doctrine unproven".
- **Prefer mechanism numbers to win counts.** "1 228 → 1 886 firing positions", "6.6 rounds saved per hop",
  "35pp of scale recovered per game", "2 480 of 2 490 intercepted", "4 gunner builds against 47 695
  failures" — these have no noise floor, they are the thing itself. A win count is a noisy function of a
  mechanism number and needs five times the games to say half as much.
- **Mirror everything.** Team A wins ~58-60% of identical-bot mirrors (G27), and at seed 1 an all-ties
  game resolved to Team A on 15 of 15 maps (M05).

### Standing constraint, restated

Nothing in this brief that beats only one named opponent may be built. `a4sit` is the clearest example: it
is the largest single measured effect in the session and it is **not a tactic**, it is a bug report against
ourselves. The corresponding capability — one shared, body-aware definition of "occupied" — is what ships,
because it works against an opponent nobody has seen.

---

## Appendix — new measurements made while writing this brief

Four things nobody in the four hunts computed, all recomputed from `maps/*.map26`:

1. **Zero of 42 map-sides have ore orthogonally adjacent to a Core footprint.** Nearest ore is Chebyshev
   2-6. Area 3's "harvester adjacent to the Core delivers 2 500 with no conveyor" is real and unreachable on
   this pool. → dud list #13.
2. **The Core ring is 5 tiles, not 12, on bridge, jackpot, string, sweden and vase** (mean 10.3 over 42
   sides), because those Cores sit flush against a map edge (G64a). All three hunters who costed ring work
   assumed 12. → §E3.
3. **Sentinel vs Gunner firing positions independently reproduced** at 1 886 vs 1 228 over 42 sides (+54%,
   against Area 3's 1 886 / 1 222), and the uplift resolved per map: +100% showdown, +82% bridge, +75%
   sweden, +71% vase, +70% string against +33% pinch/quarry. Five of the six maps G64 added are in the top
   eight. Sentinel firing positions are also reached 1-7 rounds sooner than Gunner ones on **every** map
   (mean 3.2). → §E4.
4. **The launcher ferry re-derived against firing positions rather than Core-adjacent tiles**: mean 6.6
   rounds saved by one hop, ≥3 on 20 of 21 maps, ≥5 on 14 of 21, sweden 34, showdown 0. Area 1's claim
   survives a stricter target at slightly lower magnitude. → §E6.

Also computed and used in §4: **minimum belt length from the nearest ore to a Core footprint tile is 1-6
conveyors, mean 3.0** over 42 sides; one conveyor suffices on duel, fjord, skerry and string.
