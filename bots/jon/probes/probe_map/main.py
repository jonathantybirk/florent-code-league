import sys
from fcode import Controller, EntityType, Environment


class Player:
    def __init__(self):
        self.done = False

    def run(self, ct: Controller) -> None:
        if self.done or ct.get_entity_type() != EntityType.CORE:
            return
        self.done = True
        w, h = ct.get_map_width(), ct.get_map_height()
        print(f"CORE team={ct.get_team().value} pos={tuple(ct.get_position())} map={w}x{h}",
              file=sys.stderr, flush=True)
        ct.resign()
