"""Empirical probe: does ct.get_tile_building_id (position-based) and the
id-based getters (get_entity_type/get_team/get_direction/get_position/
get_stored_resource) respect vision, or do they return real ground truth for
a tile/id no team member currently has in sight?

fake_controller.py's stand-in implementation does NOT gate any of these by
vision at all (confirmed by reading its source) -- but it explicitly
documents itself as a minimal stand-in, not a faithful vision model, so
that result says nothing about the real engine. bots/test/econ2's
_observe_flow and bots/test/econ's _is_receiver both defensively call
ct.is_in_vision() before trusting these getters; this settles whether that
guard is load-bearing or redundant, the same way bots/test/splitter_probe
settled the Splitter rotation question against the real engine instead of
guessing from docs.

First run (position-based only) already answered half of this: calling
ct.get_tile_building_id on a position outside vision raises
`GameError: Position out of vision range` -- not None, not omniscient
ground truth. This version also tests the id-based getters using an id
obtained legitimately (the Builder's own build_conveyor return value,
published over the store), to see whether an id you already hold is
*separately* vision-gated once the tile that id refers to leaves vision, or
whether only the position->id lookup itself is restricted.

Setup: a Builder Bot walks well past the Core's vision radius (dist_sq=36,
so anything past ~dist_sq=100 is unambiguous), builds one Conveyor out
there, publishes both its position and the id build_conveyor returned, then
keeps walking further away so nothing on the team has that tile in vision
by the time the Core checks it. The Core, which has never had that tile in
vision at any point, then queries both ways and resigns with the results.
"""

import random

from fcode import Controller, Direction, Environment, EntityType, Position

CARDINALS = [Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST]

STORE_PROBE_READY = 0
STORE_PROBE_X = 1
STORE_PROBE_Y = 2
STORE_PROBE_ID = 3

WALK_AWAY_DIST_SQ = 150  # comfortably past CORE_VISION_RADIUS_SQ=36
KEEP_WALKING_AFTER_BUILD = 8  # rounds -- so the builder's own vision clears it too
GIVE_UP_ROUND = 400


def in_bounds(ct: Controller, pos: Position) -> bool:
    return 0 <= pos.x < ct.get_map_width() and 0 <= pos.y < ct.get_map_height()


def _try(fn):
    try:
        return repr(fn()), None
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"


