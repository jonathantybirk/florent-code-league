# Core meta-commands

`main.py` is scaffolding, not a strategy: a small, generic **trigger →
priority → one broadcast value** engine meant to be imported into a real
bot, not run as-is (there's no `run()` method, and `MetaCommand`'s five
members are a starter vocabulary, not a recommendation).

The idea it implements: the Core is the one unit alive from round 0 with
the widest vision of any unit (radius² 36) and a Communication Store full
of whatever teammates have already reported. No other unit has that whole
picture — a lone Builder Bot or turret only ever sees its own patch of map.
So instead of every unit trying to independently infer "are we under
attack, should we be expanding, should everyone regroup" from its own
narrow view, the Core distills its wider picture into **one directive
value** and broadcasts it to [GCS](../../../docs/official/docs/global-comms.txt)
slot 0 — the "first slot" every other unit can cheaply check at the top of
its own `run()`.

## API

- **`MetaCommand`** — an `IntEnum`: `HOLD`, `DEFEND`, `RALLY`, `EXPAND`,
  `RETREAT`, `ATTACK`. Replace or extend this with a bot-specific enum;
  nothing else in this file interprets the values, it only needs them to
  fit the GCS's own constraint (a small non-negative int).
- **`Trigger(command, priority, condition)`** — one rule. `condition` is
  `Callable[[Controller], bool]`; a `Trigger` is a candidate for this
  round's broadcast whenever its `condition(ct)` is true.
- **`evaluate_meta_command(ct, triggers, default=HOLD)`** — the
  highest-priority `Trigger` whose condition currently holds, or `default`
  if none do. Read-only: doesn't touch the store, so it's safe to call for
  a preview (logging, a `resign()` message) without committing a write.
- **`broadcast_meta_command(ct, triggers, default=HOLD, slot=0)`** —
  Core-only. Runs `evaluate_meta_command`, writes the result to `slot`,
  and returns it. Raises `ValueError` if called from any other unit — same
  guard convention as [`bots/test/econ`](../econ/README.md)'s
  `expected_titanium_schedule`, so a mistaken call fails loudly instead of
  silently doing nothing useful.
- **`read_meta_command(ct, slot=0, default=HOLD)`** — any unit. The last
  committed value at `slot`, or `default` if the raw int isn't a known
  `MetaCommand` member (covers an unwritten slot, a custom vocabulary
  where `0` isn't the first member, and a stale value from a
  differently-versioned Core).

## Usage

Core, once per round:

```python
from meta_commands import MetaCommand, Trigger, broadcast_meta_command
from toolbox import find_nearest_enemy  # or your own sensing helpers

TRIGGERS = [
    # Highest priority: something is already standing next to the Core.
    Trigger(
        command=MetaCommand.DEFEND,
        priority=2,
        condition=lambda ct: find_nearest_enemy(ct, radius_sq=49) is not None,
    ),
    # Lower priority: no immediate threat, but we know where their Core is.
    Trigger(
        command=MetaCommand.ATTACK,
        priority=1,
        condition=lambda ct: ct.read_store(SLOT_ENEMY_CORE) != 0,
    ),
]

if ct.get_entity_type() == EntityType.CORE:
    broadcast_meta_command(ct, TRIGGERS)
```

Every other unit, at the top of `run()`:

```python
from meta_commands import MetaCommand, read_meta_command

command = read_meta_command(ct)
if command == MetaCommand.DEFEND:
    fall_back_to_core(ct)
elif command == MetaCommand.ATTACK:
    push_toward_enemy_core(ct)
else:
    do_the_default_thing(ct)
```

## Timing: the same one-round delay as the rest of the GCS

`broadcast_meta_command`'s write is buffered like every `write_store` call
— see [`global-comms.txt`](../../../docs/official/docs/global-comms.txt).
A command the Core decides on round `N` is only visible to
`read_meta_command` starting round `N+1`. Write triggers with that lag in
mind: a `DEFEND` condition that clears the instant the threat leaves
vision will still have every teammate seeing `DEFEND` for one more round
after it's gone, since the Core's *next* round's evaluation is what
finally overwrites it. If a command needs to persist past the round its
triggering condition stopped being true (e.g. "keep defending for a few
rounds after the last sighting" the way
[`bots/warden_/core.py`](../../warden_/core.py)'s threat-level decay
does), that's state a caller tracks itself — e.g. a small counter passed
into a closure captured by the `Trigger`'s `condition` — this module
deliberately doesn't do it for you, since how long to hold and what
decays is a strategy choice, not a property of the broadcast mechanism.

## Priority, not the reverse

Ties resolve by list order, not by anything about the command values
themselves — `MetaCommand.ATTACK == 5` doesn't mean it "outranks"
`MetaCommand.HOLD == 0`; only a `Trigger`'s explicit `priority` field does.
Keep the enum ordering and the priority numbers conceptually separate:
it's fine (and expected) for a low-value command like `DEFEND == 1` to
carry a *higher* priority than `ATTACK == 5` when defense should win a
simultaneous match.

## Extending

- **A different vocabulary**: define your own `IntEnum` (values must still
  be small non-negative ints) and pass its members as `Trigger.command`
  and as `default`/pass `default=` through to `evaluate_meta_command`/
  `broadcast_meta_command`/`read_meta_command`. Nothing here is hardcoded
  to `MetaCommand`'s five members.
- **A different slot**: pass `slot=` to `broadcast_meta_command` and
  `read_meta_command` if slot 0 already means something else in a bot's
  existing GCS layout (see e.g.
  [`bots/warden_/constants.py`](../../warden_/constants.py) for a real
  bot with a full 8-slot layout already in place).
- **Sticky / decaying commands**: see [Timing](#timing-the-same-one-round-delay-as-the-rest-of-the-gcs)
  above — build it into a `Trigger`'s `condition` closure, this module
  stays a stateless evaluator.

## Limitations

- **Not wired into a real Core.** There's no `run()` here and no shipped
  `TRIGGERS` list — every example above is illustrative, not a policy this
  file applies on its own.
- **One value per broadcast.** If a strategy genuinely needs more than one
  simultaneous directive (e.g. "defend" *and* "which side"), that's
  either a richer `MetaCommand` (a combined value) or a second slot with
  its own `broadcast_meta_command` call — this module doesn't bundle
  multiple values into one write.
- **No priority-tie resolution beyond list order.** Two `Trigger`s with
  the same `priority` that both match resolve to whichever was listed
  first, silently. Fine for a short, hand-written trigger list; would
  need an explicit rule if triggers were ever generated programmatically.

## Testing

[`tests/test_meta_commands.py`](../../../tests/test_meta_commands.py)
exercises this through the repo's `fake_controller.World`/`botimport`
harness: priority ordering (including a lower-priority trigger listed
first losing to a higher-priority one listed later), the default when no
trigger matches, the Core-only guard on `broadcast_meta_command`,
`evaluate_meta_command` not touching the store, the one-round write delay
via `world.advance_round()`, and `read_meta_command`'s fallback to
`default` on an out-of-vocabulary raw value.
