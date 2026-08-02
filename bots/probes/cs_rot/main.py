"""Q8 -- is GUNNER ROTATION scale-exempt?

GUNNER_ROTATE_COST = 10, the same number as GUNNER_BASE_COST.  If the 10 is charged flat while a
new gunner costs floor(scale/100 * 10), then at high scale re-aiming an existing gunner is
strictly cheaper than building a fresh one, and it also adds no scale of its own.

Arena `lab/csopen`.  The Core spawns FIVE Builder Bots (+20pp each) so the team scale is already
~200% before anything rotates; builder #0 walks to (5,6) and builds one gunner at (5,5).  The
GUNNER is the reporting unit: it reads scale / titanium / get_gunner_cost() immediately before and
after each rotate(), so a scaled charge (>=20 at scale 200+) is impossible to confuse with a flat
10, and any scale increment from rotating shows up directly.
"""

from fcode import Controller, Direction, EntityType, GameError, Position

HOME = Position(5, 6)
GUN = Position(5, 5)
RING = (Position(3, 6), Position(3, 5), Position(3, 7), Position(3, 8), Position(0, 6))


def e(exc):
    return type(exc).__name__[:4] + ":" + str(exc)[:20]


class Player:
    def __init__(self):
        self.n = []
        self.role = None
        self.built = False
        self.done = False

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception as exc:
            self.n.append("!" + e(exc))

    def _run(self, ct):
        et = ct.get_entity_type()
        r = ct.get_current_round()

        if et == EntityType.CORE:
            if r < len(RING) and ct.can_spawn(RING[r]):
                ct.spawn_builder(RING[r])
            return

        if et == EntityType.BUILDER_BOT:
            if self.role is None:
                self.role = "b0" if r <= 1 else "sit"
            if self.role != "b0" or self.built:
                return
            pos = ct.get_position()
            if pos.x != HOME.x or pos.y != HOME.y:
                d = pos.cardinal_direction_to(HOME)
                if ct.can_move(d):
                    ct.move(d)
                return
            if r >= 6 and ct.can_build_gunner(GUN, Direction.NORTH):
                ct.build_gunner(GUN, Direction.NORTH)
                self.built = True
            return

        if et != EntityType.GUNNER or self.done:
            return

        def snap(tag):
            self.n.append("%s s=%.0f ti=%d gc=%d" % (
                tag, ct.get_scale_percent(), ct.get_global_resources(),
                ct.get_gunner_cost()))

        if len(self.n) == 0:
            snap("pre")
            self.n.append("canrot=%s" % ct.can_rotate(Direction.EAST))
            ti0 = ct.get_global_resources()
            try:
                ct.rotate(Direction.EAST)
                self.n.append("ROT1 dti=%d s=%.0f cd=%d" % (
                    ct.get_global_resources() - ti0, ct.get_scale_percent(),
                    ct.get_action_cooldown()))
            except Exception as exc:
                self.n.append("ROT1!" + e(exc))
            return

        if len(self.n) == 3:
            self.n.append("cd=%d canrot=%s" % (
                ct.get_action_cooldown(), ct.can_rotate(Direction.SOUTH)))
            return

        if len(self.n) == 4:
            ti0 = ct.get_global_resources()
            try:
                ct.rotate(Direction.SOUTH)
                self.n.append("ROT2 dti=%d s=%.0f" % (
                    ct.get_global_resources() - ti0, ct.get_scale_percent()))
            except Exception as exc:
                self.n.append("ROT2!" + e(exc))
            return

        if len(self.n) == 5:
            self.n.append("samedir=%s" % ct.can_rotate(Direction.SOUTH))
            snap("post")
            self.done = True
            ct.resign(("CSROT " + " | ".join(self.n))[:495])
