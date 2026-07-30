"""Trunk-throughput probe: lay one westward trunk on row 2, then add harvesters
on the ore row above it one at a time, spaced far apart in time, and measure the
steady-state delivery rate after each addition."""
import json
import os
import sys

from fcode import Controller, Direction, EntityType, Position

CFG = json.load(open(os.environ["FCODE_ECON_CFG"]))
ORES = [tuple(o) for o in CFG["ores"]]
ADD_EVERY = CFG.get("add_every", 120)
TRUNK_Y, TRUNK_W, TRUNK_E = CFG["trunk_y"], CFG["trunk_w"], CFG["trunk_e"]


def log(*a):
    print(*a, file=sys.stderr, flush=True)


class Player:
    def __init__(self):
        self.phase = "east"
        self.built = 0

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
        r = ct.get_current_round()
        pos = ct.get_position()

        if self.phase == "east":                      # walk out to trunk start
            if pos == Position(TRUNK_E, TRUNK_Y):
                self.phase = "lay"
            else:
                self._step(ct, pos, Position(TRUNK_E, TRUNK_Y))
                return

        if self.phase == "lay":                       # conveyor under self, step west
            if ct.can_build_conveyor(pos, Direction.WEST):
                ct.build_conveyor(pos, Direction.WEST)
            if pos.x <= TRUNK_W:                      # last tile before the core
                self.phase = "harvest"
                log(f"TRUNK_DONE r={r} scale={ct.get_scale_percent():.2f}")
                return
            if ct.can_move(Direction.WEST):
                ct.move(Direction.WEST)
            return

        if self.phase == "harvest":
            if self.built >= len(ORES):
                return
            ox, oy = ORES[self.built]
            stand = Position(ox, TRUNK_Y)
            if pos != stand:
                self._step(ct, pos, stand)
                return
            # Stagger additions so each steady-state rate is measured cleanly.
            if r < CFG["first_harv_round"] + self.built * ADD_EVERY:
                return
            if ct.can_build_harvester(Position(ox, oy)):
                ct.build_harvester(Position(ox, oy))
                self.built += 1
                log(f"HARV n={self.built} r={r} at={(ox, oy)} "
                    f"scale={ct.get_scale_percent():.2f}")

    def _step(self, ct, pos, dest):
        dx, dy = dest.x - pos.x, dest.y - pos.y
        for d in ([Direction.EAST if dx > 0 else Direction.WEST] if dx else []) + \
                 ([Direction.SOUTH if dy > 0 else Direction.NORTH] if dy else []):
            if ct.can_move(d):
                ct.move(d)
                return
