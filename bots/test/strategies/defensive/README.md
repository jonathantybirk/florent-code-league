# Turret-vs-turret threat geometry

`main.py` answers three tactical questions about known enemy turrets: **is
this tile safe to build on**, **which enemy turrets could a new turret here
threaten**, and **if a friendly turret ends up in enemy line of fire
anyway, where can its healer stand safely**?

It's a pure geometry library with no side effects and no `ct` calls at all
— nothing here moves, builds, spends, or observes anything — meant to be
wired into a real bot's `run()` later, same shape as
[`bots/test/econ2`](../../econ2/README.md). There's no `run()` method
here.

## The tactical idea

- **A Gunner's threat is a circle.** It can rotate (`ct.rotate()`, 10 Ti +
  1 round cooldown) to face any of its 8 possible directions, so over time
  it can hit anything within `GUNNER_RANGE_SQ` regardless of which way it
  happened to be facing when last observed. Range is the *only* thing
  that keeps you safe from one — its cached facing tells you nothing
  reliable about future safety.
- **A Sentinel's threat is a single fixed ray.** It never rotates, so
  once its facing is known, everything off that one line is safe from it
  *at any distance* — but its reach along that line (`SENTINEL_RANGE_SQ`)
  is more than double a Gunner's.

This is the offensive advantage the user's own scouting creates once an
enemy turret is placed and observed: a Sentinel built outside a spotted
Gunner's circle, but on a line the Sentinel is free to commit to, can
threaten that Gunner while staying permanently out of its reach; a Gunner
tucked off a spotted Sentinel's one ray is safe from it no matter how
close it stands. `threatens()`/`is_safe()` are the primitives for either
side of that trade; `best_cluster_placement()` ranks candidate tiles by
how many known enemies a single new turret could threaten while staying
safe from all of them.

## API

