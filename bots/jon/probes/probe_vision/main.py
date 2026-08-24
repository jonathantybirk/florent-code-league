import sys
from fcode import Controller, EntityType, Environment, Position


def log(*a):
    print(*a, file=sys.stderr, flush=True)


class Player:
    def __init__(self):
        self.done = False

    def run(self, ct: Controller) -> None:
        if ct.get_team().value != "a" or self.done:
            return
        if ct.get_entity_type() != EntityType.CORE:
            return
        self.done = True
        w, h = ct.get_map_width(), ct.get_map_height()
        me = ct.get_position()
        log(f"core={tuple(me)} map={w}x{h} vision_sq={ct.get_vision_radius_sq()}")
        log(f"n nearby_tiles(default)={len(ct.get_nearby_tiles())}")
        # Can we sense a far-away tile at all?
        far = Position(w - 3, h - 3)
        log(f"far={tuple(far)} in_vision={ct.is_in_vision(far)}")
        for label, p in [("far", far), ("mid", Position(me.x + 8, me.y)), ("near", Position(me.x + 3, me.y))]:
            try:
                log(f"  get_tile_env({label} {tuple(p)}) = {ct.get_tile_env(p)} "
                    f"in_vision={ct.is_in_vision(p)}")
            except Exception as e:
                log(f"  get_tile_env({label} {tuple(p)}) RAISED {type(e).__name__}: {e}")
            try:
                log(f"  get_tile_building_id({label}) = {ct.get_tile_building_id(p)}")
            except Exception as e:
                log(f"  get_tile_building_id({label}) RAISED {type(e).__name__}: {e}")
        try:
            ct.get_nearby_tiles(200)
        except Exception as e:
            log(f"  get_nearby_tiles(200) RAISED {type(e).__name__}: {e}")
        ct.resign()
