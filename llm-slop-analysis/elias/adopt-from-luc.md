# What to take from `luc1`, and what the recorded games revealed

Two sources: a function-level read of `bots/rivals/luc1` (2432 lines, 10 files), and six recorded games
against him in `replays/`.

---

## Part 1 — techniques `luc1` has that AutistimusPrime does not

Ranked by expected value to us given what we already measured.

| # | Technique | His implementation | Why it matters to us |
|---|---|---|---|
| L1 | **Plan the conveyor route before building it** | `_plan_conveyor_path_bfs`, `_plan_conveyors` | We lay belt *by walking* — the route is whatever path the builder happened to take. He BFS-plans the whole chain first, so it is shortest and never bends into a dead end. Directly attacks our repeated one-harvester deficit. |
| L2 | **Verify a chain reaches the Core before committing** | `_source_feeds_connected_line`, `_supply_chains_to_core` | A chain one tile short scores **exactly zero** (G02). He checks connectivity as a precondition; we discover it by finishing. This is the single most expensive mistake the game allows. |
| L3 | **Launcher relay** | `_closest_forward_launcher`, `_best_launcher_position`, `_best_landing_distance`, `_wait_for_launch` | A builder walks 1 tile/round; a throw moves it ~5 in one action. Our probe rated launchers LOW_VALUE *for economy* — but the recorded games show the luc1 matchup is a **rush race decided in single turns**, so this needs re-testing specifically as rush-delivery. |
| L4 | **Enemy supply-chain takeover** | `_run_enemy_supply_takeover`, `_replace_final_conveyor_with_gunner`, `_replace_penultimate_conveyor_with_splitter` | Replace the last conveyor of *their* belt with *our* gunner, so their harvester feeds our siege. **Our improvement:** the atlas tells us where their belt must run before they build it, so we can pre-position instead of scouting. |
| L5 | **Splitters** | `_replace_penultimate_conveyor_with_splitter` | We never build one. One harvester = 2.5 Ti/round = exactly one continuously-firing Gunner; a splitter bus feeds 2-3 turrets from one chain. |
| L6 | **Deterministic ore partitioning** | `ores[i::n]` by builder index | Zero-communication work division. We spend store slots on claims to achieve the same thing, and the slots are scarce. |
| L7 | **Gunner placement scoring** | `_seek_satisfying_gunner_endpoint`, `_gunner_endpoint_priority` | We only ever place the one gunner the rush plan names. He scores candidate endpoints, so he can build a *second* threat when the first is answered. |
| L8 | **Sentinel facing choice** | `_sentinel_facing`, `_direction_distance` | Sentinel facing is permanent and its arc is a 17-tile band (G15). We never build sentinels at all. |
| L9 | **Survey and recovery planning** | `_run_infrastructure_survey`, `_plan_survey_recovery` | Explicit re-plan when the world diverges from the plan. Our equivalent is a `stuck` counter, which the nav bug proved can silently never fire. |
| L10 | **Routes that sabotage opportunistically** | `_plan_route_with_optional_sabotage` | Route choice that cuts an enemy belt en route, at no extra travel cost. |

**The meta-lesson, already adopted:** he found `fcode/data/docs/spec.md` bundled *inside the installed
package* — a primary source closer to the engine than the scraped website every other bot is built from —
and then still probed the running engine to correct it. That discipline is why he was right about builder
attack semantics long before our two verification workflows established the same thing.

---

## Part 2 — what the recorded games actually showed

Six games vs `luc1`, all in `replays/`.

| Map | Side | Result | Decided |
|---|---|---|---|
| sprint | a | **WIN** | our kill, turn 67 |
| twins | a | LOSS | his kill, turn 72 |
| vault | a | LOSS | his kill, turn 90 |
| aurora | a | LOSS | his kill, turn 103 |
| quarry | a | LOSS | his kill, turn 109 |
| sprint | b | LOSS | his kill, turn 306 |

### R1. The matchup is a pure rush race — nothing else
**Every game ends in a Core kill inside ~110 rounds.** Not one reaches the round-1000 economy tiebreak.
Defence and economy are both irrelevant to this matchup: you cannot out-survive a race, you win it by
arriving first. This invalidates the direction we had been aiming (survive his attack) and replaces it
with a single objective: **shave turns off our kill**.

### R2. Our rush runs slower than its own plan when contested — highest-value bug
On `twins` the precomputed kill turn is **64**. We died at **72**. If the rush executed at planned speed we
would have won outright. Against an inert opponent the same plan hits its predicted turn exactly (30/30),
so something an opponent does delays us. Candidates:
- our rusher's BFS routes through tiles his units occupy, and re-plans each time they move;
- his builders physically block a corridor on the way;
- our own economy builders (now 6 of them) get in the rusher's way;
- the rusher stops to heal or sabotage en route.

### R3. Large side asymmetry on a symmetric map
`sprint` is a **win on side A at turn 67** and a **loss on side B at turn 306** — same map, same bots. Team A
acts first every round (G27, worth ~58-60% in mirrors), and in a race measured in single turns that
compounds. Needs checking whether our B-side rush is *systematically* slower or whether this is one map.

### R4. On the maps we lose, we collect literally nothing
`quarry` and `vault` show `ours = 0` collected. We die with no economy at all, so those losses are total —
no tiebreak fallback if the rush is answered. The rusher may also still be wedging economy on exactly the
maps where the walk is longest.

---

## Execution order

1. **R2 — diagnose and fix the contested-rush slowdown.** Our win condition against him is arriving first,
   and we are currently slower than our own plan. Biggest single lever.
2. **R3 — side-asymmetry audit.** If the B-side rush is systematically slower, that is up to half our games.
3. **L1 + L2 — planned, connectivity-verified conveyor routes.** The economy fix that survives being
   answered, and the fallback R4 says we do not currently have.
4. **L3 — re-test launcher relay as rush delivery** (not as economy, where it already measured LOW_VALUE).
5. **L4/L5/L7 — takeover, splitters, second gunner.** Only once the race is won.
