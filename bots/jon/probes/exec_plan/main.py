"""Dumb, deterministic executor of a precomputed plan.

Given the true wall map and an explicit per-builder job list, this removes
pathfinding and scouting as confounds, so a builder-count sweep measures the
strategy rather than the bot.
"""
import json
import os
import sys
from collections import deque

from fcode import Controller, Direction, EntityType, GameError, Position

PLAN = json.load(open(os.environ["EP_PLAN"]))
WALLS = {tuple(t) for t in PLAN["walls"]}
FOOT = {tuple(t) for t in PLAN["foot"]}
EFOOT = {tuple(t) for t in PLAN["efoot"]}
W, H = PLAN["w"], PLAN["h"]
JOBS = PLAN["jobs"]                       # list per builder
NB = len(JOBS)
DIRS = {d.value: d for d in Direction}
D8 = [Direction.NORTH, Direction.NORTHEAST, Direction.EAST, Direction.SOUTHEAST,
      Direction.SOUTH, Direction.SOUTHWEST, Direction.WEST, Direction.NORTHWEST]
BLOCK = WALLS | FOOT | EFOOT


class Player:
    def __init__(self):
        self.idx = None
        self.n = 0
        self.job = 0
        self.stage = "goto"
        self.li = 0
        self.solid = set()               # harvesters we know block movement

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except GameError:
            pass          # an uncaught GameError destroys the unit

    def _run(self, ct: Controller) -> None:
        et = ct.get_entity_type()
        if et == EntityType.CORE:
            if os.environ.get("EP_TRACE"):
                print(f"T {ct.get_current_round()} {ct.get_global_resources()} "
                      f"{ct.get_scale_percent():.0f}", file=sys.stderr, flush=True)
            if self.n < NB and ct.get_global_resources() >= ct.get_builder_bot_cost():
                for p in ct.get_nearby_tiles(2):
                    if ct.can_spawn(p):
                        ct.spawn_builder(p)
                        self.n += 1
                        return
        elif et == EntityType.BUILDER_BOT:
            self._builder(ct)

    def _builder(self, ct):
        if os.environ.get("EP_DEBUG"):
            print(f"B idx={self.idx} r={ct.get_current_round()} pos={tuple(ct.get_position())} "
                  f"job={self.job} stage={self.stage} li={self.li}", file=sys.stderr, flush=True)
        if self.idx is None:
            self.idx = ct.read_store(0)
            ct.write_store(0, self.idx + 1)
            return
        if self.idx >= NB or self.job >= len(JOBS[self.idx]):
            return
        j = JOBS[self.idx][self.job]
        pos = ct.get_position()

        if self.stage == "goto":
            tgt = Position(*j["ore"])
            if 0 < pos.distance_squared(tgt) <= 2:
                if ct.can_build_harvester(tgt):
                    ct.build_harvester(tgt)
                    self.solid.add(tuple(j["ore"]))
                    self.stage, self.li = "lay", 0
                    if not j["lay"]:
                        self._next()
                    return
                if ct.get_tile_building_id(tgt) is not None:
                    self.solid.add(tuple(j["ore"]))   # someone got there first
                    self.stage, self.li = "lay", 0
                    if not j["lay"]:
                        self._next()
                    return
            self._step(ct, pos, tgt)
            return

        if self.stage == "lay":
            if self.li >= len(j["lay"]):
                self._next()
                return
            x, y, dname = j["lay"][self.li]
            tile, face = Position(x, y), DIRS[dname]
            if pos == tile:
                if ct.can_build_conveyor(tile, face):
                    ct.build_conveyor(tile, face)
                elif ct.get_tile_building_id(tile) is None:
                    return                            # cannot afford it yet; wait
                self.li += 1
                if self.li < len(j["lay"]):
                    nx, ny, _ = j["lay"][self.li]
                    self._step(ct, pos, Position(nx, ny), exact=True)
                else:
                    self._next()
                return
            self._step(ct, pos, tile, exact=True)

    def _next(self):
        self.job += 1
        self.stage = "goto"
        self.li = 0

    # --- exact BFS pathing over the true wall map ---
    def _step(self, ct, pos, dest, exact=False):
        path = self._bfs(pos, dest, exact)
        if path:
            for d in D8:
                if pos.add(d) == path and ct.can_move(d):
                    ct.move(d)
                    return
        for d in D8:                      # blocked: sidestep so we do not deadlock
            n = pos.add(d)
            if ct.can_move(d) and max(abs(n.x - dest.x), abs(n.y - dest.y)) <= \
                    max(abs(pos.x - dest.x), abs(pos.y - dest.y)):
                ct.move(d)
                return

    def _bfs(self, src, dest, exact=False):
        """First step of a shortest 8-connected path.

        exact=True targets the tile itself (conveyors are built under the bot);
        exact=False targets any tile beside it, and must never land ON it --
        a harvester cannot be built on the tile the builder occupies."""
        if exact:
            goal = {(dest.x, dest.y)}
        else:
            goal = {(dest.x + d.delta()[0], dest.y + d.delta()[1]) for d in D8}
        s = (src.x, src.y)
        if s in goal:
            return None
        prev = {s: None}
        q = deque([s])
        found = None
        while q:
            c = q.popleft()
            if c in goal and c != s:
                found = c
                break
            for d in D8:
                dx, dy = d.delta()
                n = (c[0] + dx, c[1] + dy)
                if n in prev or not (0 <= n[0] < W and 0 <= n[1] < H):
                    continue
                if n in BLOCK or n in self.solid:
                    continue
                prev[n] = c
                q.append(n)
        if found is None:
            return None
        c = found
        while prev[c] != s:
            c = prev[c]
            if c is None:
                return None
        return Position(*c)