- **`EnemyTurret(position, etype, direction=None, last_seen_round=None)`**
  — one observed (or last-known) enemy turret. See
  [Data source](#data-source) for what populates this.
- **`threatens(turret, tile) -> bool`** — could `turret` ever hit `tile`?
  Conservative in both directions that matter for safety (see
  [Limitations](#limitations)): no obstruction modeling, and a cached
  Gunner facing is ignored entirely (see above).
- **`is_safe(tile, enemies) -> bool`** — `not any(threatens(e, tile) for e
  in enemies)`.
- **`gunner_coverage(position, enemies) -> int`** — how many known enemies
  a Gunner at `position` could eventually hit by rotating. Just a range
  check: rotation is cheap and free to redo, so there's no single-line
  commitment to model, unlike a Sentinel.
- **`best_sentinel_facing(position, enemies) -> (Direction | None, int)`**
  — the one facing (of 8) that lines up with the most known enemies, and
  that count. A Sentinel can never retarget off its build-time facing, so
  only enemies exactly on one chosen ray ever count.
- **`Placement(position, turret_type, facing, coverage)`** — a scored
  candidate. `facing` is only meaningful for a `SENTINEL` placement
  (`None` for `GUNNER`, whose facing is a live rotation choice made after
  the fact).
- **`best_cluster_placement(candidates, enemies, turret_types=(GUNNER,
  SENTINEL)) -> Placement | None`** — the highest-coverage candidate that
  is safe from every known enemy, or `None` if nothing both qualifies and
  covers at least one. `candidates` is caller-supplied on purpose — see
  [Limitations](#limitations).
- **`safe_heal_tile(turret_position, enemies) -> Position | None`** — the
  first orthogonally-adjacent tile to a friendly turret (heal is
  orthogonal-only, see
  [`docs/official/docs/game-rules-builder-bot.txt`](../../../../docs/official/docs/game-rules-builder-bot.txt))
  that is itself safe from every known enemy, or `None` if all four are
  threatened.

## Data source

Nothing in this file populates `EnemyTurret` — a caller builds these from
its own vision-gated scouting/reporting, the same division of labor
[`econ2`'s `self.map`](../../econ2/README.md#selfmap-assumptions) has with
whatever fills *it* in. In particular:

- **`direction` staleness is asymmetric by design, not an oversight.**
  For a `SENTINEL` (or `LAUNCHER`, which has no facing at all), a cached
  direction is trustworthy forever once observed — it can't change.
  For a `GUNNER`, `threatens()` never even reads `direction` — a Gunner's
  facing can go stale the instant the real one rotates, with no
  notification, so trusting a cached value would be actively wrong rather
  than just imprecise. Keep the field around anyway (e.g. for UI/logging
  or a future feature that *does* want the last-known facing), just don't
  expect `threatens()` to use it for a Gunner.
- **`last_seen_round` is caller-supplied bookkeeping only.** Nothing here
  reads it. Deciding when a sighting is too stale to trust at all (the
  turret may have been destroyed, or moved — it can't move, but it could
  be gone) is a judgment call left to the caller, same as `econ2`
  explicitly not solving its own staleness problem.
- **No team filtering.** This module assumes every `EnemyTurret` handed to
  it actually is one — mixing in a friendly turret would make
  `threatens()`/`is_safe()` report your own turret as a threat to itself.

## Limitations

- **No obstruction modeling, and the bias cuts different ways depending
  on which side of the calculation you're on.** `threatens()` (safety)
  ignores walls/units between an enemy turret and the candidate tile —
  an unconfirmed wall must never be the reason a tile gets called safe,
  the same "`None` means unknown, not confirmed empty" caution
  [`econ2`](../../econ2/README.md#selfmap-assumptions) applies to its own
  map cache. `gunner_coverage()`/`best_sentinel_facing()` (offense) make
  the *same* assumption but it now cuts the *optimistic* way — a real
  shot could be blocked by something this module doesn't know about. Both
  are therefore ranking heuristics, not a final go/no-go: a caller must
  still confirm live with `ct.can_build_*`/`ct.can_fire_from` (which does
  model occupancy and walls — see `docs/official/docs/robot-api.txt`)
  before actually committing titanium.
- **`ct.can_fire_from` isn't used at all, on purpose.**
  `tests/fake_controller.py`'s version explicitly doesn't model a
  Sentinel or Launcher's hypothetical ray (`# Sentinel/Launcher
  hypothetical rays aren't modeled` — only Gunner is implemented), so
  building this module's Sentinel logic on top of it would make half the
  tests untestable without the real engine. Reimplementing the geometry
  directly (`_on_ray`) keeps everything here testable via plain
  `fcode.Position`/`Direction` math — see [Testing](#testing) — at the
  cost of the obstruction gap above. Whether the real engine's
  `can_fire_from` requires the traced-through tiles to be in the caller's
  own vision (and would raise `GameError` per `vision_probe`'s finding if
  not) is untested here; a caller relying on it for the final live check
  should verify that empirically first, the same way `vision_probe`
  settled the equivalent question for plain tile getters.
- **Candidate generation is the caller's job.** `best_cluster_placement`
  only ranks a supplied list; it doesn't scan the map or reason about
  reachability/vision/what a Builder Bot can currently see, the way
  `bots/warden_/modes/defence.py`'s `_guard_position`/`_core_ring_tiles`
  do for its own (simpler, non-adversarial) placement problem. What
  counts as a reasonable search area is bot-specific.
- **`safe_heal_tile` only checks the healer's own tile against turret
  fire, not a Launcher's pickup-and-throw.** `threatens()` correctly
  treats `LAUNCHER` as no threat to a *building's* HP (it can't damage
  one at all — see
  [`docs/official/docs/game-rules-turrets.txt`](../../../../docs/official/docs/game-rules-turrets.txt)),
  but a Launcher within pickup range (adjacent, incl. diagonal) of the
  *healer itself* can still grab and fling it — a different risk this
  function doesn't check.
- **Not wired into a `run()`.** No unit calls any of this on a schedule
  yet, and nothing populates `EnemyTurret`s from `ct` — see
  [Data source](#data-source).
- **No clustering algorithm.** "Cluster" here just means "whatever list
  of `EnemyTurret`s the caller passes in" — there's no grouping-by-
  proximity step. A caller that wants to target one cluster out of many
  scattered enemies filters the list itself before calling
  `best_cluster_placement`.

## Testing

[`tests/test_defensive.py`](../../../../tests/test_defensive.py) is plain
`pytest` against `fcode.Position`/`Direction` — no `Controller` or
`fake_controller.World` needed, since this module never calls `ct`.
Covers: Gunner range-circle safety (including the boundary and that a
cached facing is ignored), Sentinel ray safety with known vs. unknown
facing (including diagonal axes), Launcher never threatening a building,
`gunner_coverage` vs. `best_sentinel_facing`'s single-axis commitment,
`best_cluster_placement` picking the safe highest-coverage candidate (and
returning `None` when nothing qualifies), and `safe_heal_tile` finding —
or failing to find — an untargeted adjacent tile.
