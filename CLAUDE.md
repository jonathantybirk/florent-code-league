This repo uses uv.

# Florent Code League — project notes

A bot-competition framework (`fcode`). Bots control a team's `Core`,
`BuilderBot`s, and turrets each round via a `Controller` (`ct`) object;
`Player.run(ct)` is called once per unit per round. Full API/rules docs live
under `docs/official/` — read the relevant `docs/official/docs/game-rules-*.txt`
or `docs/official/docs/robot-api.txt` before assuming how a mechanic works;
several surprises below were only found by testing, not by reading docs.

## Tooling

- Package/env management: `uv` (`uv run pytest`, `uv run fcode ...`). The
  venv may warn about `VIRTUAL_ENV` mismatching `.venv` if a different venv
  (e.g. conda) is active in the shell — harmless, `uv run` still targets
  `.venv` correctly.
- The `fcode` CLI is the compiled real engine, installed in `.venv`. Nested
  test bots (`bots/test/<name>`) aren't found by bare name — pass the path:
  `uv run fcode run bots/test/foo bots/test/foo [map] [--seed N]`.
- `maps/` holds the `.map26` competition pool (`fcode maps sync` to refresh).
- Tests: `uv run pytest` (or a specific file). Config lives in
  `pyproject.toml`.

## Bot layout & conventions

- `bots/<name>/main.py` (or `bots/<name>.py`): a `Player` class with
  `__init__` and `run(self, ct)`, dispatching on `ct.get_entity_type()`
  (`CORE` vs `BUILDER_BOT` vs turret types). The engine only puts a bot's
  own directory on `sys.path`, so multi-file bots are a *flat* namespace
  (`state.py`, `constants.py`, ...), not a proper package — see
  `common/toolbox.py` and `tests/botimport.py` for why.
- `bots/test/` holds non-competitive scratch/verification bots, two kinds:
  - **Library modules** meant to be imported into a real bot later (e.g.
    `bots/test/econ`, `bots/test/econ2`) — pure calculation, no `run()`
    side effects of their own, documented in a `README.md` alongside.
  - **Probe bots** that play a real match to answer one empirical question
    and report the answer via `ct.resign(message=...)` — `fcode run` prints
    the resign message to the terminal. See `bots/test/splitter_probe`,
    `bots/test/econ_demo`, `bots/test/vision_probe`. These document
    themselves via a thorough module docstring instead of a separate
    README — follow that pattern, don't add a README for a probe.

## Testing: fake_controller — what it does and doesn't model

`tests/fake_controller.py` + `tests/botimport.py` let you exercise a bot's
logic against real `fcode` types (`Direction`, `EntityType`, `Position`, ...)
without running the full engine — see `tests/test_econ.py` /
`tests/test_econ2.py` for the pattern (`bot_on_path` + `importlib`, a
`World` with `spawn`/`set_stored_resource`, `world.controller_for(id)`).

**Known fidelity gap, confirmed by testing (see `bots/test/vision_probe`):
`fake_controller` does NOT enforce vision at all.** Every getter
(`get_tile_building_id`, `get_entity_type`, `get_stored_resource`, ...)
returns full ground truth regardless of the calling unit's vision. The real
engine is strict and uniform about this: querying a position *or an id you
already hold* outside the caller's current vision raises
`GameError: Position out of vision range` — not `None`, not stale data.
Any code that queries tiles/ids without first checking `ct.is_in_vision(...)`
will crash a real match the moment something leaves vision. Always gate
these calls, and don't trust a fake_controller test alone to catch a missing
vision check — write a probe bot and run it for real if vision behavior is
load-bearing for what you're building.

## Performance

- **10 ms CPU budget per unit per round** (`docs/official/docs/game-rules-
  overview.txt`), plus a small ~5% banked buffer. A CPU-time interruption
  just skips that unit's turn (retried fresh next round); an **uncaught
  exception permanently destroys the unit** — wrap risky calls, and never
  let `run()` raise. Use `ct.get_cpu_time_elapsed()` to self-monitor.
- Map size is capped at 30×30 (900 tiles) — informs what "O(width×height)"
  actually costs in practice; benchmark at that scale, not asymptotically.
- `fcode.Direction.delta()`/`.opposite()` rebuild a dict literal on *every
  call* rather than caching one (see `fcode/_types.py`) — cheap once, not
  cheap in a hot loop over many tiles. Precompute
  `{d: d.delta() for d in CARDINALS}` once at module scope if you're calling
  either on more than a handful of directions per round (see `_DELTA`/
  `_OPPOSITE` in `bots/test/econ2/main.py`).
- When benchmarking, use real `fcode` types via the `fake_controller`
  harness, not a from-scratch reimplementation of the game types — a
  standalone reimplementation can (and did, once) meaningfully understate
  real cost by using cheap cached lookups the real library doesn't have.
  Conversely, don't trust a wall-clock number taken *through*
  `fake_controller` for methods like `get_tile_building_id` — its
  `building_at()` is a linear scan over every entity in the `World`, which
  can dominate the number and has nothing to do with the real engine's
  (almost certainly indexed) implementation. `cProfile` before concluding
  which cost is real.

## Game-mechanic facts learned the hard way (verified, not assumed)

- `GameConstants` has no dedicated harvester-output-rate constant — a
  Harvester's "10 Ti every 4 rounds" reuses `PASSIVE_TITANIUM_AMOUNT`/
  `PASSIVE_TITANIUM_INTERVAL` (the *team's separate* passive-income
  mechanic) purely because the numbers happen to coincide. `bots/test/econ`
  and `bots/test/econ2` both do this by convention; keep doing so rather
  than hardcoding `10`/`4`.
- Splitters: the real one round-robins only among outputs that currently
  have something to receive (a Conveyor/Splitter/Core), not blindly through
  all 3 geometric slots — weight is `1 / live outputs`, not a flat `1/3`.
  See `bots/test/econ/README.md` and `bots/test/splitter_probe`.
- `ct.build_conveyor()` (and presumably the other `build_*` calls) return a
  real `int` id in the real engine, contradicting `docs/official/docs/
  robot-api.txt`'s table (which lists the return as `None`) — the
  `fcode/_types.py` `TYPE_CHECKING` stub had it right. Trust the stub over
  the doc table if they disagree.
- A Core's 2×2 footprint: querying `get_tile_building_id` on any of its 4
  tiles returns the *same* building id.

## Git / workflow

- Branch `viktor`, remote `origin` (`git@github.com:jonathantybirk/
  florent-code-league.git`), tracking `origin/viktor`.
- Only commit/push when explicitly asked. Stage specific files, not `-A` —
  this repo tends to have unrelated in-progress changes sitting in the
  working tree (e.g. a scratch notebook); don't sweep those into an
  unrelated commit.

## Working style this project has responded well to

- Ground claims in the actual docs/rules text or in an empirical test
  (`fake_controller` for logic, a real `fcode run` probe bot for anything
  vision/timing/engine-behavior-sensitive) rather than assumption — this
  repo's own `splitter_probe`/`econ_demo`/`vision_probe` precedent is to
  settle exactly this way, not to reason from the docs alone.
- Real benchmark numbers (via `fake_controller`, `cProfile` when something
  looks off) over theoretical Big-O claims, especially given the hard 10ms
  budget — see the Performance section above for a case where the two
  disagreed.
- State limitations/caveats plainly rather than let a confident-sounding
  summary imply more coverage than exists (e.g. "this computes expected
  flow but doesn't model Splitter dilution" beats staying silent about it).
