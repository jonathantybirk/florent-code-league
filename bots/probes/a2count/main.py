"""AREA-2 (d): complete the MAX_TEAM_UNITS accounting.

`denyapi` established: Core 1, Builder Bot 1, Gunner 1, Launcher 1; barrier 0, conveyor 0.
Missing: HARVESTER and SPLITTER -- and whether a Sentinel counts.

Arena `scal` (24x20, Core A anchor (1,9), ore at (6,8) and (6,10)).
Builder spawns (3,9) and walks to (5,9); its orthogonal neighbours are (4,9) (6,9) (5,8) (5,10).
It moves to (6,9) so the two ore tiles are orthogonally adjacent.
"""

from fcode import Controller, Direction, EntityType, GameError, Position


def e(exc):
    return type(exc).__name__[:4] + ":" + str(exc)[:20]


class Player:
    def __init__(self):
        self.n = []
        self.spawned = False
        self.phase = 0

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception as exc:
            self.n.append("TOP:" + e(exc))

    def _run(self, ct):
        et = ct.get_entity_type()
        if et == EntityType.CORE:
            if not self.spawned and ct.can_spawn(Position(3, 9)):
                ct.spawn_builder(Position(3, 9))
                self.spawned = True
            return
        if et != EntityType.BUILDER_BOT:
            return

        pos = ct.get_position()
        if pos.x < 6:
            if ct.can_move(Direction.EAST):
                ct.move(Direction.EAST)
            return

        def note(tag):
            self.n.append("%s u%d s%.0f" % (tag, ct.get_unit_count(), ct.get_scale_percent()))

        if self.phase == 0:
            note("base")
            ct.build_harvester(Position(6, 8))
            note("harv")
            self.phase = 1
            return
        if self.phase == 1:
            ct.build_splitter(Position(5, 9), Direction.WEST)
            note("splt")
            self.phase = 2
            return
        if self.phase == 2:
            ct.build_sentinel(Position(7, 9), Direction.EAST)
            note("sent")
            self.phase = 3
            return
        if self.phase == 3:
            ct.destroy(Position(6, 8))
            note("-harv")
            ct.destroy(Position(5, 9))
            note("-splt")
            self.phase = 4
            return
        if self.phase == 4:
            ct.destroy(Position(7, 9))
            note("-sent")
            self.n.append("cd=%s" % ct.get_action_cooldown())
            ct.resign("|".join(self.n)[:495])
            self.phase = 5
