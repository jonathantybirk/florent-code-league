# Findings

Every entry carries the number, the sample size, and the probe or sweep that produced it. Refuted
expectations are recorded as prominently as confirmed ones. Updated as work lands.

## Established before the change opened

| # | Finding | Evidence | Status |
|---|---|---|---|
| F1 | Engine is `fcode 2.3.6`; turret constants identical to 2.3.5 | `GameConstants` dump | CONFIRMED |
| F2 | Sentinel out-damages Gunner: 9.00 vs 7.00 dmg/round | derived, `tools/firstprinciples.py` | CONFIRMED |
| F3 | Sentinel is cheaper per damage: 0.556 vs 0.571 Ti/dmg | derived | CONFIRMED |
| F4 | Sentinel 40 HP vs Gunner 25; reach 5 vs 3 | `GameConstants` | CONFIRMED |
| F5 | Sentinel kills a Gunner in 2 shots; Gunner needs 6 and cannot reach back | derived | CONFIRMED |
| F6 | A Core kill costs ~310 Ti against a 500 Ti opening bank, 3000 Ti lifetime | derived | CONFIRMED |
| F7 | Fastest Core kill turn 62–77 (Sentinel) vs 80–95 (Gunner) at core-gaps 10–25 | derived | CONFIRMED |
| F8 | Sentinel fires through solid WALL: `SATK` includes wall tiles, `CF=True`, Core 500→158 by r40 | `bots/probes/sentwall` on `maps/lab/sentwall.map26`, 2.3.6 | CONFIRMED |
| F9 | Gunner cost scale doubled to +20%, same as Sentinel | `cs_inc`: `gn+20-20` | CONFIRMED |
| F10 | Cost scale is still a live census — destroying refunds in full | `cs_inc`, all types `+N-N`; `bbSD` 140→120 | CONFIRMED |
| F11 | Vision is still a raw Euclidean disc with no occlusion | `apivis`: `n=69 disc=69`, sees through wall | CONFIRMED |
| F12 | Spawn denial still requires impassable buildings; conveyors/splitters do not deny | `spawn2`: `CONV sp1`, `GUNN sp0`, `BARR sp0` | CONFIRMED |
| F13 | Engine is fully deterministic — seeds 1–5 and 999 bit-identical | repeated `run_game` | CONFIRMED |
| F14 | Ladder Elo consumes the *fractional* series score, so margin matters | `docs/official/docs/platform-ladder.txt` | CONFIRMED |
| F15 | Ladder maps are drawn at random per game from the pool; pool may change between rounds | `platform-matches.txt` | CONFIRMED |
| F16 | `ct.draw_indicator_line` / `draw_indicator_dot` render into replays | `_types.py:722,728`; `platform-matches.txt` | CONFIRMED (API present; runtime unverified) |
| F17 | Launcher pickup is team-blind — now documented, not just measured | `game-rules-turrets.txt` 2.3.4 | CONFIRMED |
| F18 | Nash support set is steward 0.523, vigil 0.199, heimdall 0.099/0.094, odin 0.085 | `tournament/runs/v2-full-20260804/ratings-distinct.csv`, 3360 games each | CONFIRMED |

## Carried forward as stale — must be re-verified before reuse

| # | Claim | Why stale |
|---|---|---|
| S1 | Every combat exchange rate in `llm-slop-analysis/elias/` | measured on 2.3.3, before the rebalance |
| S2 | Passability table | prior probe's output encoding unreadable; re-probe queued as task 1.4 |
| S3 | Sabotage exchange 6.3:1 against the attacker | 2.3.3 numbers; conveyor and repair costs unchanged but turret costs are not |
| S4 | "Gunner is blocked by the first obstruction" | doc-stated and measured on 2.3.3, not re-measured on 2.3.6 |

## Open — answers change the design

| # | Question | Task |
|---|---|---|
| Q1 | Healer-vs-grinder ratio for holding a forward turret | 1.1 |
| Q2 | Is the Sentinel duel decided by build order via entity-id priority | 1.2 |
| Q3 | Is a single long belt from the largest cluster viable, and on what fraction of maps | 1.3 |
| Q4 | Real per-unit CPU budget: 10 ms or 2 ms | 1.5 |
| Q5 | Sabotage exchange rate on 2.3.6, and the abandon condition | 1.7 |

## Map pool rotated 2026-08-04 — 15 maps, and it changes the odds

