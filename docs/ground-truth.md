# Engine Ground Truth Register

Every claim our bot logic depends on, with its verification status. **Nothing below `VERIFIED-WIN` may
influence bot logic; nothing below `VERIFIED-LINUX` may gate strategy selection.** See
`openspec/changes/elias-verification-and-offense/` for the protocol.

Engine: `fcode 2.2.0`. Windows leg = cp313 win_amd64. Linux leg = WSL2 Ubuntu x86_64, cp312 manylinux.
Ladder runs AWS Graviton3 (ARM) — **no claim here has been confirmed on ARM.**

Status: `VERIFIED-LINUX` > `VERIFIED-WIN` > `ASSERTED` > `REFUTED`

---

## Economy and scoring

| ID | Claim | Status | Evidence |
|---|---|---|---|
| G01 | `titanium_collected` counts **only stacks that land on a Core footprint tile**. Passive income contributes 0. | `VERIFIED-WIN` | Idle bot: 3000 Ti banked, **0 collected**, identical on 6 maps. 12 purpose-built probe bots. Re-confirmed on **all 15 maps** by `arena`: `idle` banks exactly 3000 and collects exactly 0 in all 30 oriented games. |
| G02 | An **unconnected harvester contributes exactly 0** — and a chain that dead-ends **one tile short of the Core** also scores 0. | `VERIFIED-WIN` | `p_chain1_partial` (live harvester, 2 conveyors, dead-ends 1 tile short): 0 collected. Adding one final conveyor → 2490. |
| G03 | Tiebreak order is `titanium_collected` > `harvesters` > `titanium_stored` > coinflip. | `VERIFIED-WIN` | Head-to-head: 1 connected harvester (2490) **beat** 3 unconnected (0). Reverse matchup confirmed symmetrically. |
| G04 | One connected harvester ≈ **2470–2490 collected** over a match (10 Ti / 4 rounds). Delay in completing a chain costs ~2.5 collected per round. | `VERIFIED-WIN` | 2490 = 249 stacks × 10 Ti; exact arithmetic reconciles to the unit against `a_titanium`. |
| G05 | Delivery into a **turret scores 0 collected**, and a turret accepts exactly **one 10-Ti stack** before jamming the chain permanently. | `VERIFIED-WIN` | Gunner self-reported `ammo=10`, `a_titanium_collected 0`. Upstream conveyors backed up and never cleared. |
| G06 | **Destroying a loaded conveyor refunds nothing.** `docs/game-rules/game-rules-conveyors.md` is wrong. | `VERIFIED-WIN` | 246 destroy/rebuild cycles: balance fell exactly 3 Ti per cycle, never rose. |
| G07 | Cost scaling is **one global scale across all entity types**: `cost = floor(scale × base)`. | `VERIFIED-WIN` | Spawning one Builder Bot raised harvester cost 20→24 and gunner 10→12. |

## Combat

| ID | Claim | Status | Evidence |
|---|---|---|---|
| G10 | **Every turret API is team-blind**: `get_gunner_target`, `can_fire`, `can_fire_from`, `fire` all ignore team. Turrets destroy their own units and buildings. | `VERIFIED-WIN` (×2 independent) | Own builder dead in 4 shots; own barrier in 3; own conveyor in 2. A Gunner facing its own Core ground it 500→0 in 50 shots and **lost the match** on `core_destroyed`. |
| G11 | A **friendly entity in the ray blocks the turret indefinitely** — target flips to the friendly and `can_fire` on the enemy behind goes False. | `VERIFIED-WIN` | Target stayed on a friendly conveyor for **373 consecutive rounds**. One conveyor shields an enemy permanently. |
| G12 | The shipped starter's `_run_gunner` therefore **fires on its own team**. | `VERIFIED-WIN` | 18 instrumented matches: 22,526 target reads, **all own-team, zero enemy**; 2,605 shots fired, **all friendly** (1,655 harvesters, 950 gunners). Second run: 61% of shots friendly. |
| G13 | Builder Bots **cannot attack any adjacent tile** — `can_fire` False and `fire()` raises vs adjacent enemy Core, Barrier, Conveyor, Harvester, and Builder Bot. Docs are wrong about range. | `VERIFIED-LINUX` | Windows and Linux probe logs **byte-identical after EOL normalization**. Not a platform regression. |
| G14 | **Range-0 sabotage DOES exist**: stand *on* an enemy conveyor/splitter tile and fire at your **own tile** — 2 dmg for 2 Ti, kills a 20 HP conveyor in 10 rounds. | `VERIFIED-LINUX` | `CAN_FIRE=True`, hp 20→18→…→destroyed at shot 9, `delta_ti=-2` per shot. Confirmed on both platforms. |
| G15 | Sentinel's attack pattern is a **3-row band (17 tiles)**, not a single-tile line, and it has no `get_sentinel_target()`. | `VERIFIED-WIN` | `get_gunner_target()` on a Sentinel raises `GameError: Unit is not a gunner`. A Sentinel destroyed its own ammo conveyor inside its own band. |
| G16 | A forward Gunner + one adjacent Harvester kills a 500 HP Core with **zero conveyors**; **13/15** maps have such a firing position. | `VERIFIED-WIN` | Geometry independently recomputed from the atlas: 13/15 confirmed (all but `quarry`, `runestone`). Implemented in `bot/main.py` and executed live: Core destroyed on turn **66** (sprint), **68** (duel), **70** (crossfire), **72** (twins), **77** (strait), **78** (skerry), **80** (longship), **85** (hive), **101** (aurora). |
| G17 | The rush **converts on 9 of 15 maps in practice**, not 13. `atoll`, `fjord`, `pinch`, `quarry`, `runestone`, `vault` ran the full 1000 rounds despite having valid geometry. | `VERIFIED-WIN` | Per-map audit vs an inert opponent. Cause not yet diagnosed (walk length and terrain are suspects). `bot/main.py` gates the rush on the measured list, not on `rushplan.recommendation()`, which was optimistic on all six. |

