## ADDED Requirements

### Requirement: No unit is ever lost to an exception

`Player.run()` SHALL be structurally incapable of letting an exception escape, because the engine
permanently deletes the raising unit — and the shipped starter bot demonstrates this failure
(`bots/starter/main.py:369`, out-of-bounds `is_tile_empty`).

#### Scenario: Outermost guard
- **WHEN** any code path inside `run()` raises any `Exception` (including `GameError`)
- **THEN** the outermost handler absorbs it, increments a per-unit error counter, and the unit continues
  playing next round

#### Scenario: Per-entity-type isolation
- **WHEN** an exception occurs inside one entity-type branch (e.g. the gunner logic)
- **THEN** it cannot prevent other entity types from acting correctly in later rounds, and the failing
  branch degrades to a minimal safe behaviour rather than repeating the crash every round

#### Scenario: Bounds and vision guarded at the call site
- **WHEN** any `ct.*` call takes a `Position`
- **THEN** the position has passed an in-bounds check, and any `get_tile_env`/tile query is either
  vision-guarded (`is_in_vision`) or wrapped, since out-of-vision queries raise

### Requirement: Submission passes the engine's AST validator by construction

All shippable bot code SHALL conform to the engine's validator rules, enforced by a local pre-submit check
that reimplements them, so rejection happens at build time and never at the deadline.

#### Scenario: Banned constructs rejected locally
- **WHEN** shippable code contains a `finally:` block, a bare `except:`, a non-name exception handler type
  (e.g. `except mod.Error:`), or an exception name outside the builtin allowlist plus `GameError`
  (`BaseException`, `KeyboardInterrupt`, `SystemExit` are disallowed)
- **THEN** the local build fails with the same message the server would produce

#### Scenario: Packaging invariants hold
- **WHEN** the bot is packaged
- **THEN** the entry point is `main.py` with a top-level `class Player` (never `bot.py` — the CLI doc is
  wrong), no file carries a UTF-8 BOM, the bot directory contains no stray `.py` outside the bot itself
  (the validator recurses from the bot root), and no module relies on `__name__` (`player_mod` locally,
  `main` on the server) or imports `main`

#### Scenario: Sandbox-banned APIs never referenced
- **WHEN** shippable code is scanned
- **THEN** it contains no use of `open()`, filesystem access, `time.*` wall-clock reads, `threading`,
  `subprocess`, `socket`, `sys._getframe`, or any C-extension import (numpy cannot load in the bot
  sub-interpreter at all), since the server sandbox deletes or fakes these even though local runs allow them

### Requirement: CPU budget respected with ordered degradation

Each unit's turn SHALL be ordered so a timeout costs planning, never action — an interrupted `run()` does
not resume, so expensive work running first would soft-lock the unit into never acting.

#### Scenario: Mandatory actions precede planning
- **WHEN** a unit's turn begins
- **THEN** cheap mandatory actions (fire/heal/build/move already decided last round) execute before any
  expensive recomputation, and planning is gated on a `get_cpu_time_elapsed()` budget check on platforms
  where the timer works, with staggered recomputation (`unit_id % K == round % K`) bounding worst-case
  rounds

#### Scenario: Local budget is derated
- **WHEN** CPU cost is assessed locally
- **THEN** the local budget is 3 ms ≙ the ladder's 10 ms (Windows/Linux delta ~1.9× plus Graviton3 margin),
  and any submission changing the compute profile is confirmed with `fcode match test` first

### Requirement: Deterministic randomness

The bot SHALL never call the global `random` module; any stochastic choice uses a per-unit
`random.Random(seed)` derived from stable game values (e.g. unit id, round), so that identical inputs
reproduce identical games in the harness.

#### Scenario: Reproducible A/B
- **WHEN** the same two bots run on the same map and sides twice
- **THEN** the results are bit-identical, preserving the harness's zero-variance evaluation property
