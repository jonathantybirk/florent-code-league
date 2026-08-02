"""Does a Harvester split its output round-robin between EVERY adjacent sink?

Arena `cd1` (ore at (4,5), orthogonally adjacent to Core A footprint tile (3,5)).
`gg_hdist` on cd1 already measured 2500 collected with the Core as the only neighbour.

Here the same harvester also gets a DEAD-END conveyor neighbour at (5,5) facing EAST
into open ground. If the round-robin counts the Core as just another sink, collected
should fall to roughly half. If the harvester prefers the Core, it stays at 2500.

This is the mechanism behind a 3-titanium "parasite conveyor" economic attack, so it
matters whether the round-robin is team-blind. This probe only settles the same-team
half; the team-blind half needs an opponent.
"""

from fcode import Controller, Direction, EntityType, GameError, Position

E = Direction.EAST
CARD = (Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST)
ORE = Position(4, 5)
LEAK = Position(5, 5)


class Player:
    def __init__(self):
        self.spawned = False
        self.phase = 0

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception as exc:
            print("GGPROBE|EXC %s %s" % (type(exc).__name__, str(exc)[:40]))

    def step(self, ct, pos, tgt):
        best = None
        for d in CARD:
            if not ct.can_move(d):
                continue
            s = pos.add(d).distance_squared(tgt)
            if best is None or s < best[0]:
                best = (s, d)
        if best is not None and best[0] < pos.distance_squared(tgt):
            ct.move(best[1])

    def _run(self, ct):
        et = ct.get_entity_type()
        r = ct.get_current_round()
        if et == EntityType.CORE:
            if not self.spawned and ct.can_spawn(Position(3, 4)):
                ct.spawn_builder(Position(3, 4))
                self.spawned = True
            return
        if et != EntityType.BUILDER_BOT:
            return
        pos = ct.get_position()

        if self.phase == 0:
            if pos != Position(4, 4):
                self.step(ct, pos, Position(4, 4))
                return
            if ct.can_build_harvester(ORE):
                ct.build_harvester(ORE)
                print("GGPROBE|HARV r=%d" % r)
                self.phase = 1
            return
        if self.phase == 1:
            if pos != Position(5, 4):
                self.step(ct, pos, Position(5, 4))
                return
            if ct.can_build_conveyor(LEAK, E):
                ct.build_conveyor(LEAK, E)
                print("GGPROBE|LEAK r=%d" % r)
                self.phase = 2
            return
        if self.phase == 2:
            if pos != Position(6, 3):
                self.step(ct, pos, Position(6, 3))
            return
