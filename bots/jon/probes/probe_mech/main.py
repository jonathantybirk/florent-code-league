"""Probe: dump raw engine mechanics to stderr. Not a competitive bot."""
import sys

from fcode import Controller, Direction, Environment, EntityType, Position

CARD = [Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST]


def log(*a):
    print(*a, file=sys.stderr, flush=True)


class Player:
    def __init__(self):
        self.tick = 0
        self.dumped = False
        self.bot_log = {}

    def run(self, ct: Controller) -> None:
        if ct.get_team().value != "a":
            return
        et = ct.get_entity_type()
        r = ct.get_current_round()
        if et == EntityType.CORE:
            self.core(ct, r)
        elif et == EntityType.BUILDER_BOT:
            self.builder(ct, r)

    def core(self, ct, r):
        if not self.dumped:
            self.dumped = True
            w, h = ct.get_map_width(), ct.get_map_height()
            log(f"MAP {w}x{h} core_pos={tuple(ct.get_position())} core_id={ct.get_id()}")
            log(f"COSTS r1 scale={ct.get_scale_percent()} conv={ct.get_conveyor_cost()} "
                f"harv={ct.get_harvester_cost()} bot={ct.get_builder_bot_cost()} "
                f"split={ct.get_splitter_cost()} gun={ct.get_gunner_cost()}")
            log(f"SPAWNABLE {[tuple(p) for p in ct.get_nearby_tiles(2) if ct.can_spawn(p)]}")
            log(f"RES r1 = {ct.get_global_resources()}")

        # Spawn exactly one builder at round 1, then observe cooldown.
        if r <= 6:
            log(f"CORE r={r} acd={ct.get_action_cooldown()} res={ct.get_global_resources()} "
                f"scale={ct.get_scale_percent():.4f} botcost={ct.get_builder_bot_cost()} "
                f"units={ct.get_unit_count()}")
        if r == 1:
            for p in ct.get_nearby_tiles(2):
                if ct.can_spawn(p):
                    ct.spawn_builder(p)
                    log(f"CORE spawned at {tuple(p)} r={r}")
                    break
        # passive income tracking
        if r <= 20:
            log(f"INCOME r={r} res={ct.get_global_resources()}")

    def builder(self, ct, r):
        bid = ct.get_id()
        st = self.bot_log.setdefault(bid, {"phase": 0})
        pos = ct.get_position()
        if st["phase"] == 0:
            st["phase"] = 1
            st["spawn_round"] = r
            log(f"BOT {bid} first_run round={r} pos={tuple(pos)} "
                f"acd={ct.get_action_cooldown()} mcd={ct.get_move_cooldown()} "
                f"vision={ct.get_vision_radius_sq()}")
            # Which tiles can I build a conveyor on? (tests diagonal + own tile)
            cands = []
            for p in ct.get_nearby_tiles(2):
                if ct.can_build_conveyor(p, Direction.NORTH):
                    cands.append((tuple(p), pos.distance_squared(p)))
            log(f"BOT {bid} conveyor-buildable in r2<=2: {sorted(cands, key=lambda x: x[1])}")
            log(f"BOT {bid} own tile buildable = {ct.can_build_conveyor(pos, Direction.NORTH)}")
            log(f"BOT {bid} barrier-buildable: "
                f"{[tuple(p) for p in ct.get_nearby_tiles(2) if ct.can_build_barrier(p)]}")

        # TEST: build then move in same round
        if r == st["spawn_round"] + 1:
            built = False
            for d in CARD:
                p = pos.add(d)
                if ct.can_build_barrier(p):
                    ct.build_barrier(p)
                    built = True
                    log(f"BOT {bid} r={r} built barrier at {tuple(p)}; "
                        f"acd_now={ct.get_action_cooldown()} mcd_now={ct.get_move_cooldown()}")
                    break
            if built:
                moved = [d.value for d in CARD if ct.can_move(d)]
                log(f"BOT {bid} r={r} AFTER BUILD can_move -> {moved}")
                if moved:
                    for d in CARD:
                        if ct.can_move(d):
                            ct.move(d)
                            log(f"BOT {bid} r={r} MOVED AFTER BUILD to {tuple(ct.get_position())} "
                                f"acd={ct.get_action_cooldown()} mcd={ct.get_move_cooldown()}")
                            break
        elif r == st["spawn_round"] + 2:
            log(f"BOT {bid} r={r} pos={tuple(pos)} acd={ct.get_action_cooldown()} "
                f"mcd={ct.get_move_cooldown()}")
