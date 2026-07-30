"""Head-to-head: core-first outward laying vs ore-first inward laying.

MODE=outward : walk from the core toward the ore laying conveyors that face
               back at the core, harvester last  (the model Codex assumed)
MODE=inward  : walk to the ore, build the harvester first, then lay the line
               back toward the core, building on the bot's own tile
ALT=1        : never build and move in the same round (Codex's assumption)
"""
import json
import os
import sys

from fcode import Controller, Direction, EntityType, Position

CFG = json.load(open(os.environ["FCODE_ECON_CFG"]))
MODE, ALT = CFG["mode"], CFG["alt"]
OX, OY = CFG["ore"]
CX = CFG["core_x"]          # x of the core-adjacent conveyor tile
ROW = CFG["row"]


def log(*a):
    print(*a, file=sys.stderr, flush=True)


class Player:
    def __init__(self):
        self.x = None

    def run(self, ct: Controller) -> None:
        if ct.get_team().value != "a":
            return
        r = ct.get_current_round()
        if ct.get_entity_type() == EntityType.CORE:
            log(f"T {r} res={ct.get_global_resources()}")
            if r == 0:
                for p in ct.get_nearby_tiles(2):
                    if ct.can_spawn(p):
                        ct.spawn_builder(p)
                        break
            return
        self._builder(ct, r)

    def _builder(self, ct, r):
        pos = ct.get_position()
        if MODE == "inward":
            stand = Position(OX - 1, ROW)
            if self.x is None:
                if pos != stand:
                    self._go(ct, pos, stand)
                    return
                ct.build_harvester(Position(OX, OY))
                log(f"HARV r={r}")
                self.x = pos.x
                return
            if pos.x < CX:
                return
            acted = False
            if ct.can_build_conveyor(pos, Direction.WEST):
                ct.build_conveyor(pos, Direction.WEST)
                acted = True
            if pos.x == CX:
                return
            if not (ALT and acted) and ct.can_move(Direction.WEST):
                ct.move(Direction.WEST)
            return
        # outward: lay from the core tile out to the ore, all facing WEST,
        # and only then build the harvester at the far end
        if self.x is not None and self.x >= OX - 1:
            if ct.can_build_harvester(Position(OX, OY)):
                ct.build_harvester(Position(OX, OY))
                log(f"HARV r={r}")
            return
        tile = Position(CX, ROW) if self.x is None else Position(self.x + 1, ROW)
        if pos != tile:
            self._go(ct, pos, tile)
            return
        acted = False
        if ct.can_build_conveyor(pos, Direction.WEST):
            ct.build_conveyor(pos, Direction.WEST)
            self.x = pos.x
            acted = True
        if self.x is not None and self.x >= OX - 1:
            return
        if not (ALT and acted) and ct.can_move(Direction.EAST):
            ct.move(Direction.EAST)

    def _go(self, ct, pos, dest):
        dx, dy = dest.x - pos.x, dest.y - pos.y
        for d in ([Direction.EAST if dx > 0 else Direction.WEST] if dx else []) + \
                 ([Direction.SOUTH if dy > 0 else Direction.NORTH] if dy else []):
            if ct.can_move(d):
                ct.move(d)
                return
