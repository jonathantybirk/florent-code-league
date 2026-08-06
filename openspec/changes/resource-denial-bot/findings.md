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
