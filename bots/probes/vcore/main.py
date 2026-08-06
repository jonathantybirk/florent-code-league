"""VERIFICATION probe: is a team's OWN Core really impassable to its own builder bot?

Independent re-derivation of the pt_own / pt_foe / pt_core claim. Deliberately harsher:
pt_own tested ONE core tile from ONE stance; pt_foe tested a second tile from a second
stance. Both happened to be the column of Core A nearest the map centre. This probe
enumerates EVERY (core footprint tile, cardinal approach direction) pair that is
physically reachable -- up to 16 per map -- so a "the core is passable from the far side"
escape hatch cannot survive.

Map-agnostic: the core footprint is discovered by get_tile_building_id + get_entity_type
+ get_team, never hardcoded. Pathing uses RAW facts (get_tile_env / building id /
builder id), never is_tile_passable, so the predicate under test is not used to reach
its own measurement.

    rm -rf bots/probes/vcore/__pycache__
    .venv/Scripts/python.exe tools/runprobe.py vcore --map sprint --vs idle
"""

import os

from fcode import Controller, Direction, EntityType, Environment, Position

OUT = os.environ.get("VCORE_OUT") or (
    "C:/Users/edlun/AppData/Local/Temp/claude/"
    "c--Users-edlun-Desktop-lucky-shots-Hackathons-florent-code-league/"
    "69495691-95ef-4878-adf9-aeca64f3e3b5/scratchpad/vcore.txt"
)
TAG = os.environ.get("VCORE_TAG", "?")

CARD = (Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST)


def delta(d):
    o = Position(50, 50)
    p = o.add(d)
    return p.x - o.x, p.y - o.y


DELTA = {d: delta(d) for d in CARD}


class Player:
    def __init__(self):
        self.spawned = False
        self.gen = None
        self.ct = None
        self.dead = False
        self.log = []
        self.rows = []

    # ---------------- plumbing ----------------

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
        n = len(self.rows)
        pt = sum(1 for r in self.rows if r[0])
        cm = sum(1 for r in self.rows if r[1])
        rl = sum(1 for r in self.rows if r[2])
        msg = ("vcore[%s] OWN_CORE pairs=%d passable=%d can_move=%d relocated=%d"
               % (TAG, n, pt, cm, rl))
        self._note("SUMMARY " + msg)
        try:
            self.ct.resign(msg[:480])
        except Exception:
            pass

    # ---------------- raw-fact pathing (never uses is_tile_passable) ----------------

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
        """One BFS step toward target over raw-walkable tiles. Returns a Direction or None."""
        start = ct.get_position()
        if start == target:
            return None
        seen = {(start.x, start.y): None}
        frontier = [start]
        for _ in range(12):
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

    def _walk_to(self, target, budget=60):
        for _ in range(budget):
            ct = self.ct
            if ct.get_position() == target:
                return True
            if ct.get_move_cooldown() == 0:
                d = self._step(ct, target)
                if d is not None:
                    try:
                        ct.move(d)
                    except Exception:
                        pass
            yield
        return self.ct.get_position() == target

    # ---------------- the script ----------------

    def _script(self):
        ct = self.ct
        self._note("=== vcore[%s] : own-Core passability, exhaustive ===" % TAG)
        self._note("map %dx%d round=%d id=%d team=%s pos=%s vision_sq=%d"
                   % (ct.get_map_width(), ct.get_map_height(), ct.get_current_round(),
                      ct.get_id(), self._try(ct.get_team), self._try(ct.get_position),
                      ct.get_vision_radius_sq()))

        # --- discover the own-core footprint from entity facts, never hardcoded ---
        mine = ct.get_team()
        core_tiles = []
        for p in ct.get_nearby_tiles():
            try:
                bid = ct.get_tile_building_id(p)
                if bid is None:
                    continue
                if ct.get_entity_type(bid) == EntityType.CORE and ct.get_team(bid) == mine:
                    core_tiles.append(p)
            except Exception:
                pass
        core_tiles.sort(key=lambda p: (p.y, p.x))
        self._note("own core footprint tiles = %s"
                   % " ".join("(%d,%d)" % (p.x, p.y) for p in core_tiles))

        # --- predicate on every core tile, from a distance, with no movement at all ---
        for p in core_tiles:
            self._note("STATIC   core_tile=(%d,%d)  is_tile_passable=%s  is_tile_empty=%s  "
                       "env=%s  building=%s"
                       % (p.x, p.y,
                          self._try(ct.is_tile_passable, p),
                          self._try(ct.is_tile_empty, p),
                          self._try(ct.get_tile_env, p),
                          self._try(ct.get_tile_building_id, p)))

        # --- enumerate every (core tile, approach direction) pair ---
        cset = {(p.x, p.y) for p in core_tiles}
        pairs = []
        for t in core_tiles:
            for d in CARD:
                dx, dy = DELTA[d]
                s = Position(t.x - dx, t.y - dy)       # stance: step d from s lands on t
                if (s.x, s.y) in cset:
                    continue                            # stance inside the core itself
                if not (0 <= s.x < ct.get_map_width() and 0 <= s.y < ct.get_map_height()):
                    continue
                pairs.append((t, d, s))
        self._note("candidate (core_tile, dir, stance) pairs = %d" % len(pairs))

        for t, d, s in pairs:
            ok = yield from self._walk_to(s)
            ct = self.ct
            if ct.get_position() != s:
                self._note("PAIR t=(%d,%d) dir=%-5s stance=(%d,%d)  UNREACHABLE (stopped at %s)"
                           % (t.x, t.y, d.name, s.x, s.y, self._try(ct.get_position)))
                continue
            while self.ct.get_move_cooldown() != 0:
                yield
            ct = self.ct
            home = ct.get_position()
            bid = self._try(ct.get_tile_building_id, t)
            typ = "?"
            tm = "?"
            try:
                raw = ct.get_tile_building_id(t)
                if raw is not None:
                    typ = self._try(ct.get_entity_type, raw)
                    tm = self._try(ct.get_team, raw)
            except Exception:
                pass
            pa = self._try(ct.is_tile_passable, t)
            cm = self._try(ct.can_move, d)
            mv = self._try(ct.move, d)
            same = self._try(ct.get_position)
            yield
            ct = self.ct
            landed = ct.get_position()
            rel = (landed == t)
            self.rows.append((pa == "True", cm == "True", rel))
            self._note("PAIR t=(%d,%d) dir=%-5s stance=(%d,%d) occ=%s/%s/%s  passable=%s  "
                       "move_cd=0 can_move=%s  move()=%s  same_round=%s  next_round=(%d,%d)  "
                       "RELOCATED=%s"
                       % (t.x, t.y, d.name, s.x, s.y, bid, typ, tm, pa, cm, mv, same,
                          landed.x, landed.y, "True" if rel else "False"))
            if landed != home:
                yield from self._walk_to(home)

        self._note("=== vcore[%s] complete round %d ===" % (TAG, self.ct.get_current_round()))
