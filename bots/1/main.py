"""Bot 1 — internal map representation only.

Each unit builds and maintains its own view of the map (static terrain plus
last-seen occupancy) by calling update_map() every round. This bot does not
act on that information yet — it's a base for building map-aware strategy on
top of.
"""

from fcode import Controller, Position

from utils.map import MapMatchState, TileState, update_map


class Player:
    def __init__(self):
        self.map: dict[Position, TileState] = {}
        self.map_match_state = MapMatchState()

    def run(self, ct: Controller) -> None:
        update_map(ct, self.map, self.map_match_state)
