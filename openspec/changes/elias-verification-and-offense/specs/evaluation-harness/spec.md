> **Measured before the Aug 4 turret patch (fcode ≤ 2.3.3).** Everything below was
> measured when turrets were stronger. The 2026-08-04 balance pass (fcode 2.3.4)
> changed the Gunner to 25 HP (was 40), 20 Ti (was 10), +20% cost scaling (was
> +10%), 7 damage (was 10) and 4 ammo per shot (was 2), and the Sentinel to 40 HP
> (was 30) on a 2-round reload (was 3). That balance pass is the only rules change
> in 2.3.4, so conclusions here that do not turn on turret strength still stand —
> but every turret-heavy number needs re-measuring before it is trusted again.

## ADDED Requirements

### Requirement: In-process, exhaustive, mirrored evaluation

The harness SHALL evaluate bot pairs via `fcode.fcode_engine.run_game` (not the CLI), over the exhaustive
set of pool maps × both sides, scored antisymmetrically.

#### Scenario: Exhaustive sweep replaces sampling
- **WHEN** two bots are compared
- **THEN** the harness runs all 15 pool maps × 2 side assignments (30 games, ~10 s), never replicates a
  completed (bots, map, side) triple, and never varies `--seed` expecting information (seed affects only the
  coinflip tiebreak)

#### Scenario: Side bias cancelled by construction
- **WHEN** a comparison score is produced
- **THEN** it is `S(X,Y) = ½[s(X as A, Y as B) − s(Y as A, X as B)]` per map, so Team A's first-mover
  advantage (~58–60% in identical-bot mirrors) cancels exactly and `S(X,X) = 0`

#### Scenario: Held-out maps guard overfit
- **WHEN** any parameter tuning or strategy selection is performed
- **THEN** 3 designated maps are excluded from the tuning loop and reported separately, and a tuning result
  that improves pool maps while degrading held-out maps is treated as overfit

### Requirement: Worker processes survive sub-interpreter finalisation

Parallel execution SHALL use one-shot subprocess workers that terminate with `os._exit(0)`, matching the
engine's own pattern, because fork-based `ProcessPoolExecutor` dies on sub-interpreter cleanup.

#### Scenario: Parallel sweep
- **WHEN** a sweep larger than one comparison runs
- **THEN** the runner fans out K subprocess workers (K ≈ physical cores) with `PYTHONPATH` set in the worker
  env, each running batches of `run_game` and emitting one JSON line per game, with a hard per-worker
  timeout, and a worker that dies or hangs records its games as `crashed` losses rather than disappearing

### Requirement: Crash and CPU regressions fail the build, not the ladder

The harness SHALL surface unit deletion and CPU overruns as first-class results, since both are silent in
the engine's result dict.

#### Scenario: Strict mode
- **WHEN** the pre-submission gate runs
- **THEN** `--strict` fails if any of our units was deleted by an exception in any of the 30 games
  (detected via traceback capture on stderr/replay), and fails on any TLE event in a Linux `--tle 10` run

#### Scenario: Fitness includes CPU
- **WHEN** candidate bots are ranked
- **THEN** per-turn CPU cost is a scoring term — a policy near the 10 ms ceiling collapses harness
  throughput ~200× and is undeployable regardless of strength

### Requirement: Zoo of reference opponents

The harness SHALL maintain a fixed zoo — at minimum: `idle` (does nothing — also the absolute economy
benchmark, since the tiebreak metric is absolute), a repaired `starter` (the shipped bot with its
out-of-bounds crash fixed, as the field median), `rush` (our own forward-gunner doctrine), `greed` (max
connected harvesters), and each archived champion — and every candidate SHALL be gated on the full zoo.

#### Scenario: Champion promotion
- **WHEN** a candidate claims to beat the current champion
- **THEN** promotion requires the full exhaustive sweep against the entire zoo, aggregated as
  0.7·mean + 0.3·min so a catastrophic loss to one archetype blocks promotion, and the dethroned champion
  enters the zoo permanently

#### Scenario: Teammate bots as zoo members
- **WHEN** a teammate branch (`x/jon`, `x/luc`, `x/llm-RL`) produces a runnable bot
- **THEN** it is added to the zoo under its branch name, giving every teammate a standing, reproducible
  benchmark of all bots against all bots
