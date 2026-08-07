"""Empirical probe: does a Splitter's round-robin only rotate among outputs
that currently have somewhere to go, or does it blindly cycle through all
3 geometric output slots regardless of what's built there?

Builds exactly one route -- Harvester -> Conveyor chain -> Splitter --
where the Splitter's capping output touches the Core and its other two
valid outputs are left bare (nothing built on them). Counts:

  D = rounds the Splitter is observed holding a stack. Each of these is a
      dispatch: the docs say a Splitter unconditionally sends whatever it
      holds every round it holds anything, so "observed occupied" and "a
      dispatch happened this round" are the same event.
  R = stacks that actually arrived at the Core via this route, backed out
      of the team's resource total by subtracting the known passive
      trickle (10 every PASSIVE_TITANIUM_INTERVAL rounds, exact and
      unconditional) from the raw gain over the measurement window.

R/D near 1/3 means the rotation is "dumb" -- bots/test/econ's hardcoded 1/3
Splitter weight is correct regardless of how many of the other two sides
are built out. R/D near 1.0 means the rotation only ever uses outputs that
lead somewhere, and econ's fixed 1/3 underestimates any Splitter that
doesn't have all three sides built -- the common case in a real network.
"""

import importlib.util
import random
from pathlib import Path

from fcode import Controller, Direction, Environment, EntityType, GameConstants, Position

CARDINALS = [Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST]

STORE_CHAIN_DONE = 0
STORE_SPLITTER_POS = 1
POS_PACK_BASE = 1024

MEASURE_DELAY = 5        # rounds after chain completion before baselining
MEASURE_UNTIL_ROUND = 900  # hard stop well before MAX_TURNS=1000


def _load_econ():
    econ_main = Path(__file__).resolve().parent.parent / "econ" / "main.py"
    spec = importlib.util.spec_from_file_location("econ_lib", econ_main)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


econ = _load_econ()


def in_bounds(ct: Controller, pos: Position) -> bool:
    return 0 <= pos.x < ct.get_map_width() and 0 <= pos.y < ct.get_map_height()


def _pack_pos(pos: Position) -> int:
    # +1 offset so 0 stays an unambiguous "nothing written yet" sentinel.
    return (pos.x + 1) * POS_PACK_BASE + (pos.y + 1)


