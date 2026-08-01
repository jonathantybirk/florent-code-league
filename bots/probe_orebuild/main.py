"""Probe: is an ORE tile a legal site for a Gunner / Barrier?

sprint, Team A. Core (1,1); ore at (4,4). The builder spawns on ring tile (3,3), steps SOUTH to
(3,4), and from there interrogates (4,4) -- which is ORE and orthogonally adjacent.
"""

from fcode import Controller, Direction, EntityType, Position

ORE = (4, 4)
PLAIN = (3, 5)
SPAWN = (3, 3)


class Player:
    def __init__(self):
        self.n = 0
        self.log = []
        self.spawned = False
        self.step = 0
        self.done = False

    def run(self, ct: Controller) -> None:
        try:
            et = ct.get_entity_type()
        except Exception:
            return
        if et == EntityType.CORE:
            self.n += 1
            if not self.spawned:
                try:
                    ct.spawn_builder(Position(*SPAWN))
                    self.spawned = True
                except Exception:
                    pass
            return
        if et != EntityType.BUILDER_BOT or self.done:
            return
        if self.step == 0:
            try:
                ct.move(Direction.SOUTH)          # (3,3) -> (3,4)
                self.step = 1
            except Exception:
                pass
            return
        self.done = True
        for label, tile in (("ore", ORE), ("plain", PLAIN)):
            for what in ("gunner", "barrier", "harvester", "conveyor"):
                try:
                    p = Position(*tile)
                    if what == "gunner":
                        r = ct.can_build_gunner(p, Direction.EAST)
                    elif what == "barrier":
                        r = ct.can_build_barrier(p)
                    elif what == "harvester":
                        r = ct.can_build_harvester(p)
                    else:
                        r = ct.can_build_conveyor(p, Direction.EAST)
                except Exception as e:
                    r = "ERR:%s" % type(e).__name__
                self.log.append("%s(%d,%d) %s=%s" % (label, tile[0], tile[1], what, r))
        try:
            env_ore = ct.get_tile_env(Position(*ORE))
            env_plain = ct.get_tile_env(Position(*PLAIN))
            self.log.append("env ore=%s plain=%s" % (env_ore, env_plain))
        except Exception:
            pass
        try:
            ct.resign("|".join(self.log))
        except Exception:
            ct.resign()
