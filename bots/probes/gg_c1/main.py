"""AREA 3a: what is CORE_ACTION_RADIUS_SQ = 8 for?

Enumerate, from the CORE, every capability query over an 8x8 offset block around the
core anchor, plus every Controller method that is not obviously core-legal.

Arena `corelab` (26x22): Core A anchor (6,9), footprint (6,9)(7,9)(6,10)(7,10).
Ore at (4,7) and (9,12).

Offsets scanned: dx in -3..4, dy in -3..4 relative to the anchor.
Distance^2 to the NEAREST footprint tile is printed alongside so the radius that each
capability actually respects can be read straight off the bitmap.
"""

from fcode import Controller, Direction, EntityType, GameError, Position

E = Direction.EAST
FOOT = [(0, 0), (1, 0), (0, 1), (1, 1)]


def e(exc):
    return type(exc).__name__[:4] + ":" + str(exc)[:22]


class Player:
    def __init__(self):
        self.done = False

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception as exc:
            print("GGPROBE|TOP " + e(exc))

    def _run(self, ct):
        if ct.get_entity_type() != EntityType.CORE or self.done:
            return
        if ct.get_current_round() != 2:
            return
        self.done = True
        a = ct.get_position()
        print("GGPROBE|ANCHOR %d,%d round=%d" % (a.x, a.y, ct.get_current_round()))

        tests = [
            ("spawn", lambda p: ct.can_spawn(p)),
            ("barr", lambda p: ct.can_build_barrier(p)),
            ("conv", lambda p: ct.can_build_conveyor(p, E)),
            ("gunn", lambda p: ct.can_build_gunner(p, E)),
            ("harv", lambda p: ct.can_build_harvester(p)),
            ("heal", lambda p: ct.can_heal(p)),
            ("dstr", lambda p: ct.can_destroy(p)),
            ("fire", lambda p: ct.can_fire(p)),
            ("visi", lambda p: ct.is_in_vision(p)),
        ]

        # distance^2 map for reference
        for dy in range(-3, 5):
            row = []
            for dx in range(-3, 5):
                best = 99
                for (fx, fy) in FOOT:
                    d = (dx - fx) ** 2 + (dy - fy) ** 2
                    if d < best:
                        best = d
                row.append("%2d" % min(best, 99))
            print("GGPROBE|D2 dy=%d %s" % (dy, ",".join(row)))

        for (name, fn) in tests:
            rows = []
            errs = {}
            for dy in range(-3, 5):
                r = ""
                for dx in range(-3, 5):
                    p = Position(a.x + dx, a.y + dy)
                    try:
                        r += "1" if fn(p) else "0"
                    except Exception as exc:
                        r += "!"
                        errs[e(exc)] = 1
                rows.append(r)
            print("GGPROBE|%s %s ERR=%s" % (name, ",".join(rows), ";".join(errs)[:60]))

        # method-availability sweep from the Core
        out = []

        def t(label, fn):
            try:
                out.append("%s=%s" % (label, str(fn())[:26]))
            except Exception as exc:
                out.append("%s!%s" % (label, e(exc)))

        t("etype", lambda: ct.get_entity_type())
        t("dir", lambda: ct.get_direction())
        t("actcd", lambda: ct.get_action_cooldown())
        t("movecd", lambda: ct.get_move_cooldown())
        t("canact", lambda: ct.can_act())
        t("vision", lambda: ct.get_vision_radius_sq())
        t("attk", lambda: len(ct.get_attackable_tiles()))
        t("gtgt", lambda: ct.get_gunner_target())
        t("canmove", lambda: ct.can_move(E))
        t("move", lambda: ct.move(E))
        t("canrot", lambda: ct.can_rotate(Direction.NORTH))
        t("rot", lambda: ct.rotate(Direction.NORTH))
        t("stored", lambda: ct.get_stored_resource())
        t("nearu", lambda: len(ct.get_nearby_units()))
        t("nearb", lambda: len(ct.get_nearby_buildings()))
        t("neart8", lambda: len(ct.get_nearby_tiles(8)))
        t("neart36", lambda: len(ct.get_nearby_tiles(36)))
        t("neart64", lambda: len(ct.get_nearby_tiles(64)))
        print("GGPROBE|M1 " + " | ".join(out))
        out = []
        t("attkfrom", lambda: len(ct.get_attackable_tiles_from(
            Position(a.x, a.y), E, EntityType.SENTINEL)))
        t("canfirefrom", lambda: ct.can_fire_from(
            Position(a.x + 4, a.y), E, EntityType.GUNNER, Position(a.x + 5, a.y)))
        t("canlaunch", lambda: ct.can_launch(Position(a.x, a.y - 1), Position(a.x, a.y - 3)))
        t("selfdes", lambda: ct.self_destruct())
        print("GGPROBE|M2 " + " | ".join(out))
        ct.resign("GGP|c1 done")
