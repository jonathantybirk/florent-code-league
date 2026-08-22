"""Real-engine smoke test for bots/test/econ/main.py's expected_titanium_flow
and expected_titanium_schedule.

Not a competitive bot. It lays exactly one route to the Core -- Harvester ->
Conveyor chain -> Splitter -> Core, the same shape the econ README's worked
example walks through -- waits long enough for titanium to actually start
flowing through it, then has the Core call the real (imported, not copied)
econ functions and resign with the results in the message. `fcode run`
prints a resign message, so this surfaces real numbers from a real match
instead of only from a hand-built fake Controller. SCHEDULE_ROUNDS is
deliberately larger than expected_titanium_flow's fixed 4-round window, so
this also exercises the schedule reaching further than that window allows.
"""

import importlib.util
import random
from pathlib import Path

from fcode import Controller, Direction, Environment, EntityType, Position

CARDINALS = [Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST]

STORE_CHAIN_DONE = 0
ROUNDS_TO_LET_TITANIUM_FLOW = 30
GIVE_UP_ROUND = 300
SCHEDULE_ROUNDS = 8  # deliberately > the old 4-round window expected_titanium_flow uses


def _load_econ():
    # Imported under a name distinct from "main" so it can't collide with
    # however the engine's own subinterpreter loads this file.
    econ_main = Path(__file__).resolve().parent.parent / "econ" / "main.py"
    spec = importlib.util.spec_from_file_location("econ_lib", econ_main)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


econ = _load_econ()


def in_bounds(ct: Controller, pos: Position) -> bool:
    return 0 <= pos.x < ct.get_map_width() and 0 <= pos.y < ct.get_map_height()


class Player:
    def __init__(self):
        self.core_tiles: list[Position] = []
        self.harvester_pos: Position | None = None
        self.trail_pos: Position | None = None
        self.chain_done = False
        self.chain_done_round: int | None = None
        self.max_flow_seen = 0.0
        self.max_flow_round: int | None = None
        self.max_schedule_seen = [0.0] * SCHEDULE_ROUNDS

    def run(self, ct: Controller) -> None:
        etype = ct.get_entity_type()
        if etype == EntityType.CORE:
            self._run_core(ct)
        elif etype == EntityType.BUILDER_BOT:
            self._run_builder(ct)

    # --- Core: spawn one builder, then wait for the chain and report ---

    def _run_core(self, ct: Controller) -> None:
        if ct.get_unit_count() < 2:
            for pos in ct.get_nearby_tiles(dist_sq=2):
                if ct.can_spawn(pos):
                    ct.spawn_builder(pos)
                    break

        round_ = ct.get_current_round()
        if ct.read_store(STORE_CHAIN_DONE) == 1 and self.chain_done_round is None:
            self.chain_done_round = round_

        # A single snapshot can catch the chain between deliveries (a
        # Splitter dispatches its whole stack the instant it fires, so it
        # reads empty most rounds even when the route is healthy) -- poll
        # every round once the chain exists and keep the peak reading
        # instead of trusting whatever the last round happened to show.
        if self.chain_done_round is not None:
            flow = econ.expected_titanium_flow(ct)
            if flow > self.max_flow_seen:
                self.max_flow_seen = flow
                self.max_flow_round = round_
            schedule = econ.expected_titanium_schedule(ct, SCHEDULE_ROUNDS)
            self.max_schedule_seen = [max(a, b) for a, b in zip(self.max_schedule_seen, schedule)]

        ready = self.chain_done_round is not None and round_ >= self.chain_done_round + ROUNDS_TO_LET_TITANIUM_FLOW
        if ready or round_ >= GIVE_UP_ROUND:
            flow = econ.expected_titanium_flow(ct)
            schedule = econ.expected_titanium_schedule(ct, SCHEDULE_ROUNDS)
            ct.resign(
                message=(
                    f"round={round_} chain_done_round={self.chain_done_round} "
                    f"flow_now={flow:.4f} "
                    f"max_flow_seen={self.max_flow_seen:.4f} at round {self.max_flow_round} "
                    f"schedule_now={[round(v, 2) for v in schedule]} "
                    f"max_schedule_seen={[round(v, 2) for v in self.max_schedule_seen]}"
                )
            )

    # --- Builder: find ore, build a Harvester, lay Conveyors, finish with a Splitter ---
    # Adapted from docs/official/tutorials/conveyors-logistics (last-mile + splitting-the-flow),
    # with two fixes found by running this against real maps -- see the
    # comments in _pick_direction and _lay_chain_toward_core.

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
        # Steer toward whichever footprint corner is nearest to pos right
        # now, not a corner recorded once on first sighting -- anchoring on
        # an arbitrary corner is what put a pivot decision (see
        # _lay_chain_toward_core) one tile away from where it needed to be,
        # leaving a corner Conveyor facing straight past the turn instead
        # of around it.
        assert self.core_tiles
        core_tile = min(self.core_tiles, key=lambda t: pos.distance_squared(t))
        dx = core_tile.x - pos.x
        dy = core_tile.y - pos.y
        preferred = []
        if dx != 0:
            preferred.append(Direction.EAST if dx > 0 else Direction.WEST)
        if dy != 0:
            preferred.append(Direction.SOUTH if dy > 0 else Direction.NORTH)

        # A single wall on the preferred axis used to mean "give up" even
        # with an obvious way around -- sidestep on any other open
        # direction rather than stopping dead next to an obstacle.
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
        # self.trail_pos is always a tile the Builder has already walked
        # off of -- guaranteed empty and legal to build on *from here*,
        # unlike pos itself (a Builder can never build on its own tile).
        # The original (tutorial) version built the *next* tile ahead of
        # itself before moving, locking in that tile's facing from a
        # direction chosen before the following turn's direction was known.
        # That's fine on a straight run, but at the one tile where the
        # route bends, the facing gets locked in a turn early and ends up
        # pointing straight past the bend instead of around it. Building
        # only ever behind where the Builder has actually been avoids that
        # by construction: a tile's facing is never assigned until we know
        # exactly which tile it needs to reach.
        if self.trail_pos != pos:
            core_dir = self._direction_to_core(ct, self.trail_pos)
            if core_dir is not None:
                # trail_pos is adjacent to the Core -- cap the chain here.
                if ct.can_build_splitter(self.trail_pos, core_dir):
                    ct.build_splitter(self.trail_pos, core_dir)
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
