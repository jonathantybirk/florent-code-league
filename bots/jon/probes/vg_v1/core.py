"""Core opening: buy Builders while the titanium buys more than it costs."""

from fcode import Controller, Direction, Environment, Position

from constants import (ECONOMY_BUILDERS, EMERGENCY_RESERVE,
                       HOME_ALARM_PERCENT, SLOT_HOME_UNDER_FIRE)

CARDINALS = (Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST)

# Every Builder adds 20% to the shared cost scale, which taxes every later
# Conveyor, Gunner and Harvester alike. Four Builders already put a Gunner at
# 18 Ti; a fifth would buy less siege than it costs.
MAX_BUILDERS = 4
EMERGENCY_BUILDERS = 14


def run(player, ct: Controller) -> None:
    if not hasattr(player, "spawned"):
        player.spawned = 0
        anchor = ct.get_position()
        ores = [tile for tile in ct.get_nearby_tiles()
                if ct.get_tile_env(tile) == Environment.ORE_TITANIUM]
        ores.sort(key=lambda t: (t.distance_squared(anchor), t.x, t.y))
        player.opening_ores = ores

    # A scratch is not an emergency; sustained fire is. Publishing the alarm
    # only past a real threshold keeps a single stray shot from recalling the
    # whole assault.
    hurt = ct.get_hp() * 100 < ct.get_max_hp() * HOME_ALARM_PERCENT
    if hurt:
        ct.write_store(SLOT_HOME_UNDER_FIRE, 1)
    # Under fire the cap lifts hard: healing costs a flat 1 Ti and is not
    # touched by the cost scale, so with a deep bank every extra Builder is
    # another 4 HP a round against a Gunner's 5. Losing on a full treasury is
    # the worst possible way to lose.
    cap = MAX_BUILDERS
    if hurt and ct.get_global_resources() > EMERGENCY_RESERVE:
        cap = EMERGENCY_BUILDERS
    if player.spawned >= cap:
        return
    cost = ct.get_builder_bot_cost()
    reserve = 0 if player.spawned < ECONOMY_BUILDERS else 60
    if ct.get_global_resources() < cost + reserve:
        return

    role = player.spawned
    if role < ECONOMY_BUILDERS and role < len(player.opening_ores):
        goal = player.opening_ores[role]
    else:
        goal = _away_from_home(ct)

    candidates = [tile for tile in ct.get_nearby_tiles(2) if ct.can_spawn(tile)]
    if not candidates:
        return
    candidates.sort(key=lambda t: (t.distance_squared(goal), t.x, t.y))
    ct.spawn_builder(candidates[0])
    player.spawned += 1


def _away_from_home(ct: Controller) -> Position:
    """Head for the far corner; the Builder refines this once it can see."""
    anchor = ct.get_position()
    return Position(ct.get_map_width() - 2 - anchor.x,
                    ct.get_map_height() - 2 - anchor.y)
