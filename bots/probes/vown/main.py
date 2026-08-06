"""VERIFICATION probe: own-building passability on a STOCK map, plus the conveyor-facing
question pt_own never asked.

pt_own built every conveyor/splitter facing NORTH and always stepped onto it heading
NORTH -- i.e. always travelling WITH the belt. If passability depended on the belt facing,
that design could not have seen it. This probe builds each of conveyor and splitter facing
EAST and facing WEST and steps on from the west heading EAST both times, then parks on the
belt for 4 rounds to see whether the tile is merely enterable or actually habitable.

Everything is measured on a stock tournament map, so nothing here depends on maps/lab/.

    rm -rf bots/probes/vown/__pycache__
    .venv/Scripts/python.exe tools/runprobe.py vown --map duel --vs idle
"""

import os

from fcode import Controller, Direction, EntityType, Environment, Position

OUT = os.environ.get("VOWN_OUT") or (
    "C:/Users/edlun/AppData/Local/Temp/claude/"
    "c--Users-edlun-Desktop-lucky-shots-Hackathons-florent-code-league/"
    "69495691-95ef-4878-adf9-aeca64f3e3b5/scratchpad/vown.txt"
)
TAG = os.environ.get("VOWN_TAG", "?")

CARD = (Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST)


def delta(d):
    o = Position(50, 50)
    p = o.add(d)
    return p.x - o.x, p.y - o.y


DELTA = {d: delta(d) for d in CARD}

# (label, kind, extra_direction_or_None)
SPECS = (
    ("CONVEYOR_E", "conveyor", Direction.EAST),
    ("CONVEYOR_W", "conveyor", Direction.WEST),
    ("CONVEYOR_N", "conveyor", Direction.NORTH),
    ("SPLITTER_E", "splitter", Direction.EAST),
    ("SPLITTER_W", "splitter", Direction.WEST),
    ("BARRIER", "barrier", None),
    ("GUNNER", "gunner", Direction.EAST),
    ("SENTINEL", "sentinel", Direction.EAST),
    ("LAUNCHER", "launcher", None),
)