## Engine and platform

| ID | Claim | Status | Evidence |
|---|---|---|---|
| G20 | **Module-level globals are NOT shared between units** — each runs in its own CPython sub-interpreter. Only the 16 store slots (1-round lag) and per-unit `self` persist. | `VERIFIED-WIN` (×3 independent) | Distinct `globals_id`, distinct `_interpreters.get_current()`, same pid/thread. |
| G21 | **`get_cpu_time_elapsed()` returns 0 on Windows and `--tle` is never enforced**; on Linux both work correctly. | `VERIFIED-LINUX` | Windows: `cpu_us=0` after a 60 ms burn, actions still landed. Linux: `cpu_us=67432` real; over-budget turns produced no output at all. |
| G22 | An over-budget turn **silently voids everything after the threshold** (actions, prints, resign) but the **unit survives** to act next round. | `VERIFIED-LINUX` | Linux `tle=10`: hog3 logged `enter` but never `after`; spawns voided; unit alive next round. Threshold ~300k loop iterations ≈ 9 ms. |
| G23 | `ct.get_tile_env(pos)` **raises** for tiles outside vision; uncaught exceptions **permanently delete the unit**. | `VERIFIED-WIN` | `GameError: Position out of vision range`. Starter crashed its own builders **520 times across 90 games** at `main.py:369`. |
| G24 | Entry point is **`main.py`**, not `bot.py`. `docs/cli/cli-submitting.md` is wrong. | `VERIFIED-WIN` | Engine binary `importlib.import_module('main')`; `submission.py` `_make_zip()` requires `main.py`. |
| G25 | The AST validator rejects `finally:`, bare `except:`, non-Name handler types, and non-allowlisted exception names (`BaseException`/`KeyboardInterrupt`/`SystemExit` banned). | `VERIFIED-WIN` | Triggered locally; exact messages captured. |
| G26 | Engine is **deterministic**; 100% of outcome variance is between-map, 0% within-map across seeds. `--seed` affects only the coinflip tiebreak. | `VERIFIED-WIN` | Identical results on seeds 1/7/42 and across 14/15 maps at 3 seeds. |
| G27 | Team A wins ~58–60% of identical-bot mirrors (its Core acts first). Mirrored scoring is mandatory. | `VERIFIED-WIN` | Unpaired estimate +1024 Ti vs paired −106 — unpaired was side bias with the sign wrong. |
| G28 | **numpy cannot be imported inside the bot sandbox at all** — single-phase-init C extension, engine's trial sub-interpreter takes the only slot. | `VERIFIED-WIN` | `ImportError: cannot load module more than once per process`, reproduced on Windows and Linux. |
| G29 | `print()` from a bot does **not** reach stdout under `run_game` or `fcode run` — it is embedded in the `.replay26`. | `VERIFIED-LINUX` | Recovered via byte-scanner. Contradicts an earlier toolchain note. |
| G30 | A stray `__pycache__` inside a bot directory makes the engine **silently run the bot as inert**. | `VERIFIED-WIN` | Logs from such runs look like "the bot does nothing" with no error. |
| G31 | **A Builder Bot does not act on the round it is spawned** — contradicting `game-rules-core.md` ("becomes active in the same round"). | `VERIFIED-WIN` | By its first turn the Core has already incremented the spawn counter, so **no builder ever reads ordinal 0**. Gating a role on `ordinal == 0` silently disables it. Assign roles by store claim-then-confirm instead. |
| G32 | Map symmetry: only **4** of 15 maps are not 180°-rotational — `longship` (mirror_x), `pinch`/`strait`/`twins` (mirror_y). **No map is diagonal.** | `VERIFIED-WIN` | Determined empirically per map (a transform must map walls onto walls, ore onto ore, and Core A's footprint exactly onto Core B's). Corrects an earlier claim of 6 maps with `atoll` diagonal — `atoll` is rot180. 1414 assertions pass. |
| G33 | The Core's `get_position()` is the **top-left anchor** of its 2×2 footprint, and `(width, height, own_core_pos)` is a **unique fingerprint** across all 15 maps. | `VERIFIED-WIN` | Probed `get_tile_building_id` at all four offsets in-engine on 15 maps × both sides, 30/30. Enables round-0 map identification with zero scouting (~0.23 µs per lookup). |
| G34 | `get_attackable_tiles_from()` is callable from a **Builder Bot**, not only from a turret. | `VERIFIED-WIN` | Probe-verified. Lets a builder evaluate turret geometry before committing to a build site. |
| G35 | `import heapq` **works inside the bot sandbox**, despite numpy failing (G28). | `VERIFIED-WIN` | Pure-Python stdlib modules import fine; the G28 failure is specific to single-phase-init C extensions. |

