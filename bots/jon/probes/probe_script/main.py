"""General scripted-build probe: one builder executes an ordered task list.

Task = [type, x, y, dir_or_null, not_before_round].
The builder walks until the target is inside its action radius, then builds.
Everything the core sees is logged per round so rates can be differenced out.
"""
import json
import os
import sys

from fcode import Controller, Direction, EntityType, Position

CFG = json.load(open(os.environ["FCODE_ECON_CFG"]))
TASKS = CFG["tasks"]
DIRS = {d.value: d for d in Direction}
CARD = [Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST]


def log(*a):
    print(*a, file=sys.stderr, flush=True)


class Player:
    def __init__(self):
        self.i = 0

    def run(self, ct: Controller) -> None:
        if ct.get_team().value != "a":
            return
        et = ct.get_entity_type()
        if et == EntityType.CORE:
            r = ct.get_current_round()
            log(f"T {r} res={ct.get_global_resources()} scale={ct.get_scale_percent():.2f}")
            if r == 0:
                for p in ct.get_nearby_tiles(2):
                    if ct.can_spawn(p):
                        ct.spawn_builder(p)
                        break
        elif et == EntityType.BUILDER_BOT:
            self._builder(ct)

    def _builder(self, ct):
        if self.i >= len(TASKS):
            return
        r = ct.get_current_round()
        pos = ct.get_position()
        kind, tx, ty, dname, not_before = TASKS[self.i]
        tgt = Position(tx, ty)
        if r < not_before:
            return
        if pos.distance_squared(tgt) <= 2:
            extra = DIRS[dname] if dname else None
            et = EntityType(kind)
            if ct.can_build(et, tgt, extra):
                ct.build(et, tgt, extra)
                log(f"BUILD i={self.i} {kind} at={(tx, ty)} dir={dname} r={r} "
                    f"scale={ct.get_scale_percent():.2f}")
                self.i += 1
                return
            if ct.get_tile_building_id(tgt) is not None:
                self.i += 1   # already there — skip
                return
        self._step(ct, pos, tgt)

    def _step(self, ct, pos, dest):
        dx, dy = dest.x - pos.x, dest.y - pos.y
        cands = []
        if abs(dx) >= abs(dy):
            if dx: cands.append(Direction.EAST if dx > 0 else Direction.WEST)
            if dy: cands.append(Direction.SOUTH if dy > 0 else Direction.NORTH)
        else:
            if dy: cands.append(Direction.SOUTH if dy > 0 else Direction.NORTH)
            if dx: cands.append(Direction.EAST if dx > 0 else Direction.WEST)
        for d in cands + CARD:
            if ct.can_move(d):
                ct.move(d)
                return