| # | Finding | Evidence | Status |
|---|---|---|---|
| F19 | Pool is now **15 maps**, 12 of them new. Only `atoll`, `hive`, `jackpot` survive from the old 21. | `fcode maps list` | CONFIRMED |
| F20 | **The enemy Core is the 180-degree rotation on 14 of 15 maps.** `meander` is the sole exception (mirror-y). | decoded all 15 map files | CONFIRMED |
| F21 | Terrain symmetry and Core placement can disagree — `antler`, `eider`, `heart`, `moonrise`, `nordkap` have mirror terrain but rot180 Core placement | `matching_symmetries` vs `siege.candidates` | CONFIRMED |
| F22 | Mean walk from spawn to Sentinel range (5 tiles from enemy footprint) is **14.6 rounds**, spread 3 (`meander`) to 31 (`hive`) | BFS over all 15 pool maps | CONFIRMED |
| F23 | Half the pool has walks of 20+ rounds: hive 31, saga 26, archipelago 24, snowflake 24, drumlin 22, jackpot 21 | same | CONFIRMED |
| F24 | Sentinel first shot lands ~turn 6–34 (mean ~18); +56 rounds to kill a Core puts a clean siege at ~turn 74 | derived from F22 | CONFIRMED |

**Design consequence.** On the old pool, rot180 was right on 66.7% of map-sides and symmetry
inference mattered. On this pool a flat rot180 assumption is right **93%** of the time and terrain
refutation catches `meander` early — the inference problem has essentially gone away.

The bigger consequence is length. With mean 14.6 rounds of walking before a Sentinel can fire and 56
rounds to kill a Core, many games on this pool will reach turn 1000 and be decided by
`titanium_collected`. That is the objective this change already targets.

## Baseline on the new pool — the control is badly beaten

| # | Finding | Evidence | Status |
|---|---|---|---|
| F25 | The shipped `bot/` scores **4–26 (13.3%)** against `steward` on the 15-map pool, both seats | `tools/arena.py`, 30 games | CONFIRMED |
| F26 | It is out-delivered **6150 to 15380 titanium**, a margin of −9230 | same | CONFIRMED |
| F27 | Diagnostics over those 30 games: **739 idle rounds per game on average**, 209 idle runs of 6+ rounds, 157 units idle for ≥50% of the game, 80 oscillations, 36 turrets silent for 40+ rounds, 17 games owning a turret with an empty ammo pool | `tools/diag/detect.py` | CONFIRMED |

The 2.5:1 titanium deficit is the resource-denial thesis stated as a measurement: we are not losing
close fights, we are being out-resourced.


## Gating investigations — 6 questions, 12 agents, adversarially verified

Each probe's headline was re-derived by an independent verifier told to refute it. **Three of six
headlines did not survive.** Raw returns in `gating-raw.json`.

### G1 Healer vs grinder — arithmetic CONFIRMED, "unkillable" REFUTED

| metric | value | evidence |
|---|---|---|
| net HP/round on a forward turret | **6k − 8**, k = contact tiles we hold | 11 cells, `grindheal` |
| heal vs grind exchange | **4:1 in titanium, 2:1 in HP** | 272-round flat hold at 28 HP |
| heal on a building | works, +4 HP/1 Ti, and **stacks** simultaneously | 2 healers = +8 in one round |
| wasted healing at full HP | **zero** — `can_heal` is False, surplus healers spend nothing | 240 rounds, 0 Ti |
| contact tiles on a 1×1 turret | exactly **4**; surplus bots physically locked out | in-engine census |
| who bankrupts first at break-even | the **attacker** — B_ti 1250 → 6 by r800 | 800-round run |

**But the verifier broke the conclusion.** The probe hard-assigned disjoint tiles to each side. When
both sides genuinely race for the same 4 tiles, **the enemy arrives 3 rounds earlier, takes E/N/S,
and the turret dies at −2 HP/round on round 32** with the 2nd and 3rd escorts standing uselessly
outside. Forward turrets are holdable **only if we win the tile race** — a timing requirement, not a
cost one. Park the escort at build time; the builder that constructs the turret must never leave.

### G2 Sentinel first-strike — id order CONFIRMED, "decides completely" REFUTED

Lower global entity id fires first, survivor at exactly **4/40 HP in 11/11** bare duels. A head start
beyond winning the tie is worth **0 HP for a Sentinel, +7 for a Gunner**.