def _unpack_pos(value: int) -> Position | None:
    if value == 0:
        return None
    return Position(value // POS_PACK_BASE - 1, value % POS_PACK_BASE - 1)


class Player:
    def __init__(self):
        self.core_tiles: list[Position] = []
        self.harvester_pos: Position | None = None
        self.trail_pos: Position | None = None
        self.chain_done = False
        self.chain_done_round: int | None = None
        self.splitter_pos: Position | None = None
        self.baseline_round: int | None = None
        self.baseline_resources: int | None = None
        self.dispatch_rounds = 0

    def run(self, ct: Controller) -> None:
        etype = ct.get_entity_type()
        if etype == EntityType.CORE:
            self._run_core(ct)
        elif etype == EntityType.BUILDER_BOT:
            self._run_builder(ct)

    # --- Core: spawn one builder, then count Splitter dispatches vs Core arrivals ---

    def _run_core(self, ct: Controller) -> None:
        if ct.get_unit_count() < 2:
            for pos in ct.get_nearby_tiles(dist_sq=2):
                if ct.can_spawn(pos):
                    ct.spawn_builder(pos)
                    break

        round_ = ct.get_current_round()
        if ct.read_store(STORE_CHAIN_DONE) == 1 and self.chain_done_round is None:
            self.chain_done_round = round_
            self.splitter_pos = _unpack_pos(ct.read_store(STORE_SPLITTER_POS))
            if self.splitter_pos is None:
                ct.resign(message=f"SETUP_FAILED round={round_} chain capped with a plain "
                                   f"Conveyor instead of a Splitter -- nothing to probe")
                return

        if self.chain_done_round is None:
            return

        if self.baseline_round is None and round_ >= self.chain_done_round + MEASURE_DELAY:
            self.baseline_round = round_
            self.baseline_resources = ct.get_global_resources()
            self.dispatch_rounds = 0

        if self.baseline_round is None:
            return

        bid = ct.get_tile_building_id(self.splitter_pos)
        if bid is not None and ct.get_stored_resource(bid) is not None:
            self.dispatch_rounds += 1

        if round_ >= MEASURE_UNTIL_ROUND:
            self._report(ct, round_)

    def _report(self, ct: Controller, round_: int) -> None:
        elapsed = round_ - self.baseline_round
        passive_ticks = elapsed // GameConstants.PASSIVE_TITANIUM_INTERVAL
        passive_total = passive_ticks * GameConstants.PASSIVE_TITANIUM_AMOUNT
        gain = ct.get_global_resources() - self.baseline_resources
        route_gain = gain - passive_total
        arrivals = route_gain / GameConstants.STACK_SIZE
        ratio = (arrivals / self.dispatch_rounds) if self.dispatch_rounds else None
        ratio_text = f"{ratio:.4f}" if ratio is not None else "n/a"
        ct.resign(
            message=(
                f"elapsed={elapsed} dispatch_rounds={self.dispatch_rounds} "
                f"raw_gain={gain} passive_total={passive_total} "
                f"route_gain={route_gain} arrivals~={arrivals:.2f} "
                f"ratio~={ratio_text}"
            )
        )

    # --- Builder: find ore, build a Harvester, lay Conveyors, finish with a Splitter ---
    # Same routing as bots/test/econ_demo, plus publishing the Splitter's
    # position to the store so the Core can watch it directly.

    def _run_builder(self, ct: Controller) -> None:
        pos = ct.get_position()
        if not self.core_tiles:
            for tile in ct.get_nearby_tiles():
                bid = ct.get_tile_building_id(tile)
                if bid is not None and ct.get_entity_type(bid) == EntityType.CORE:
                    self.core_tiles.append(tile)

        if self.harvester_pos is None:
            self._seek_and_harvest(ct, pos)
        elif not self.chain_done and self.core_tiles:
            self._lay_chain_toward_core(ct, pos)

    def _seek_and_harvest(self, ct: Controller, pos: Position) -> None:
        for d in CARDINALS:
            tile = pos.add(d)
            if not in_bounds(ct, tile):
                continue
            if ct.get_tile_env(tile) == Environment.ORE_TITANIUM and ct.can_build_harvester(tile):
                ct.build_harvester(tile)
                self.harvester_pos = tile
                self.trail_pos = pos
                return

        ore_tiles = [t for t in ct.get_nearby_tiles() if ct.get_tile_env(t) == Environment.ORE_TITANIUM]
        if ore_tiles:
            target = min(ore_tiles, key=lambda t: pos.distance_squared(t))
            direction = pos.cardinal_direction_to(target)
            if ct.can_move(direction):
                ct.move(direction)
                return

        open_dirs = [d for d in CARDINALS if ct.can_move(d) and ct.get_tile_env(pos.add(d)) == Environment.EMPTY]
        move_options = open_dirs or [d for d in CARDINALS if ct.can_move(d)]
        if move_options:
            ct.move(random.choice(move_options))

    def _pick_direction(self, ct: Controller, pos: Position) -> Direction | None:
        assert self.core_tiles
        core_tile = min(self.core_tiles, key=lambda t: pos.distance_squared(t))
        dx = core_tile.x - pos.x
        dy = core_tile.y - pos.y
        preferred = []
        if dx != 0:
            preferred.append(Direction.EAST if dx > 0 else Direction.WEST)
        if dy != 0:
            preferred.append(Direction.SOUTH if dy > 0 else Direction.NORTH)
        for d in preferred + CARDINALS:
            if ct.can_move(d):
                return d
        return None

    def _direction_to_core(self, ct: Controller, pos: Position) -> Direction | None:
        for d in CARDINALS:
            neighbor = pos.add(d)
            if not in_bounds(ct, neighbor):
                continue
            bid = ct.get_tile_building_id(neighbor)
            if bid is not None and ct.get_entity_type(bid) == EntityType.CORE:
                return d
        return None

    def _lay_chain_toward_core(self, ct: Controller, pos: Position) -> None:
        if self.trail_pos != pos:
            core_dir = self._direction_to_core(ct, self.trail_pos)
            if core_dir is not None:
                if ct.can_build_splitter(self.trail_pos, core_dir):
                    ct.build_splitter(self.trail_pos, core_dir)
                    ct.write_store(STORE_SPLITTER_POS, _pack_pos(self.trail_pos))
                elif ct.can_build_conveyor(self.trail_pos, core_dir):
                    ct.build_conveyor(self.trail_pos, core_dir)
                self.chain_done = True
                ct.write_store(STORE_CHAIN_DONE, 1)
                return

            facing = self.trail_pos.cardinal_direction_to(pos)
            if ct.can_build_conveyor(self.trail_pos, facing):
                ct.build_conveyor(self.trail_pos, facing)
            self.trail_pos = pos

        direction = self._pick_direction(ct, pos)
        if direction is None:
            self.chain_done = True
            ct.write_store(STORE_CHAIN_DONE, 1)
            return
        if ct.can_move(direction):
            ct.move(direction)
