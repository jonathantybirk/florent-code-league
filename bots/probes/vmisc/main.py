"""VERIFICATION probe: the predicate traps, re-derived independently.

Covers, on a stock map: is_tile_passable(own tile), CENTRE, diagonals (does the predicate
disagree with can_move there?), the vision gate on is_tile_passable, in-vision-but-
out-of-bounds tiles, and whether can_move conflates "impassable" with "still on move
cooldown". Ends by resigning a 1200-character landmarked string so the truncation length
of resign_message can be measured exactly.

    rm -rf bots/probes/vmisc/__pycache__
    .venv/Scripts/python.exe tools/runprobe.py vmisc --map duel --vs idle
"""

import os

from fcode import Controller, Direction, EntityType, Environment, Position

OUT = os.environ.get("VMISC_OUT") or (
    "C:/Users/edlun/AppData/Local/Temp/claude/"
    "c--Users-edlun-Desktop-lucky-shots-Hackathons-florent-code-league/"
    "69495691-95ef-4878-adf9-aeca64f3e3b5/scratchpad/vmisc.txt"
)

CARD = (Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST)
DIAG = (Direction.NORTHEAST, Direction.SOUTHEAST, Direction.SOUTHWEST, Direction.NORTHWEST)


def delta(d):
    o = Position(50, 50)
    p = o.add(d)
    return p.x - o.x, p.y - o.y


