"""Scripted, fully deterministic economy probe.

Config (JSON via FCODE_ECON_CFG): {"spawns":[round,...], "targets":[[x,y],...]}
Builder i walks to targets[i], builds a harvester, then lays a westward conveyor
line back along row y until it feeds the core. Everything is logged per round.
"""
import json
import os
import sys

from fcode import Controller, Direction, EntityType, Position

CFG = json.load(open(os.environ["FCODE_ECON_CFG"]))
CARD = [Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST]


def log(*a):
    print(*a, file=sys.stderr, flush=True)


class Player:
    def __init__(self):
        self.n_spawned = 0
        self.idx = None
        self.phase = "goto"
        self.core = None
        self.target = None

    def run(self, ct: Controller) -> None:
        if ct.get_team().value != "a":
            return
        if ct.get_entity_type() == EntityType.CORE:
            self._core(ct)
        elif ct.get_entity_type() == EntityType.BUILDER_BOT:
            self._builder(ct)

    def _core(self, ct):
        r = ct.get_current_round()
        log(f"T {r} res={ct.get_global_resources()} scale={ct.get_scale_percent():.2f} "
            f"units={ct.get_unit_count()}")
        if r in CFG["spawns"] and self.n_spawned < len(CFG["targets"]):
            for p in ct.get_nearby_tiles(2):
                if ct.can_spawn(p):
                    ct.spawn_builder(p)
                    log(f"SPAWN r={r} at={tuple(p)} idx={self.n_spawned} cost_scale_now="
                        f"{ct.get_scale_percent():.2f}")
                    self.n_spawned += 1
                    break

    def _builder(self, ct):
        r = ct.get_current_round()
        pos = ct.get_position()
        if self.idx is None:
            if len(CFG["targets"]) == 1:
                self.idx = 0
            else:
                # Ticket dispenser: costs this bot its first round, so callers
                # with >1 builder must account for the one-round offset.
                self.idx = ct.read_store(0)
                ct.write_store(0, self.idx + 1)
            self.target = Position(*CFG["targets"][self.idx])
            self.core = Position(*CFG["core"])
            log(f"BOT idx={self.idx} r={r} pos={tuple(pos)} target={tuple(self.target)}")
            if len(CFG["targets"]) > 1:
                return

        if self.phase == "goto":
            # Stand on the tile immediately west of the ore.
            stand = Position(self.target.x - 1, self.target.y)
            if pos == stand:
                if ct.can_build_harvester(self.target):
                    ct.build_harvester(self.target)
                    log(f"HARV idx={self.idx} r={r} at={tuple(self.target)} "
                        f"scale={ct.get_scale_percent():.2f} res={ct.get_global_resources()}")
                    self.phase = "lay"
                return
            self._step_towards(ct, pos, stand)
            return

        if self.phase == "lay":
            # Conveyor on our own tile facing WEST, then step west. 1 tile/round.
            if pos.x <= self.core.x + 1:
                self.phase = "done"
                log(f"LINE_DONE idx={self.idx} r={r} pos={tuple(pos)}")
                return
            if ct.can_build_conveyor(pos, Direction.WEST):
                ct.build_conveyor(pos, Direction.WEST)
            if ct.can_move(Direction.WEST):
                ct.move(Direction.WEST)

    def _step_towards(self, ct, pos, dest):
        dx = dest.x - pos.x
        dy = dest.y - pos.y
        order = []
        if dx:
            order.append(Direction.EAST if dx > 0 else Direction.WEST)
        if dy:
            order.append(Direction.SOUTH if dy > 0 else Direction.NORTH)
        for d in order:
            if ct.can_move(d):
                ct.move(d)
                return
