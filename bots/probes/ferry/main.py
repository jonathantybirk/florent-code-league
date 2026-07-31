"""Probe G46 on 2.3.3: does a thrown Builder Bot act on the round it lands?

Entities act in ascending id order, so a bot only gets a post-landing turn in the same round
if the Launcher's id is LOWER than the bot's. Arena `close`:
  builder1 (spawned r0) walks to (5,5) and builds the Launcher at (6,5);
  builder2 (spawned r14, so id > Launcher id) walks to (4,5), then to (5,5);
  the Launcher throws builder2 to (6,9); builder2 notices it teleported and reports its
  cooldowns and whether it can still move that same round.
"""

from fcode import Controller, Direction, EntityType, GameError, Position

HOME1 = Position(5, 5)
LAUNCH = Position(6, 5)
PAD = Position(5, 5)
TARGET = Position(6, 9)


def e(exc):
    return type(exc).__name__ + ":" + str(exc)[:22]


class Player:
    def __init__(self):
        self.n = []
        self.spawnedA = False
        self.spawnedB = False
        self.built = False
        self.first = None
        self.last = None
        self.launched = False
        self.reported = False

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception as exc:
            self.n.append("TOP:" + e(exc))

    def _run(self, ct):
        et = ct.get_entity_type()
        r = ct.get_current_round()
        if et == EntityType.CORE:
            if not self.spawnedA and ct.can_spawn(Position(3, 5)):
                ct.spawn_builder(Position(3, 5))
                self.spawnedA = True
                return
            if r == 14 and not self.spawnedB and ct.can_spawn(Position(3, 6)):
                ct.spawn_builder(Position(3, 6))
                self.spawnedB = True
            return

        if et == EntityType.LAUNCHER:
            if r >= 22 and not self.launched:
                if ct.can_launch(PAD, TARGET):
                    ct.launch(PAD, TARGET)
                    self.launched = True
            return

        if et != EntityType.BUILDER_BOT:
            return

        pos = ct.get_position()
        if self.first is None:
            self.first = r

        # builder1: the one that first ran early. It builds the Launcher then steps aside.
        if self.first <= 2:
            if not self.built:
                if pos != HOME1:
                    d = pos.cardinal_direction_to(HOME1)
                    if ct.can_move(d):
                        ct.move(d)
                    return
                if ct.can_build_launcher(LAUNCH):
                    ct.build_launcher(LAUNCH)
                    self.built = True
                return
            if pos == HOME1 and ct.can_move(Direction.NORTH):
                ct.move(Direction.NORTH)   # vacate the pad for builder2
            return

        # builder2: walk onto the pad and wait to be thrown.
        if self.reported:
            return
        if self.last is not None and pos.distance_squared(self.last) > 2:
            self.reported = True
            moved = "no"
            try:
                if ct.can_move(Direction.SOUTH):
                    ct.move(Direction.SOUTH)
                    moved = "yes->%d,%d" % (ct.get_position().x, ct.get_position().y)
            except Exception as exc:
                moved = e(exc)
            self.n.append("G46 r%d thrown %s->%d,%d mvcd=%d actcd=%d hp=%d/%d moved=%s" % (
                r, self.last, pos.x, pos.y, ct.get_move_cooldown(),
                ct.get_action_cooldown(), ct.get_hp(), ct.get_max_hp(), moved))
            ct.resign(" | ".join(self.n[:4]))
            return
        self.last = (pos.x, pos.y)
        self.last = pos
        if pos != PAD:
            d = pos.cardinal_direction_to(PAD)
            if ct.can_move(d):
                ct.move(d)
                self.last = pos
