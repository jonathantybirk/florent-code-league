"""TARGET half of bots/test/builder_combat_probe -- see that directory's
main.py module docstring for the full experiment design. This bot is
deliberately passive: it never fights back and never flees, so any HP
change observed by ATTACKER can only be attributed to ATTACKER's own
Attack calls.

Behaviour: stand still on empty ground until an enemy Builder Bot has been
orthogonally adjacent for PHASE1_ROUNDS_BEFORE_TRANSITION rounds (Phase 1:
"bare ground" data collection for ATTACKER), then build one Conveyor on a
tile away from the enemy, step onto it (Conveyor tiles are Builder-Bot-
passable), and stand there forever (Phase 2: "on a building" data
collection). Never resigns -- ATTACKER's Core is the one that reports the
result and forfeits the match.
"""

from __future__ import annotations

from fcode import Controller, Direction, Environment, EntityType, Position

CARDINALS = [Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST]

PHASE1_ROUNDS_BEFORE_TRANSITION = 5  # keep in sync with the ATTACKER's own constant


def in_bounds(ct: Controller, pos: Position) -> bool:
    return 0 <= pos.x < ct.get_map_width() and 0 <= pos.y < ct.get_map_height()


class Player:
    def __init__(self):
        self.adjacent_enemy_rounds = 0
        self.conveyor_pos: Position | None = None
        self.relocated = False

    def run(self, ct: Controller) -> None:
        etype = ct.get_entity_type()
        if etype == EntityType.CORE:
            self._run_core(ct)
        elif etype == EntityType.BUILDER_BOT:
            self._run_builder(ct)

    def _run_core(self, ct: Controller) -> None:
        if ct.get_unit_count() < 2:
            for pos in ct.get_nearby_tiles(dist_sq=2):
                if ct.can_spawn(pos):
                    ct.spawn_builder(pos)
                    break

    def _run_builder(self, ct: Controller) -> None:
        if self.relocated:
            return  # sit still forever once on the Conveyor -- Phase 2 is running

        pos = ct.get_position()

        if self.conveyor_pos is not None:
            if pos == self.conveyor_pos:
                self.relocated = True
                return
            d = pos.cardinal_direction_to(self.conveyor_pos)
            if ct.can_move(d):
                ct.move(d)
            return

        enemy_pos = self._adjacent_enemy_pos(ct, pos)
        if enemy_pos is not None:
            self.adjacent_enemy_rounds += 1
        # else: don't reset the counter on a single missed round (the
        # ATTACKER may be mid-step re-approaching) -- only forward progress
        # matters for triggering the transition.

        if self.adjacent_enemy_rounds >= PHASE1_ROUNDS_BEFORE_TRANSITION:
            self._try_build_conveyor_away_from(ct, pos, enemy_pos)
        # else: stand still -- Phase 1's whole point is bare ground under us.

    def _adjacent_enemy_pos(self, ct: Controller, pos: Position) -> Position | None:
        my_team = ct.get_team()
        for d in CARDINALS:
            tile = pos.add(d)
            if not in_bounds(ct, tile):
                continue
            bid = ct.get_tile_builder_bot_id(tile)
            if bid is not None and ct.get_team(bid) != my_team:
                return tile
        return None

    def _try_build_conveyor_away_from(self, ct: Controller, pos: Position, avoid: Position | None) -> None:
        for d in CARDINALS:
            tile = pos.add(d)
            if not in_bounds(ct, tile) or tile == avoid:
                continue
            if ct.get_tile_env(tile) == Environment.EMPTY and ct.can_build_conveyor(tile, d):
                ct.build_conveyor(tile, d)
                self.conveyor_pos = tile
                return