**But one builder healing +4 HP/round flips the winner to the HIGHER-id turret** (2/2, both mirror
directions). The duel is decided by escort, not by build order. Separately, a head start of ≥6 rounds
buys total turret denial — you shoot the site before they can build on it.

### G3 Passability — CONFIRMED, and it refutes the engine's own docstring

Only **Conveyor and Splitter** are walk-through, of 7 building types. **Team never matters on any
row.** The **allied Core is impassable in 64/64 configurations**, contradicting `is_tile_passable`'s
docstring. The three-way equivalence `is_tile_passable == can_move == did-move` holds only at
`move_cd == 0`.

### G4 CPU budget — CONFIRMED at 10 ms, with a hazard

The enforced limit equals `turn_timeout_ms` exactly — 509 chunks of work at tle=10 against 106 at
tle=2, a 4.8× ratio. The visualiser's 2 ms is only a display fallback for replays carrying no `tled`
flag. There is a real **+5% bank** (10 515–10 519 µs on first overrun).

**Hazard:** the engine never pre-empts Python. It stops a unit only at its next Controller API call,
so an API-free loop ran **110 580–138 218 µs uncut**. Long computation between API calls is not
protected by the engine; it just runs.

### G5 Store slots and role leases — CONFIRMED

A one-slot lease word `(id+1) << 10 | round`, renewed every round and challenged at
`round − stamp >= 2`, costs **zero extra slots** (`word >> 10` is the id the bot already stores).
**0 false evictions in 2620 lease-held rounds**, measured directly rather than inferred. Vacancy is
`2*(1+k)` rounds where k is consecutive claimants killed before confirming — 58 of 59 contested
handovers took 2 rounds, one took 4, a forced double-kill took 6.

### G6 Sabotage — REFUTED, and this one costs us a plan

Belt-sniping reproduces bit-exact at **2.18:1 against the attacker**: 3120 Ti spent to inflict
1430 Ti, with the victim replanting the cut link inside the same round (`empty=0` across 800 rounds).

The probe then claimed a flip — a 3 Ti barrier held on the terminal conveyor tile denying 91% of the
harvest at 1:6.5 in our favour. **That was a script artifact.** The victim was hard-coded to deliver
through one of its Core's 8 intake tiles. Against a victim that lays a 4-conveyor bypass one row
north, the identical 285 Ti attack denies **1.0%** of the harvest and costs the defender 74 Ti —
**3.85:1 against the attacker**.

**A Core has 8 intake tiles and a bypass costs 12 Ti. Belt sabotage is a trap at every price we can
pay for it.** The denial thesis has to rest on something with no cheap bypass — an occupied ore tile
has none, because the ore cannot be moved. That is now the load-bearing untested mechanic.


## Uncle Stewart ablations, Nash-weighted (base: steward, 15-map pool, both seats)

Baseline weighted score 0.451. Weights steward 0.442, vigil 0.200, heimdall 0.195,
odin 0.114, prospect_rushonly 0.050.

### Single changes -- all seven pass

| variant | weighted | gain | shape |
|---|---|---|---|
| wary_cost2 (coverage as +2 step cost) | **0.518** | +0.068 | up on ALL five surfaces |
| wary_cost12 | 0.518 | +0.067 | vigil +4, heimdall +4 |
| wary_cost (penalty 6) | 0.508 | +0.057 | |
| frontier_stake_hold | 0.507 | +0.056 | vigil +5, odin +4, prospect -3 |
| frontier_stake | 0.506 | +0.056 | vigil +3, odin +3, prospect -2 |
| ore_deny_preempt | 0.502 | +0.052 | vigil +7, odin +4 |
| frontier_stake_relay | 0.493 | +0.043 | |

### Stacks -- composition is sub-additive, and one pairing is destructive

| stack | weighted | gain | verdict |
|---|---|---|---|
| **stack_wf** (wary + frontier_stake) | **0.524** | +0.074 | SHIPPABLE, best gated |
| stack_wfh (wary + frontier_hold) | 0.557 | +0.107 | REJECTED, prospect -6 cliff |
| stack_wo (wary + ore_deny) | 0.507 | +0.056 | passes, but WORSE than wary alone |
| stack_all (all three) | 0.496 | +0.046 | REJECTED, and worse than every part |

**F28 Stacking is sub-additive.** wary +0.068 and frontier +0.056 would be +0.124 if
independent; stacked they give +0.074, about 60% of the sum.

