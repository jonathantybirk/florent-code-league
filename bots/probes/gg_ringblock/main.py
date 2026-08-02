"""Is there any no-build exclusion zone around an ENEMY Core?

CORE_ACTION_RADIUS_SQ = 8 is the one Core constant nobody has explained, and the map format enforces
a one-tile EMPTY margin around every Core, so it is at least plausible that the engine refuses
construction inside an enemy Core's margin.  This asks the question directly, on every kind of
building, on an enemy spawn-ring tile and on an enemy FOOTPRINT tile.

Arena `lab/ringtight` (12x10): Core A anchor (2,4), Core B anchor (8,4).  The builder walks to
(6,4) -- two tiles west of the enemy footprint, orthogonally adjacent to the enemy ring tile (7,4),
whose distance^2 to the enemy footprint tile (8,4) is 1, well inside CORE_ACTION_RADIUS_SQ.

Reported by the BUILDER (M07) through resign (G29/M06).
"""

from fcode import Controller, Direction, EntityType, GameError, Position

STAND = Position(6, 4)
RING = Position(7, 4)
FOOT = Position(8, 4)
SPAWN = Position(4, 4)


class Player:
    def __init__(self):
        self.n = []
        self.spawned = False
        self.done = False

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception as exc:
            self.n.append("TOP:" + type(exc).__name__ + ":" + str(exc)[:16])

    def _run(self, ct):
        et = ct.get_entity_type()
        if et == EntityType.CORE:
            if not self.spawned and ct.can_spawn(SPAWN):
                ct.spawn_builder(SPAWN)
                self.spawned = True
            return
        if et != EntityType.BUILDER_BOT or self.done:
            return
        pos = ct.get_position()
        if pos != STAND:
            d = pos.cardinal_direction_to(STAND)
            if ct.can_move(d):
                ct.move(d)
            return
        self.done = True

        def t(label, fn):
            try:
                self.n.append("%s=%s" % (label, str(fn())[:12]))
            except Exception as exc:
                self.n.append("%s!%s" % (label, str(exc)[:22]))

        t("Rempty", lambda: ct.is_tile_empty(RING))
        t("Rbar", lambda: ct.can_build_barrier(RING))
        t("Rgun", lambda: ct.can_build_gunner(RING, Direction.EAST))
        t("Rlau", lambda: ct.can_build_launcher(RING))
        t("Rhar", lambda: ct.can_build_harvester(RING))
        t("Rcon", lambda: ct.can_build_conveyor(RING, Direction.EAST))
        t("Fempty", lambda: ct.is_tile_empty(FOOT))
        t("Fbar", lambda: ct.can_build_barrier(FOOT))
        t("BUILD", lambda: ct.build_barrier(RING))
        t("Rid", lambda: ct.get_tile_building_id(RING))
        ct.resign(("GGRB|" + " ".join(self.n))[:495])
