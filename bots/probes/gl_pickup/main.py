"""AREA 1 / probe 1: what is the LAUNCHER's PICKUP radius?

G48 proved the THROW radius is the disc r^2<=26 measured from the Launcher.
Nobody has ever measured the PICKUP radius -- every prior probe used an
orthogonally adjacent builder (d^2=1), so "adjacent" was an assumption.

Arena `openfield` (24x20, no ore, Core A anchor (1,9), Core B anchor (21,9)).
  B1 spawns at (3,9), walks east to (11,9), builds a LAUNCHER at (11,8),
  then marches east one tile per round along row 9.
  Distances from the Launcher at (11,8) to (x,9):
     x=12 d2=2   13 d2=5   14 d2=10   15 d2=17   16 d2=26   17 d2=37
     18 d2=50   19 d2=65
  The Launcher tests can_launch((x,9), TGT) for x in 12..19 every round.

Exfil: print lines tagged 'LP|' are recovered from the .replay26 by gl_run.py.
"""

from fcode import Controller, Direction, EntityType, GameError, Position

PARK = Position(11, 9)
LAUNCH = Position(11, 8)
TGT = Position(11, 7)


def en(exc):
    return type(exc).__name__ + ":" + str(exc)[:20]


class Player:
    def __init__(self):
        self.spawned = False
        self.built = False
        self.role = None

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception as exc:
            print("LP|TOP %s" % en(exc))

    def _run(self, ct):
        et = ct.get_entity_type()
        r = ct.get_current_round()
        if et == EntityType.CORE:
            if not self.spawned and ct.can_spawn(Position(3, 9)):
                ct.spawn_builder(Position(3, 9))
                self.spawned = True
            return

        if et == EntityType.BUILDER_BOT:
            pos = ct.get_position()
            if not self.built:
                if pos != PARK:
                    d = pos.cardinal_direction_to(PARK)
                    if ct.can_move(d):
                        ct.move(d)
                    return
                if ct.can_build_launcher(LAUNCH):
                    ct.build_launcher(LAUNCH)
                    self.built = True
                    print("LP|r%d built launcher at %s,%s" % (r, LAUNCH.x, LAUNCH.y))
                return
            # march east, one tile per round
            if ct.can_move(Direction.EAST) and pos.x < 19:
                ct.move(Direction.EAST)
            print("LP|r%d BOT at %s,%s" % (r, ct.get_position().x, ct.get_position().y))
            return

        if et != EntityType.LAUNCHER:
            return

        cells = []
        for x in range(12, 20):
            q = Position(x, 9)
            d2 = (x - LAUNCH.x) ** 2 + (9 - LAUNCH.y) ** 2
            try:
                ok = "1" if ct.can_launch(q, TGT) else "0"
            except Exception as exc:
                ok = "E"
            try:
                bid = ct.get_tile_builder_bot_id(q)
                seen = "b" if bid is not None else "-"
            except Exception:
                seen = "?"
            cells.append("%d:d%d:%s%s" % (x, d2, seen, ok))
        print("LP|r%d LAUNCH %s" % (r, " ".join(cells)))