class Player:
    def __init__(self):
        self.spawned = False
        self.gen = None
        self.ct = None
        self.dead = False
        self.log = []

    def run(self, ct: Controller) -> None:
        self.ct = ct
        try:
            et = ct.get_entity_type()
        except Exception:
            return
        if et == EntityType.CORE:
            if not self.spawned:
                here = ct.get_position()
                for dx in range(-2, 4):
                    for dy in range(-2, 4):
                        p = Position(here.x + dx, here.y + dy)
                        try:
                            if ct.can_spawn(p):
                                ct.spawn_builder(p)
                                self.spawned = True
                                return
                        except Exception:
                            pass
            return
        if et != EntityType.BUILDER_BOT or self.dead:
            return
        if self.gen is None:
            self.gen = self._script()
        try:
            next(self.gen)
        except StopIteration:
            self.dead = True
        except Exception as exc:
            self._note("FATAL %s: %s" % (type(exc).__name__, str(exc)[:200]))
            self.dead = True

    def _note(self, line):
        self.log.append(line)
        try:
            with open(OUT, "w", encoding="utf-8") as fh:
                fh.write("\n".join(self.log) + "\n")
        except Exception:
            pass

    def _try(self, fn, *args):
        try:
            v = fn(*args)
            if v is None:
                return "None"
            if isinstance(v, bool):
                return "True" if v else "False"
            if isinstance(v, Position):
                return "(%d,%d)" % (v.x, v.y)
            return str(getattr(v, "name", v))
        except Exception as exc:
            return "%s<%s>" % (type(exc).__name__, str(exc)[:70])

    def _free(self, ct, p):
        if not (0 <= p.x < ct.get_map_width() and 0 <= p.y < ct.get_map_height()):
            return False
        try:
            if not ct.is_in_vision(p):
                return False
            if ct.get_tile_env(p) == Environment.WALL:
                return False
            if ct.get_tile_building_id(p) is not None:
                return False
            b = ct.get_tile_builder_bot_id(p)
            if b is not None and b != ct.get_id():
                return False
        except Exception:
            return False
        return True

    def _walk_to(self, tx, ty, budget=60):
        tgt = Position(tx, ty)
        for _ in range(budget):
            ct = self.ct
            if ct.get_position() == tgt:
                return
            if ct.get_move_cooldown() == 0:
                pos = ct.get_position()
                order = []
                if pos.x != tx:
                    order.append(Direction.EAST if tx > pos.x else Direction.WEST)
                if pos.y != ty:
                    order.append(Direction.SOUTH if ty > pos.y else Direction.NORTH)
                for d in order + list(CARD):
                    dx, dy = delta(d)
                    if self._free(ct, Position(pos.x + dx, pos.y + dy)):
                        try:
                            ct.move(d)
                        except Exception:
                            pass
                        break
            yield

    def _script(self):
        ct = self.ct
        self._note("=== vmisc : predicate traps ===")

        # Find an open spot with all four cardinal and all four diagonal neighbours free,
        # close to the west edge so x=-1 is inside vision.
        spot = None
        for p in ct.get_nearby_tiles():
            if p.x > 2 or not self._free(ct, p):
                continue
            if all(self._free(ct, Position(p.x + dx, p.y + dy))
                   for dx, dy in ((0, -1), (1, 0), (0, 1), (-1, 0),
                                  (1, -1), (1, 1), (-1, 1), (-1, -1))):
                spot = p
                break
        if spot is None:
            for p in ct.get_nearby_tiles():
                if self._free(ct, p) and all(
                        self._free(ct, Position(p.x + dx, p.y + dy))
                        for dx, dy in ((0, -1), (1, 0), (0, 1), (-1, 0), (1, -1))):
                    spot = p
                    break
        if spot is None:
            self._note("no open spot found")
            return
        yield from self._walk_to(spot.x, spot.y)
        while self.ct.get_move_cooldown() != 0:
            yield
        ct = self.ct
        here = ct.get_position()
        self._note("spot=(%d,%d) vision_sq=%d" % (here.x, here.y, ct.get_vision_radius_sq()))

        # --- 1. own tile ---
        self._note("SELFTILE passable=%s empty=%s can_move(CENTRE)=%s"
                   % (self._try(ct.is_tile_passable, here),
                      self._try(ct.is_tile_empty, here),
                      self._try(ct.can_move, Direction.CENTRE)))

        # --- 2. diagonals: predicate vs can_move vs move() ---
        for d in DIAG:
            dx, dy = delta(d)
            t = Position(here.x + dx, here.y + dy)
            self._note("DIAG %-9s tile=(%d,%d) passable=%s can_move=%s move()=%s pos_after=%s"
                       % (d.name, t.x, t.y,
                          self._try(ct.is_tile_passable, t),
                          self._try(ct.can_move, d),
                          self._try(ct.move, d),
                          self._try(ct.get_position)))
        self._note("CENTRE move()=%s pos_after=%s"
                   % (self._try(ct.move, Direction.CENTRE), self._try(ct.get_position)))
        yield
        ct = self.ct
        self._note("AFTER_DIAGONALS pos=(%d,%d) move_cd=%d (unchanged => none of them took effect)"
                   % (ct.get_position().x, ct.get_position().y, ct.get_move_cooldown()))

        # --- 3. vision gate + out-of-bounds ---
        ct = self.ct
        here = ct.get_position()
        ok, bad = set(), set()
        for dx in range(-7, 8):
            for dy in range(-7, 8):
                p = Position(here.x + dx, here.y + dy)
                if not (0 <= p.x < ct.get_map_width() and 0 <= p.y < ct.get_map_height()):
                    continue
                dsq = here.distance_squared(p)
                try:
                    ct.is_tile_passable(p)
                    ok.add(dsq)
                except Exception:
                    bad.add(dsq)
        self._note("VISION_GATE ok_dsq=%s" % sorted(ok))
        self._note("VISION_GATE raise_dsq=%s" % sorted(bad))
        oob = Position(-1, here.y)
        self._note("OOB_IN_VISION tile=(%d,%d) dsq=%d is_in_vision=%s passable=%s empty=%s env=%s"
                   % (oob.x, oob.y, here.distance_squared(oob),
                      self._try(ct.is_in_vision, oob),
                      self._try(ct.is_tile_passable, oob),
                      self._try(ct.is_tile_empty, oob),
                      self._try(ct.get_tile_env, oob)))
        far = Position(-6, here.y)
        self._note("OOB_OUT_VISION tile=(%d,%d) dsq=%d passable=%s"
                   % (far.x, far.y, here.distance_squared(far),
                      self._try(ct.is_tile_passable, far)))

        # --- 4. does can_move conflate impassable with move cooldown? ---
        while self.ct.get_move_cooldown() != 0:
            yield
        ct = self.ct
        here = ct.get_position()
        east = Position(here.x + 1, here.y)
        self._note("CD pre  pos=(%d,%d) cd=%d east_free=%s east_passable=%s can_move(E)=%s"
                   % (here.x, here.y, ct.get_move_cooldown(),
                      self._free(ct, east), self._try(ct.is_tile_passable, east),
                      self._try(ct.can_move, Direction.EAST)))
        mv = self._try(ct.move, Direction.EAST)
        p2 = ct.get_position()
        east2 = Position(p2.x + 1, p2.y)
        self._note("CD post pos=(%d,%d) move()=%s cd=%d next_east=(%d,%d) passable=%s "
                   "can_move(E)=%s second_move()=%s"
                   % (p2.x, p2.y, mv, ct.get_move_cooldown(), east2.x, east2.y,
                      self._try(ct.is_tile_passable, east2),
                      self._try(ct.can_move, Direction.EAST),
                      self._try(ct.move, Direction.EAST)))
        yield
        ct = self.ct
        self._note("CD next pos=(%d,%d) cd=%d can_move(E)=%s"
                   % (ct.get_position().x, ct.get_position().y, ct.get_move_cooldown(),
                      self._try(ct.can_move, Direction.EAST)))

        # --- 5. resign truncation: 1200 chars, landmarked every 20 ---
        payload = "".join("[%04d]xxxxxxxxxxxxx" % i for i in range(0, 1200, 20))[:1200]
        self._note("RESIGN payload length sent = %d" % len(payload))
        self.ct.resign(payload)