class Player:
    def __init__(self):
        self.start_pos: Position | None = None
        self.built = False
        self.built_pos: Position | None = None
        self.built_id: int | None = None
        self.rounds_since_build = 0
        self.reported = False

    def run(self, ct: Controller) -> None:
        etype = ct.get_entity_type()
        if etype == EntityType.CORE:
            self._run_core(ct)
        elif etype == EntityType.BUILDER_BOT:
            self._run_builder(ct)

    # --- Core: spawn a builder, wait for the probe tile, then query it ---

    def _run_core(self, ct: Controller) -> None:
        if ct.get_unit_count() < 2:
            for pos in ct.get_nearby_tiles(dist_sq=2):
                if ct.can_spawn(pos):
                    ct.spawn_builder(pos)
                    break

        round_ = ct.get_current_round()
        if self.reported:
            return

        if ct.read_store(STORE_PROBE_READY) != 1:
            if round_ >= GIVE_UP_ROUND:
                ct.resign(message=f"SETUP_FAILED round={round_}: builder never finished the probe")
                self.reported = True
            return

        probe_pos = Position(ct.read_store(STORE_PROBE_X), ct.read_store(STORE_PROBE_Y))
        probe_id = ct.read_store(STORE_PROBE_ID)
        self._report(ct, round_, probe_pos, probe_id)

    def _report(self, ct: Controller, round_: int, probe_pos: Position, probe_id: int) -> None:
        in_vision = ct.is_in_vision(probe_pos)
        dist_sq = ct.get_position().distance_squared(probe_pos)

        # Positive control: the Core's own tile is always in its own vision.
        # If this ALSO errored, the probe itself would be broken, not
        # demonstrating real vision-gating.
        own_bid_val, own_bid_err = _try(lambda: ct.get_tile_building_id(ct.get_position()))
        own_etype_val, own_etype_err = _try(lambda: ct.get_entity_type(ct.get_id()))

        bid_val, bid_err = _try(lambda: ct.get_tile_building_id(probe_pos))

        # id-based getters, using the id the Builder captured directly from
        # build_conveyor's return value -- bypasses the position lookup
        # entirely, to isolate whether id-based access is separately gated.
        etype_val, etype_err = _try(lambda: ct.get_entity_type(probe_id))
        team_val, team_err = _try(lambda: ct.get_team(probe_id))
        dir_val, dir_err = _try(lambda: ct.get_direction(probe_id))
        pos_val, pos_err = _try(lambda: ct.get_position(probe_id))
        stored_val, stored_err = _try(lambda: ct.get_stored_resource(probe_id))

        def field(name, val, err):
            return f"{name}={val if err is None else '<' + err + '>'}"

        ct.resign(
            message=(
                f"round={round_} probe_pos=({probe_pos.x},{probe_pos.y}) probe_id={probe_id} "
                f"dist_sq_from_core={dist_sq} is_in_vision={in_vision} | "
                f"CONTROL (own tile, always in vision): "
                f"{field('get_tile_building_id', own_bid_val, own_bid_err)} "
                f"{field('get_entity_type', own_etype_val, own_etype_err)} | "
                f"POSITION-BASED: {field('get_tile_building_id', bid_val, bid_err)} | "
                f"ID-BASED: {field('get_entity_type', etype_val, etype_err)} "
                f"{field('get_team', team_val, team_err)} "
                f"{field('get_direction', dir_val, dir_err)} "
                f"{field('get_position', pos_val, pos_err)} "
                f"{field('get_stored_resource', stored_val, stored_err)}"
            )
        )
        self.reported = True

    # --- Builder: walk far, build one Conveyor, keep walking, publish it ---

    def _run_builder(self, ct: Controller) -> None:
        pos = ct.get_position()
        if self.start_pos is None:
            self.start_pos = pos

        if self.built:
            self.rounds_since_build += 1
            if self.rounds_since_build == 1:
                self._publish(ct)
            if self.rounds_since_build <= KEEP_WALKING_AFTER_BUILD:
                self._walk_east(ct, pos)
            return

        if self.start_pos.distance_squared(pos) >= WALK_AWAY_DIST_SQ:
            self._try_build(ct, pos)
            return

        self._walk_east(ct, pos)

    def _try_build(self, ct: Controller, pos: Position) -> None:
        for d in CARDINALS:
            target = pos.add(d)
            if not in_bounds(ct, target):
                continue
            if ct.get_tile_env(target) == Environment.EMPTY and ct.can_build_conveyor(target, Direction.NORTH):
                built_id = ct.build_conveyor(target, Direction.NORTH)
                self.built = True
                self.built_pos = target
                self.built_id = built_id if isinstance(built_id, int) else ct.get_tile_building_id(target)
                return
        # nowhere buildable this round (blocked on all sides) -- keep walking, retry next round
        self._walk_east(ct, pos)

    def _publish(self, ct: Controller) -> None:
        ct.write_store(STORE_PROBE_X, self.built_pos.x)
        ct.write_store(STORE_PROBE_Y, self.built_pos.y)
        ct.write_store(STORE_PROBE_ID, self.built_id)
        ct.write_store(STORE_PROBE_READY, 1)

    def _walk_east(self, ct: Controller, pos: Position) -> None:
        if ct.can_move(Direction.EAST) and ct.get_tile_env(pos.add(Direction.EAST)) != Environment.WALL:
            ct.move(Direction.EAST)
            return
        open_dirs = [d for d in CARDINALS if ct.can_move(d) and ct.get_tile_env(pos.add(d)) == Environment.EMPTY]
        move_options = open_dirs or [d for d in CARDINALS if ct.can_move(d)]
        if move_options:
            ct.move(random.choice(move_options))
