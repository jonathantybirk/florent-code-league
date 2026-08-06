"""VERIFICATION probe: does the OWNING TEAM ever change passability?

Team-A measurer, paired with `vprop` (team B). Every row is gated on OBSERVING the
building -- the probe refuses to record a row until get_tile_building_id returns an id
whose get_team is the enemy team -- so a prop that failed to build produces a loud
NEVER_APPEARED line instead of a quiet "impassable" that is really just empty ground.

Nine enemy rows: conveyor, splitter, harvester, barrier, gunner, sentinel, launcher,
builder bot, core. Paired against the nine own-side rows from `vown` + `vcore`.

    rm -rf bots/probes/vfoe/__pycache__ bots/probes/vprop/__pycache__
    .venv/Scripts/python.exe tools/runprobe.py vfoe --map passlab --vs vprop
"""

import os

from fcode import Controller, Direction, EntityType, Environment, Position

OUT = os.environ.get("VFOE_OUT") or (
    "C:/Users/edlun/AppData/Local/Temp/claude/"
    "c--Users-edlun-Desktop-lucky-shots-Hackathons-florent-code-league/"
    "69495691-95ef-4878-adf9-aeca64f3e3b5/scratchpad/vfoe.txt"
)

CARD = (Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST)
LANE_X = (7, 8, 9, 10, 11, 12, 13)
ENTER_LANE_ROUND = 130


class Player:
    def __init__(self):
        self.spawned = False
        self.gen = None
        self.ct = None
        self.dead = False
        self.log = []
        self.rows = []

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
            self._finish()
        except Exception as exc:
            self._note("FATAL %s: %s" % (type(exc).__name__, str(exc)[:200]))
            self.dead = True
            self._finish()

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

    def _finish(self):
        walk = [r[0] for r in self.rows if r[1]]
        msg = ("vfoe rows=%d walkthrough=[%s]" % (len(self.rows), ",".join(walk)))
        self._note("SUMMARY " + msg)
        try:
            self.ct.resign(msg[:480])
        except Exception:
            pass

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

    def _walk_to(self, tx, ty, budget=140):
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
                    dx = 1 if d is Direction.EAST else (-1 if d is Direction.WEST else 0)
                    dy = 1 if d is Direction.SOUTH else (-1 if d is Direction.NORTH else 0)
                    if self._free(ct, Position(pos.x + dx, pos.y + dy)):
                        try:
                            ct.move(d)
                        except Exception:
                            pass
                        break
            yield

    def _wait_round(self, r):
        while self.ct.get_current_round() < r:
            yield

    def _occupied_by_enemy(self, tile, want_builder=False):
        """Wait until tile holds an enemy entity; return (label, id) or None on timeout."""
        for _ in range(160):
            ct = self.ct
            try:
                eid = (ct.get_tile_builder_bot_id(tile) if want_builder
                       else ct.get_tile_building_id(tile))
                if eid is not None and ct.get_team(eid) != ct.get_team():
                    return (self._try(ct.get_entity_type, eid), eid)
            except Exception:
                pass
            yield
        return None

    def _row(self, tile, d, want_builder=False):
        hit = yield from self._occupied_by_enemy(tile, want_builder)
        ct = self.ct
        if hit is None:
            self._note("ROW NEVER_APPEARED tile=(%d,%d) -- nothing enemy-owned ever seen here"
                       % (tile.x, tile.y))
            return
        typ, eid = hit
        while self.ct.get_move_cooldown() != 0:
            yield
        ct = self.ct
        home = ct.get_position()
        tm = self._try(ct.get_team, eid)
        pa = self._try(ct.is_tile_passable, tile)
        em = self._try(ct.is_tile_empty, tile)
        env = self._try(ct.get_tile_env, tile)
        cm = self._try(ct.can_move, d)
        mv = self._try(ct.move, d)
        same = self._try(ct.get_position)
        yield
        ct = self.ct
        landed = ct.get_position()
        rel = landed == tile
        self.rows.append(("FOE_" + typ, rel, pa == "True", cm == "True"))
        self._note("ROW FOE_%-11s tile=(%d,%d) from=(%d,%d) dir=%-5s occ=%s/%s/%s env=%s "
                   "passable=%s empty=%s can_move=%s move()=%s same=%s next=(%d,%d) "
                   "RELOCATED=%s"
                   % (typ, tile.x, tile.y, home.x, home.y, d.name, eid, typ, tm, env,
                      pa, em, cm, mv, same, landed.x, landed.y, "True" if rel else "False"))
        if landed != home:
            yield from self._walk_to(home.x, home.y)

    def _script(self):
        ct = self.ct
        self._note("=== vfoe : enemy-side passability, occupancy-gated ===")
        self._note("map %dx%d id=%d team=%s pos=%s"
                   % (ct.get_map_width(), ct.get_map_height(), ct.get_id(),
                      self._try(ct.get_team), self._try(ct.get_position)))

        yield from self._walk_to(3, 10)
        yield from self._wait_round(ENTER_LANE_ROUND)

        for x in LANE_X:
            yield from self._walk_to(x, 10)
            if self.ct.get_position() != Position(x, 10):
                self._note("could not reach stance (%d,10), at %s"
                           % (x, self._try(self.ct.get_position)))
                continue
            yield from self._row(Position(x, 9), Direction.NORTH)

        # enemy builder bot, parked by vprop at (17,11)
        yield from self._walk_to(16, 10)
        yield from self._walk_to(16, 11)
        if self.ct.get_position() == Position(16, 11):
            yield from self._row(Position(17, 11), Direction.EAST, want_builder=True)
        else:
            self._note("could not reach (16,11) for the enemy-builder row")

        # enemy core
        yield from self._walk_to(16, 10)
        yield from self._walk_to(17, 10)
        yield from self._walk_to(17, 5)
        yield from self._walk_to(18, 5)
        if self.ct.get_position() == Position(18, 5):
            yield from self._row(Position(19, 5), Direction.EAST)
        else:
            self._note("could not reach (18,5) for the enemy-core row, at %s"
                       % self._try(self.ct.get_position))

        self._note("=== vfoe complete round %d ===" % self.ct.get_current_round())