class Player:
    def __init__(self):
        self.spawned = False
        self.gen = None
        self.ct = None
        self.dead = False
        self.log = []
        self.walk = []   # labels that turned out walk-through

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
        msg = "vown[%s] walkthrough=[%s]" % (TAG, ",".join(self.walk))
        self._note("SUMMARY " + msg)
        try:
            self.ct.resign(msg[:480])
        except Exception:
            pass

    # ---- raw-fact pathing, never uses is_tile_passable ----

    def _raw_walkable(self, ct, p, allow=()):
        if not (0 <= p.x < ct.get_map_width() and 0 <= p.y < ct.get_map_height()):
            return False
        for a in allow:
            if p == a:
                return True
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

    def _step(self, ct, target):
        start = ct.get_position()
        if start == target:
            return None
        seen = {(start.x, start.y): None}
        frontier = [start]
        for _ in range(14):
            nxt = []
            for cur in frontier:
                for d in CARD:
                    dx, dy = DELTA[d]
                    p = Position(cur.x + dx, cur.y + dy)
                    key = (p.x, p.y)
                    if key in seen:
                        continue
                    if not self._raw_walkable(ct, p, allow=(target,)):
                        continue
                    first = seen[(cur.x, cur.y)] or d
                    seen[key] = first
                    if p == target:
                        return first
                    nxt.append(p)
            if not nxt:
                break
            frontier = nxt
        return None

    def _walk_to(self, target, budget=70):
        for _ in range(budget):
            ct = self.ct
            if ct.get_position() == target:
                return
            if ct.get_move_cooldown() == 0:
                d = self._step(ct, target)
                if d is not None:
                    try:
                        ct.move(d)
                    except Exception:
                        pass
            yield

    def _wait_act(self):
        while not self.ct.can_act():
            yield

    def _wait_move(self):
        while self.ct.get_move_cooldown() != 0:
            yield

    # ---- one measured row ----

    def _row(self, label, tile, d, linger=0):
        yield from self._wait_move()
        ct = self.ct
        home = ct.get_position()
        bid = self._try(ct.get_tile_building_id, tile)
        typ, tm = "-", "-"
        try:
            raw = ct.get_tile_building_id(tile)
            if raw is not None:
                typ = self._try(ct.get_entity_type, raw)
                tm = self._try(ct.get_team, raw)
        except Exception:
            pass
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
        line = ("ROW %-11s tile=%s from=(%d,%d) dir=%-5s occ=%s/%s/%s env=%s passable=%s "
                "empty=%s can_move=%s move()=%s same=%s next=(%d,%d) RELOCATED=%s"
                % (label, self._try(lambda: tile), home.x, home.y, d.name, bid, typ, tm,
                   env, pa, em, cm, mv, same, landed.x, landed.y,
                   "True" if rel else "False"))
        if rel:
            self.walk.append(label)
            track = []
            for _ in range(linger):
                yield
                ct = self.ct
                track.append("(%d,%d)/cd%d" % (ct.get_position().x, ct.get_position().y,
                                               ct.get_move_cooldown()))
            if track:
                line += "  LINGER=" + ">".join(track)
        self._note(line)
        if self.ct.get_position() != home:
            yield from self._walk_to(home)

    # ---- script ----

    def _script(self):
        ct = self.ct
        self._note("=== vown[%s] : own-building passability on a stock map ===" % TAG)
        self._note("map %dx%d id=%d team=%s pos=%s ti=%d"
                   % (ct.get_map_width(), ct.get_map_height(), ct.get_id(),
                      self._try(ct.get_team), self._try(ct.get_position),
                      ct.get_global_resources()))

        # Pick a stance with a free EAST neighbour and a free WEST neighbour (so we can
        # always retreat), away from the core footprint.
        stance = None
        for p in ct.get_nearby_tiles():
            if not self._raw_walkable(ct, p):
                continue
            e = Position(p.x + 1, p.y)
            w = Position(p.x - 1, p.y)
            if self._raw_walkable(ct, e) and self._raw_walkable(ct, w):
                stance = p
                break
        if stance is None:
            self._note("no usable stance found")
            return
        self._note("stance=(%d,%d) prop tile=(%d,%d)" % (stance.x, stance.y,
                                                         stance.x + 1, stance.y))
        yield from self._walk_to(stance)
        if self.ct.get_position() != stance:
            self._note("could not reach stance, at %s" % self._try(self.ct.get_position))
            return
        prop = Position(stance.x + 1, stance.y)

        for label, kind, extra in SPECS:
            yield from self._walk_to(stance)
            yield from self._wait_act()
            ct = self.ct
            args = (prop, extra) if extra is not None else (prop,)
            canb = self._try(getattr(ct, "can_build_" + kind), *args)
            built = self._try(getattr(ct, "build_" + kind), *args)
            self._note("BUILD %-11s at (%d,%d) can_build=%s build=%s ti=%d"
                       % (label, prop.x, prop.y, canb, built, ct.get_global_resources()))
            if built.startswith("GameError"):
                continue
            yield
            yield from self._row(label, prop, Direction.EAST,
                                 linger=4 if kind in ("conveyor", "splitter") else 0)
            yield from self._walk_to(stance)
            yield from self._wait_act()
            ct = self.ct
            self._note("      %-11s can_destroy=%s destroy=%s"
                       % (label, self._try(ct.can_destroy, prop),
                          self._try(ct.destroy, prop)))
            yield

        # ---- harvester: needs an ore tile ----
        ct = self.ct
        ore = None
        for p in ct.get_nearby_tiles():
            try:
                if ct.get_tile_env(p) == Environment.ORE_TITANIUM \
                        and ct.get_tile_building_id(p) is None:
                    ore = p
                    break
            except Exception:
                pass
        if ore is None:
            self._note("HARVESTER: no ore tile in vision, skipped")
        else:
            hstance = None
            for d in CARD:
                dx, dy = DELTA[d]
                cand = Position(ore.x - dx, ore.y - dy)
                if self._raw_walkable(self.ct, cand):
                    hstance, hdir = cand, d
                    break
            if hstance is None:
                self._note("HARVESTER: ore (%d,%d) has no walkable neighbour" % (ore.x, ore.y))
            else:
                yield from self._walk_to(hstance)
                if self.ct.get_position() != hstance:
                    self._note("HARVESTER: could not reach stance (%d,%d)"
                               % (hstance.x, hstance.y))
                else:
                    # First: is a BARE ore tile passable? (control for the harvester row)
                    yield from self._row("ORE_BARE", ore, hdir)
                    yield from self._walk_to(hstance)
                    yield from self._wait_act()
                    ct = self.ct
                    canb = self._try(ct.can_build_harvester, ore)
                    built = self._try(ct.build_harvester, ore)
                    self._note("BUILD %-11s at (%d,%d) can_build=%s build=%s"
                               % ("HARVESTER", ore.x, ore.y, canb, built))
                    yield
                    yield from self._row("HARVESTER", ore, hdir)

        self._note("=== vown[%s] complete round %d ===" % (TAG, self.ct.get_current_round()))
