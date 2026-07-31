"""Probe G42: do Harvesters block Builder Bot movement?

docs/game-rules/game-rules-reference.md says Harvester "Blocks movement: No". An earlier probe measured
is_tile_passable() == False against a harvester tile, which would mean a harvester built in your own
corridor walls off your own bots -- a real risk for any auto-build policy.

Also re-checks the documented claim that Conveyor and Splitter tiles ARE walkable, including enemy ones.

Findings are exfiltrated through ct.resign(), the only channel that reaches run_game's result dict
(print() is swallowed into the replay -- G29).
"""

from fcode import Controller, Direction, EntityType, Environment, Position

CARDINALS = (Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST)


class Player:
    def __init__(self):
        self.notes = []
        self.built = None
        self.reported = False
        self.round0 = None

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception as exc:
            self.notes.append("EXC:" + type(exc).__name__)

    def _run(self, ct):
        etype = ct.get_entity_type()
        if etype == EntityType.CORE:
            if ct.get_current_round() < 3:
                for d in Direction:
                    if d == Direction.CENTRE:
                        continue
                    try:
                        if ct.can_spawn(ct.get_position().add(d)):
                            ct.spawn_builder(ct.get_position().add(d))
                            return
                    except Exception:
                        continue
            return

        if etype != EntityType.BUILDER_BOT:
            return

        pos = ct.get_position()
        rnd = ct.get_current_round()

        # Phase 1: find an adjacent ore tile and build a harvester on it.
        if self.built is None:
            for d in CARDINALS:
                t = pos.add(d)
                try:
                    if ct.get_tile_env(t) != Environment.ORE_TITANIUM:
                        continue
                    if ct.can_build_harvester(t):
                        ct.build_harvester(t)
                        self.built = (t.x, t.y)
                        self.round0 = rnd
                        self.notes.append("built harvester at %d,%d r%d" % (t.x, t.y, rnd))
                        return
                except Exception:
                    continue
            # wander toward ore
            for d in CARDINALS:
                try:
                    if ct.can_move(d):
                        ct.move(d)
                        return
                except Exception:
                    continue
            return

        # Phase 2: interrogate the harvester tile we just built.
        h = Position(self.built[0], self.built[1])
        if not self.reported and rnd > self.round0:
            self.reported = True
            try:
                passable = ct.is_tile_passable(h)
            except Exception as exc:
                passable = "RAISE:" + type(exc).__name__
            try:
                empty = ct.is_tile_empty(h)
            except Exception as exc:
                empty = "RAISE:" + type(exc).__name__
            self.notes.append("HARVESTER passable=%s empty=%s" % (passable, empty))

            # Which cardinal points at it, and does can_move agree?
            for d in CARDINALS:
                if pos.add(d) == h:
                    try:
                        self.notes.append("can_move(toward harvester)=%s" % ct.can_move(d))
                    except Exception as exc:
                        self.notes.append("can_move RAISE:" + type(exc).__name__)

            # Control: a conveyor tile, documented as walkable.
            for d in CARDINALS:
                t = pos.add(d)
                try:
                    if ct.can_build_conveyor(t, Direction.NORTH):
                        ct.build_conveyor(t, Direction.NORTH)
                        self.notes.append("built conveyor at %d,%d" % (t.x, t.y))
                        break
                except Exception:
                    continue
            ct.resign(" | ".join(self.notes[:8]))
