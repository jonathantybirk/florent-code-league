"""Per-unit persistent state for warden.

The engine calls Player() with no arguments before it's known which
entity type that instance will control (see main.py), so this one
dataclass -- not just a "BuilderState" despite the name -- is what every
unit type's Player stashes its state in, same as bots/strategist/
state.py's BotState. last_spawn_round is Core-only, for
BUILDER_SPAWN_COOLDOWN_ROUNDS pacing (see core.py) -- everything else the
Core needs is read live each round. For an actual Builder Bot it survives
mode switches, which is the point: promoting/demoting a builder must not
lose its position in whatever it was doing.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from fcode import Direction, Position

from constants import Mode
from toolbox import StuckTracker


@dataclass
class BuilderState:
    # Core only
    last_spawn_round: int = -999999

    ticket: int | None = None
    mode: Mode = Mode.ECONOMY
    promoted: bool = False  # True if this unit's mode was set by the threat trigger, not its ticket

    core_pos: Position | None = None

    # Economy
    ore_target: Position | None = None
    # Consecutive rounds with neither an ore_target nor a route -- i.e.
    # genuinely idle, not mid-walk or mid-route. Reset to 0 whenever
    # either is active; see modes/economy.py's run() and
    # policy.maybe_reassign()'s ECON_IDLE_ROUNDS_BEFORE_SCOUT trigger.
    econ_idle_rounds: int = 0
    # Route-from-harvester walk, set right after building a harvester;
    # all three fields cleared together once connected (or abandoned) --
    # see modes/economy.py's _abandon() and module docstring.
    # route_harvester alone gates whether _lay_route runs at all.
    # route_target is decided once, at route start: the nearest existing
    # Conveyor tile if closer than the Core, else the Core itself.
    # route_pending_pos/_dir track a single build owed one round late: a
    # tile just vacated, waiting to receive a conveyor facing the
    # direction actually just moved -- never a *predicted* direction,
    # since build and move are mutually exclusive within a round (the
    # tile can't be built on the same round it's stepped off of).
    route_harvester: Position | None = None
    route_target: Position | None = None
    route_pending_pos: Position | None = None
    route_pending_dir: Direction | None = None

    # Scouting
    scout_target: Position | None = None
    scout_cycle: int = 0

    stuck: StuckTracker = field(default_factory=StuckTracker)
