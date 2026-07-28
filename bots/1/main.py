"""Bot 1 — internal map representation, entity logic split per type.

Each unit builds and maintains its own view of the map (static terrain plus
last-seen occupancy) by calling update_map() every round, then dispatches to
the entity-specific mixin (core, builder, gunner) for the rest of its turn.
"""

from fcode import Controller, EntityType, Position

from entities.builder import BuilderMixin
from entities.core import CoreMixin
from entities.gunner import GunnerMixin
from utils.map import MapMatchState, TileState, update_map


class Player(CoreMixin, BuilderMixin, GunnerMixin):
    def __init__(self):
        self.map: dict[Position, TileState] = {}
        self.map_match_state = MapMatchState()

    def run(self, ct: Controller) -> None:
        update_map(ct, self.map, self.map_match_state)

        etype = ct.get_entity_type()
        if etype == EntityType.CORE:
            self.run_core(ct)
        elif etype == EntityType.BUILDER_BOT:
            self.run_builder(ct)
        elif etype == EntityType.GUNNER:
            self.run_gunner(ct)
