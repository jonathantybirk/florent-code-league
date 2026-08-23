# Anti-harassment: block, don't fight

`main.py` answers two questions about an enemy Builder Bot caught working
over friendly infrastructure: **is one currently there**, and **which of
its own escape tiles should an allied Builder Bot occupy** to deny it a
move and keep it in a covering turret's line of fire longer?

## Why blocking, not fighting

[`bots/test/builder_combat_probe`](../../builder_combat_probe/main.py)
empirically settled a question the docs leave ambiguous: can a Builder
Bot's Attack ever damage another Builder Bot? Run against the real engine
four times (different maps/seeds), the answer was consistently no, in
either of the two ways it might have worked:

- **Directly**, against a Builder Bot standing on bare ground —
  `can_fire()` was `False` every round. Matches
  [`game-rules-builder-bot.txt`](../../../../docs/official/docs/game-rules-builder-bot.txt)'s
  own wording: Attack targets "the building," not the unit.
- **As collateral**, against a Builder Bot standing on a building being
  attacked — `fire()` succeeded and (presumably) damaged the building
  every round, but the co-located Builder Bot's HP never moved. Unlike
  `heal()`, which is explicitly documented as hitting both the building
  and a Builder Bot standing on it in the same call, Attack does not
  share that behavior.

So an allied Builder Bot can never speed up a kill by dealing damage
itself — only a covering Gunner or Sentinel can actually kill a harasser.
What an allied Builder Bot *can* still do is occupy a tile: per the same
doc, "Tiles occupied by another Builder Bot" are impassable. Parking one
on a harasser's escape route removes that move option outright, which
matters because a Builder Bot that "behaves optimally" is genuinely hard
to pin down otherwise — a Gunner's only way to follow a target that
stepped off its ray is `rotate()`, which costs 10 Ti *and* a round that
isn't spent firing, and a Sentinel can't rotate at all. Blocking doesn't
deal damage; it takes options away from the harasser so the turret's
existing damage actually lands.

## API

- **`FriendlyInfra(position, etype)`** — one tile this team expects to
  have a Conveyor, Splitter, or Harvester on. Nothing here populates this
  — a caller supplies it from its own build history, same division of
  labor as [`econ2`'s `harvester_positions`](../../econ2/README.md) or
  [`defensive`'s `EnemyTurret`](../defensive/README.md).
- **`find_active_harassers(ct, infra) -> dict[int, Position]`** — enemy
  Builder Bot ids currently standing on, or orthogonally adjacent to, a
  tile in `infra`, mapped to their position. Only ever looks at tiles
  currently in this unit's own vision.
- **`escape_tiles(ct, harasser_pos, friendly_turret_ids) -> list[Position]`**
  — of `harasser_pos`'s (in-bounds, Builder-Bot-passable) cardinal
  neighbours, the ones NOT currently threatened by any of
  `friendly_turret_ids`. An empty list means the harasser is already
  boxed in — nothing to block.
- **`best_blocking_tile(escape, blocker_pos) -> Position | None`** — the
  escape tile closest to `blocker_pos`, or `None` if `escape` is empty.

## How escape_tiles reuses `defensive`

Rather than re-deriving turret-range geometry a third time, `escape_tiles`
loads [`bots/test/strategies/defensive/main.py`](../defensive/main.py) by
direct file path (`_load_defensive`, the same cross-`bots/test/` trick
[`splitter_probe`](../../splitter_probe/main.py) uses to reuse
[`econ`](../../econ/README.md) — the engine's flat per-directory
`sys.path` rules out a plain package-relative import here) and calls its
`is_safe`/`EnemyTurret` directly. The reuse works because the geometry is
symmetric: a turret's threat envelope is the same shape whether it's
"theirs" (can I safely stand here?) or "ours" (can the harasser safely
stand here?) — only the label is enemy-flavored. `_read_turret` builds an
`EnemyTurret` describing a *friendly* turret, reading its position/type/
facing live via `ct` each call rather than caching them, for the same
reason `defensive.threatens()` never trusts a cached Gunner facing: it can
rotate at any time.

One consequence worth calling out explicitly: `defensive.threatens()`'s
Gunner check ignores facing entirely and just tests range, since a Gunner
can rotate to face anything within reach. That's the right conservative
assumption when the question is "could this position ever come under
fire" (`defensive`'s own placement-safety use case) — and it's *also* the
right call here, if less obviously: a friendly Gunner that isn't currently
facing the harasser's escape tile could rotate onto it next round, so
counting the tile as "covered" now is a reasonable bet on how the turret
will actually be used, not just a leftover assumption from a different
problem.

## Limitations

- **Single blocker only.** `best_blocking_tile` picks one tile for one
  Builder Bot. If `escape_tiles` returns more than one open route, only
  the nearest gets blocked — the harasser can still take another. No
  multi-blocker coordination exists here.
- **No lag modeling.** Both functions assume the picked block tile stays
  open until the blocker arrives, but the harasser moves too — if it
  reaches that tile first, or a different escape opens up on the same
  round the blocker commits to one, this doesn't notice or replan. A
  caller re-running `escape_tiles`/`best_blocking_tile` every round (cheap
  — no state carried between calls) is the mitigation, not anything
  inside these functions.
- **Unreadable turrets are dropped, not treated as unknown-and-dangerous.**
  A turret id that's out of vision, or was destroyed since last checked,
  silently doesn't count toward coverage in `escape_tiles` — biasing
  toward reporting *more* escape tiles (and therefore an unnecessary
  block) rather than fewer (a harasser walking straight through a tile
  this module wrongly thought was covered). Wasting a block is the safer
  failure mode of the two, but it is a real one: if all your covering
  turrets are temporarily out of your builder's vision, `escape_tiles`
  quietly reports the harasser as having no coverage at all.
- **Detection only tells you "adjacent to infra," not "attacking it right
  now."** `find_active_harassers` doesn't check whether the enemy Builder
  Bot has actually fired this round, spent its action cooldown, or is
  just passing through. A caller that wants to distinguish a genuine
  attack from an enemy builder momentarily walking past should read
  `ct.get_action_cooldown`/`ct.get_hp` on the infra tile itself across
  rounds — not something this module tracks.
- **No repair/rebuild step.** This module is scoped to the "catch it in
  the act and pin it down" half of the problem. What happens after
  (clearing a Barrier the harasser placed — Attack does work cross-team
  on buildings, ~15 hits for a 30-HP Barrier — and rebuilding the lost
  Conveyor/Harvester) isn't implemented here.
- **Doesn't build or move anything.** Same division of labor as
  `defensive`/`econ2`: this returns positions and ids for a caller's own
  `run()` to act on (`ct.move`, `ct.can_build_*`, ...) with its own
  legality gates.

## Testing

[`tests/test_anti_harassment.py`](../../../../tests/test_anti_harassment.py)
uses `tests/fake_controller.World` (this module makes live `ct` calls,
unlike `defensive`'s pure-Python tests) — harasser detection (adjacent,
standing on the infra tile itself, team-filtered, vision-gated), escape-
tile computation (open with no coverage, one side removed by a covering
Gunner, a wall or another Builder Bot excluded regardless of turret
coverage, an unreadable turret id skipped without crashing, every side
covered by four Sentinels), and nearest-tile blocker selection.
