"""Pantheon's real decisions for N rounds, then the replica takes the wheel.

Instrument, not a candidate. Divergence compounds: a Builder one tile off on
round 0 changes every landing and every walk after it, so a raw side-by-side
diff cannot separate "we decide differently here" from "we arrived here in a
different state". This bot removes that. It replays Pantheon's own actions --
extracted from a real v20 game against tempest_fast by
tools/pantheon_analysis/make_script.py -- verbatim until HANDOVER_ROUND, so the
board at that round is the board Pantheon actually faced, and only then hands
control to the replica. What it does next is a decision taken from an identical
state, so any difference is a real difference in policy.

The replica's own logic still runs every scripted round, through a Controller
that answers every query truthfully and quietly drops every action. Ragnarok's
Builders carry a great deal of state -- builder index, doctrine, phase, route,
remembered terrain, ore claims, build counters -- almost all of it accumulated
in _sense on rounds the unit was alive. Skipping those rounds would hand over to
a bot that had never looked at the board, and the experiment would be measuring
that instead of its policy.
"""

import builder
import core
import gunner
import launcher
import sentinel
from fcode import Controller, Direction, EntityType, GameError, Position

from handover import HANDOVER_ROUND
from script_data import SCRIPT

HANDLERS = {
    EntityType.CORE: core.run,
    EntityType.BUILDER_BOT: builder.run,
    EntityType.GUNNER: gunner.run,
    EntityType.LAUNCHER: launcher.run,
    EntityType.SENTINEL: sentinel.run,
}

# Everything that changes the board. Reads, predicates and the comms store all
# pass through: the store is team memory rather than a move, and suppressing it
# would leave the replica blind at handover.
_MUTATORS = frozenset((
    "move", "spawn_builder", "build", "build_harvester", "build_conveyor",
    "build_splitter", "build_barrier", "build_gunner", "build_sentinel",
    "build_launcher", "destroy", "fire", "heal", "self_destruct", "rotate",
    "launch", "convert_ammo", "resign",
))

_OFFSETS = {
    (0, -1): Direction.NORTH, (1, -1): Direction.NORTHEAST,
    (1, 0): Direction.EAST, (1, 1): Direction.SOUTHEAST,
    (0, 1): Direction.SOUTH, (-1, 1): Direction.SOUTHWEST,
    (-1, 0): Direction.WEST, (-1, -1): Direction.NORTHWEST,
}
_NAMED = {
    "DIR_NORTH": Direction.NORTH, "DIR_NORTHEAST": Direction.NORTHEAST,
    "DIR_EAST": Direction.EAST, "DIR_SOUTHEAST": Direction.SOUTHEAST,
    "DIR_SOUTH": Direction.SOUTH, "DIR_SOUTHWEST": Direction.SOUTHWEST,
    "DIR_WEST": Direction.WEST, "DIR_NORTHWEST": Direction.NORTHWEST,
    "DIR_CENTRE": Direction.NORTH,
}


def _swallow(*_args, **_kwargs):
    return None


class Shadow:
    """Answers every question, performs nothing."""

    def __init__(self, ct):
        self._ct = ct

    def __getattr__(self, name):
        if name in _MUTATORS:
            return _swallow
        return getattr(self._ct, name)


class Player:
    def __init__(self):
        self.done = set()

    def run(self, ct: Controller) -> None:
        rnd = ct.get_current_round()
        if rnd >= HANDOVER_ROUND:
            self._think(ct)
            return
        # Let the replica look at the board and update itself, then do what
        # Pantheon actually did.
        self._think(Shadow(ct))
        self._scripted(ct, rnd)

    def _think(self, ct):
        handler = HANDLERS.get(ct.get_entity_type())
        if handler is None:
            return
        try:
            handler(self, ct)
        except Exception:
            pass

    def _scripted(self, ct, rnd):
        me = ct.get_id()
        kind = ct.get_entity_type()
        for index, (unit, action) in enumerate(SCRIPT.get(rnd, [])):
            key = (rnd, index)
            if key in self.done:
                continue
            # A launch is recorded against the passenger, not the Launcher, so
            # any Launcher may claim it; there is only ever one in the opening.
            if unit is None:
                if kind != EntityType.LAUNCHER:
                    continue
            elif unit != me:
                continue
            self.done.add(key)
            try:
                self._do(ct, action)
            except GameError:
                pass

    def _do(self, ct, action):
        verb = action[0]
        if verb == "spawn":
            ct.spawn_builder(Position(*action[1]))
        elif verb == "convert":
            if ct.can_convert_ammo(action[1]):
                ct.convert_ammo(action[1])
        elif verb == "move":
            here = ct.get_position()
            step = (action[1][0] - here.x, action[1][1] - here.y)
            direction = _OFFSETS.get(step)
            if direction is not None and ct.can_move(direction):
                ct.move(direction)
        elif verb == "launch":
            ct.launch(Position(*action[1]), Position(*action[2]))
        elif verb == "selfdestruct":
            ct.self_destruct()
        elif verb == "build":
            _, what, where, facing = action
            pos = Position(*where)
            direction = _NAMED.get(facing, Direction.NORTH)
            if what == "launcher":
                ct.build_launcher(pos)
            elif what == "harvester":
                ct.build_harvester(pos)
            elif what == "barrier":
                ct.build_barrier(pos)
            elif what == "gunner":
                ct.build_gunner(pos, direction)
            elif what == "sentinel":
                ct.build_sentinel(pos, direction)
            elif what == "conveyor":
                ct.build_conveyor(pos, direction)
            elif what == "splitter":
                ct.build_splitter(pos, direction)