**F29 Ore denial and danger-avoidance actively fight each other.** stack_wo scores 0.507
against wary_cost2's 0.518 alone -- adding ore denial to the danger-aware bot makes it
worse. The mechanism is visible in the design: ore denial sends builders to enemy-side ore,
which is precisely the ground the coverage penalty has just made expensive. Two changes
that each win alone can cancel, and only the stack test reveals it.

**F30 All three together is worse than any one of them.** stack_all 0.496 against 0.518,
0.506 and 0.502 for its parts. More accepted changes is not a better bot.

**F31 Seizing contested ore opens a hole against pure rushers.** Both frontier stacks lose
heavily to prospect_rushonly (stack_wfh 9-21, i.e. 30%), because committing a builder to
mid-map ore early leaves home thin. This is the one archetype weakness in the set and it is
the thing standing between us and stack_wfh's +0.107, the largest gain measured.

**F32 Two ablations inside the danger idea came back negative**, and both are general
lessons: coverage as a HARD BLOCK loses the mirror 14-16 and regresses two opponents, and
WITHDRAW-UNDER-FIRE subtracts from every surface it is added to. Pricing danger is worth
it; refusing to enter it, or fleeing once inside, is not.

**F33 The conveyor maze is dead at the premise.** Belts do not displace units at all --
measured three ways (own belt, loaded belt with stacks stepping every round, enemy-owned
belt), 40-60 idle rounds each, zero movement. There is nothing to recirculate.


## Diagnosis: why builders and turrets idle (root cause found and fixed)

**Symptom.** 71 idle runs in one game, units idle 37 consecutive rounds, "13 rounds for a
3-round path". Initially read as a pathfinding defect. It is not.

**F34 The idling is economic, not navigational.** Traced per unit per round: the worst
idlers are GUNNERS, not builders -- unit 22 fires rounds 15-21 then does nothing for the
remaining 67 rounds (91% idle). The team ammunition pool is 120 at round 2, drained to 3 by
round 23, and sits at 1-3 for the rest of the game while five turrets stand silent.

**F35 The bot builds four to eight times more turrets than it can feed.** Derived from
constants: a Gunner shot costs 4 Ti since 2.3.4 (it was 2) against passive income of
2.50 Ti/round, so passive sustains **0.62 gunners** firing every round and a full harvester
chain reaches **1.25**. The bot routinely builds five. Across 10 games on 5 maps, **22% of
all turret-owning rounds had too little ammunition to fire once** -- 81-85% on maps where
the economy delivered nothing, 0% where it delivered well. Dryness tracks delivery exactly.

**F36 Raising the ammunition gate treats the symptom and wins nothing.**
`MIN_AMMO_FOR_GUNNER` 20 -> 120 cuts dryness 54% -> 34% and banks far more titanium
(+12980 against heimdall), but the weighted score moves 0.451 -> 0.451. Denied turrets, the
bot simply holds the titanium: it has no other way to convert resources into wins. The
lever is income, not spending -- which is why the economy variants gained.

**F37 ROOT CAUSE: a doctrine constant tuned on a map pool and an engine that no longer
exist.** `doctrine.BLITZ_MAX_DISTANCE = 6` sends the whole team to attack with no economy
when the Cores are close. Its own comment documents the evidence honestly: measured "over
the 21 official maps" against showdown, sprint, duel, bridge and quarry -- **none of which
are in the current 15-map pool** -- and measured before 2.3.4, when a Gunner cost 10 Ti and
2 ammunition instead of 20 and 4, so a blitz needed half the titanium it needs now.

On `fjordgate` (inside the threshold) the base builds **0 harvesters, 0 conveyors, 5
gunners, collects 0 titanium, is 81% dry, and dies at turn 88.**

**F38 The fix.** `BLITZ_MAX_DISTANCE = 0`: weighted 0.451 -> **0.469 (+0.019)**, gaining on
four of five surfaces with no regression anywhere. On fjordgate: dryness 81% -> **0%**,
collection 0 -> 850, and a loss becomes a win. Setting it to 4 instead is byte-identical to
the base, which pins the mechanism exactly -- no pool map has a Core distance <= 4, so the
threshold only bites in the 5-6 band.

**What would have prevented it.** Nothing was careless: the constant carried a scrupulous
record of what it was measured on. What was missing is any check that the named evidence is
still valid. With half the map pool rotating weekly, **a constant justified by a named
instance set needs an expiry test** -- something that flags a tuned value whose cited maps
are no longer in the pool, or whose cited engine version has moved. That check is cheap and
would have caught this the morning the pool rotated.