## Measurement methodology

| ID | Claim | Status | Evidence |
|---|---|---|---|
| **M01** | **A 30-game mirrored sweep has a noise floor of ±2–4 games** for any change that perturbs pathing. Deterministic does NOT mean low-variance across code changes. | `VERIFIED-WIN` | Control experiment: a variant whose tie-break provably **cannot lengthen any path** (only re-orders equal-length ones) still moved **7 games** across the sweep — +2 vs luc1, −4 vs frontier. Choosing a different shortest path cascades into a completely different game. **Consequence: only effects ≥5 games are trustworthy from one 30-game sweep.** Smaller deltas need more maps, more opponents, or a mechanism-level measurement (e.g. kill turn) rather than win/loss. |
| G31 | **A deterministic engine does not mean reproducible results.** A bot that uses `random` without seeding is non-reproducible: each unit gets its own sub-interpreter (G20), and a fresh interpreter seeds the Mersenne Twister from `os.urandom`, which the sandbox does **not** stub. The shipped starter does exactly this. Fix: `random.seed(ct.get_id())` on the unit's first turn. | `VERIFIED-WIN` | Two identical 4-map sweeps of `starter` vs `starter`: all 4 maps disagreed on titanium/units/buildings and **fjord flipped the winner** (A→B). `idle` vs `idle` over the same maps was bit-identical. After seeding, `starter_fixed` was bit-identical over 3 repeats; the full 30-game report diffed clean line-for-line across two runs. |
| G32 | The AST validator does **not raise** — it **terminates the process with exit code 10**. In a batched harness this kills the worker and every remaining match in its chunk. Exit code 11 = bot failed to load. | `VERIFIED-WIN` | 9 violation cases each produced rc=10 + `Bot A failed validation: ValueError: <bot>/main.py:N: ...` on stderr; 3 legal cases ran to completion. |
| G33 | The engine **creates the `__pycache__` of G30 itself**: its importlib trial-load writes `__pycache__/main.cpython-*.pyc` next to the bot's `main.py` on every run, unless `PYTHONDONTWRITEBYTECODE` is set. So running a bot once can poison it for the next run. | `VERIFIED-WIN` | `__pycache__` appeared in bot dirs after in-process `run_game` calls; zero appeared across 210+ matches run through `arena/` workers, which set `PYTHONDONTWRITEBYTECODE=1`. |
| G34 | When **every tiebreak metric ties**, `win_condition` is `coinflip` and at seed 1 it resolved to **Team A on 15/15 maps** — a 100% side bias, not the ~58-60% of G27. Mirrored scoring cancels it; unmirrored scoring would be catastrophically wrong. | `VERIFIED-WIN` | `idle` vs `idle`, all 15 maps: `{'coinflip': 15}`, winner `A` every time. |

## Open — probes failed to session limits, must be run

| ID | Claim | Priority |
|---|---|---|
| G16 | Forward-gunner Core kill at turn 77 / 13-of-15 ore-adjacent firing positions | **P0** — the offence doctrine rests entirely on this |
| G40 | Turret ammo magazine only refills at exactly 0 (inverts fire discipline) | P1 |
| G41 | Launcher mechanics: can a thrown bot act on landing? chainable? enemy bots throwable? | P1 |
| G42 | Harvesters block movement (contradicts the reference table) | P1 |
| G43 | Harvester output splitting / parasite-conveyor denial | P2 |
| G44 | Anything at all on Graviton3/ARM | P1 — no claim here is ARM-confirmed |

---

## Corrections to repository documentation

Doc errors found so far, in addition to the repo's own "Correction vs. the official docs" blocks — **two of
which are themselves wrong** (builder attack range; conveyor refund):

1. `docs/cli/cli-submitting.md` — entry point is `main.py`, not `bot.py`. (G24)
2. `docs/game-rules/game-rules-conveyors.md` — destroying a loaded conveyor refunds nothing. (G06)
3. `docs/game-rules/game-rules-builder-bot.md` — builders cannot attack adjacent tiles at all; the real
   attack is range-0 on their own tile. (G13, G14)
4. `docs/game-rules/game-rules-turrets.md` — Sentinel fires a 3-row 17-tile band, not a single-tile line. (G15)
5. `docs/game-rules/game-rules-reference.md` — "Harvester blocks movement: No" is disputed. (G42, open)
6. Nothing documents that **turrets are team-blind** — the single most consequential fact in the game. (G10)
