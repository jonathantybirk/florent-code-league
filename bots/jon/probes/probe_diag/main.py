import sys
from fcode import Controller, Direction, EntityType

DIAG = [Direction.NORTHEAST, Direction.SOUTHEAST, Direction.SOUTHWEST, Direction.NORTHWEST]


def log(*a):
    print(*a, file=sys.stderr, flush=True)


class Player:
    def __init__(self):
        self.n = 0

    def run(self, ct: Controller) -> None:
        if ct.get_team().value != "a":
            return
        r = ct.get_current_round()
        if ct.get_entity_type() == EntityType.CORE:
            if r == 0:
                for p in ct.get_nearby_tiles(2):
                    if ct.can_spawn(p):
                        ct.spawn_builder(p)
                        break
            return
        if r > 8:
            return
        pos = ct.get_position()
        log(f"r={r} pos={tuple(pos)} can_move_diag="
            f"{[d.value for d in DIAG if ct.can_move(d)]} mcd={ct.get_move_cooldown()}")
        for d in DIAG:
            if ct.can_move(d):
                ct.move(d)
                log(f"  moved {d.value} -> {tuple(ct.get_position())}")
                break
