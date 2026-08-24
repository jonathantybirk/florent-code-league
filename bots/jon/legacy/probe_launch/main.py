"""Probe: can a Launcher throw an ENEMY Builder?"""
import sys
from fcode import Controller, EntityType, Direction, Position

D8 = [d for d in Direction if d != Direction.CENTRE]


def log(*a):
    print(*a, file=sys.stderr, flush=True)


def safe(fn, *a):
    try:
        return fn(*a)
    except Exception as e:  # noqa
        return f"<{type(e).__name__}>"


class Player:
    def __init__(self):
        self.said = 0

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception as e:  # noqa
            log("ERR", type(e).__name__, e)

    def _run(self, ct):
        t = ct.get_entity_type()
        r = ct.get_current_round()
        if t == EntityType.CORE:
            if r < 4:
                for tile in ct.get_nearby_tiles(2):
                    if ct.can_spawn(tile):
                        ct.spawn_builder(tile)
                        return
        elif t == EntityType.BUILDER_BOT:
            me = ct.get_position()
            mine = ct.get_team()
            foes = [ct.get_position(u) for u in ct.get_nearby_units()
                    if ct.get_team(u) != mine]
            # Plant a Launcher right beside any enemy Builder we can reach.
            for foe in foes:
                for d in D8:
                    spot = foe.add(d)
                    if spot.distance_squared(me) <= 2 and ct.can_build_launcher(spot):
                        ct.build_launcher(spot)
                        log(f"r{r} launcher at {tuple(spot)} beside foe {tuple(foe)}")
                        return
            target = foes[0] if foes else Position(ct.get_map_width() - 1 - me.x,
                                                   ct.get_map_height() - 1 - me.y)
            best = None
            for d in D8:
                if not ct.can_move(d):
                    continue
                score = me.add(d).distance_squared(target)
                if best is None or score < best[0]:
                    best = (score, d)
            if best:
                ct.move(best[1])
        elif t == EntityType.LAUNCHER:
            mine = ct.get_team()
            for unit in ct.get_nearby_units(2):
                if ct.get_team(unit) == mine:
                    continue
                pos = ct.get_position(unit)
                hits = [p for p in ct.get_nearby_tiles(26)
                        if safe(ct.can_launch, pos, p) is True]
                log(f"r{r} ADJACENT enemy builder at {tuple(pos)} "
                    f"d2={pos.distance_squared(ct.get_position())} "
                    f"legal_targets={len(hits)}")
                if hits:
                    far = max(hits, key=lambda p: p.distance_squared(pos))
                    log(f"r{r} *** THREW ENEMY BUILDER {tuple(pos)} -> {tuple(far)}")
                    ct.launch(pos, far)
                return
