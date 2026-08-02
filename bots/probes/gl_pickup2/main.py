"""AREA 1 / probe 2: pin down the LAUNCHER pickup radius exactly.

Probe 1 showed d^2=2 (a DIAGONAL neighbour) is pickable and d^2=5 is not.
Remaining candidates: r^2<=2 (the 8-neighbourhood) vs r^2<=4 vs r^2<=8.
The builder walks a scripted tour visiting d^2 = 1,2,4,5,8,9 from the Launcher
at (11,8); the Launcher reports can_launch() for whatever tile it is on.

Arena `openfield` (24x20). TGT (10,8) is a permanently-empty legal throw target.
"""

from fcode import Controller, Direction, EntityType, GameError, Position

PARK = Position(11, 9)
LAUNCH = Position(11, 8)
TGT = Position(10, 8)

TOUR = [
    (11, 9), (12, 9), (13, 9), (13, 10), (13, 9), (13, 8), (13, 7), (13, 6),
    (12, 6), (11, 6), (10, 6), (9, 6), (9, 7), (9, 8), (9, 9), (10, 9),
    (11, 9), (11, 10), (11, 11), (11, 12), (11, 11),
]


def en(exc):
    return type(exc).__name__ + ":" + str(exc)[:20]


class Player:
    def __init__(self):
        self.spawned = False
        self.built = False
        self.i = 0

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
                return
            if self.i < len(TOUR):
                tx, ty = TOUR[self.i]
                if pos == Position(tx, ty):
                    self.i += 1
                    if self.i >= len(TOUR):
                        return
                    tx, ty = TOUR[self.i]
                d = pos.cardinal_direction_to(Position(tx, ty))
                if ct.can_move(d):
                    ct.move(d)
            return

        if et != EntityType.LAUNCHER:
            return

        found = []
        for dy in range(-4, 5):
            for dx in range(-4, 5):
                q = Position(LAUNCH.x + dx, LAUNCH.y + dy)
                if q.x < 0 or q.y < 0:
                    continue
                try:
                    bid = ct.get_tile_builder_bot_id(q)
                except Exception:
                    continue
                if bid is None:
                    continue
                try:
                    ok = "1" if ct.can_launch(q, TGT) else "0"
                except Exception:
                    ok = "E"
                found.append("%s,%s d2=%d ok=%s" % (q.x, q.y, dx * dx + dy * dy, ok))
        if found:
            print("LP|r%d %s" % (r, " | ".join(found)))
