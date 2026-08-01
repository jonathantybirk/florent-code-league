"""Core opening: buy Builders while the titanium buys more than it costs."""

from fcode import Controller, Direction, Environment, Position

from atlas import identify_visible

from constants import (AMMO_FLOOR, AMMO_TARGET, ECONOMY_BUILDERS,
                       RUSH_DISTANCE, RUSH_ECONOMY_BUILDERS,
                       EMERGENCY_RESERVE,
                       HOME_ALARM_PERCENT, RICH_RESERVE,
                       SLOT_HOME_UNDER_FIRE)

CARDINALS = (Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST)

# Every Builder adds 20% to the shared cost scale, which taxes every later
# Conveyor, Gunner and Harvester alike. Four Builders already put a Gunner at
# 18 Ti; a fifth would buy less siege than it costs.
MAX_BUILDERS = 4
EMERGENCY_BUILDERS = 14
RICH_BUILDERS = 8


def run(player, ct: Controller) -> None:
    _keep_ammunition(ct)
    if not hasattr(player, "spawned"):
        player.spawned = 0
        player.alarm = False
        anchor = ct.get_position()
        ores = [tile for tile in ct.get_nearby_tiles()
                if ct.get_tile_env(tile) == Environment.ORE_TITANIUM]
        ores.sort(key=lambda t: (t.distance_squared(anchor), t.x, t.y))
        player.opening_ores = ores

    # A scratch is not an emergency; sustained fire is. Publishing the alarm
    # only past a real threshold keeps a single stray shot from recalling the
    # whole assault.
    # Hysteresis, and it must clear. Raise the alarm below the threshold, drop
    # it only once the repair crew has healed the Core all the way back. A
    # latch that never clears converts every attacker into an economy Builder
    # for the rest of the match after a single early scratch -- which is
    # exactly how a mirror match ends 1000-round scoreless.
    healthy = ct.get_hp() >= ct.get_max_hp()
    if ct.get_hp() * 100 < ct.get_max_hp() * HOME_ALARM_PERCENT:
        player.alarm = True
    elif healthy:
        player.alarm = False
    hurt = getattr(player, "alarm", False)
    ct.write_store(SLOT_HOME_UNDER_FIRE, 1 if hurt else 0)
    # Under fire the cap lifts hard: healing costs a flat 1 Ti and is not
    # touched by the cost scale, so with a deep bank every extra Builder is
    # another 4 HP a round against a Gunner's 5. Losing on a full treasury is
    # the worst possible way to lose.
    # Idle titanium is the most expensive thing on the board. The Builder cap
    # exists to protect the shared cost scale while every Ti is spoken for; once
    # the bank is deep the scale is cheaper than the standing still.
    cap = MAX_BUILDERS
    bank = ct.get_global_resources()
    if bank > RICH_RESERVE:
        cap = RICH_BUILDERS
    if hurt and bank > EMERGENCY_RESERVE:
        cap = EMERGENCY_BUILDERS
    if player.spawned >= cap:
        return
    cost = ct.get_builder_bot_cost()
    economy = _opening_economy(player, ct)
    reserve = 0 if player.spawned < economy else 60
    if ct.get_global_resources() < cost + reserve:
        return

    role = player.spawned
    if role < economy and role < len(player.opening_ores):
        goal = player.opening_ores[role]
    else:
        goal = _away_from_home(ct)

    candidates = [tile for tile in ct.get_nearby_tiles(2) if ct.can_spawn(tile)]
    if not candidates:
        return
    candidates.sort(key=lambda t: (t.distance_squared(goal), t.x, t.y))
    ct.spawn_builder(candidates[0])
    player.spawned += 1


def _keep_ammunition(ct: Controller) -> None:
    """Turn titanium into ammunition, or no turret we own can fire at all.

    Engine 2.3.3 replaced 2.2.0's per-turret ammunition with a global pool the
    Core fills by conversion: 1 titanium for 1 ammunition, at most once per
    team per turn, no action cooldown, usable the same turn.
    """
    try:
        held = ct.get_global_ammo()
        if held >= AMMO_TARGET:
            return
        amount = min(AMMO_TARGET - held, ct.get_global_resources() - AMMO_FLOOR)
        if amount > 0 and ct.can_convert_ammo(amount):
            ct.convert_ammo(amount)
    except Exception:  # noqa: BLE001 - never let this kill the Core
        return


def _away_from_home(ct: Controller) -> Position:
    """Head for the far corner; the Builder refines this once it can see."""
    anchor = ct.get_position()
    return Position(ct.get_map_width() - 2 - anchor.x,
                    ct.get_map_height() - 2 - anchor.y)

def _opening_economy(player, ct) -> int:
    """Split the opening Builders using the real distance between Cores.

    The fair bot has to guess this: it cannot know how far away the enemy is
    until it has walked there, so it commits to one opening for every map. The
    atlas removes the guess. A short map rewards Mistral's answer -- put almost
    everything into pressure, because the Gunners arrive before any economy
    could have repaid itself -- and a long map rewards ours, because there is
    time to mine and the walk is dead rounds either way.

    Measured once, at spawn, and cached: this is a full-map BFS and the Core
    has the same 10ms budget as anything else.
    """
    cached = getattr(player, "econ_builders", None)
    if cached is not None:
        return cached
    player.econ_builders = ECONOMY_BUILDERS
    try:
        anchor = ct.get_position()
        atlas = identify_visible(ct, (anchor.x, anchor.y))
        if atlas is None:
            return player.econ_builders
        goal = atlas.enemy_core
        seen = {(anchor.x, anchor.y)}
        frontier = [(anchor.x, anchor.y)]
        steps = 0
        while frontier and steps < atlas.width * atlas.height:
            nxt = []
            for x, y in frontier:
                if abs(x - goal[0]) <= 1 and abs(y - goal[1]) <= 1:
                    player.econ_builders = (RUSH_ECONOMY_BUILDERS
                                            if steps <= RUSH_DISTANCE
                                            else ECONOMY_BUILDERS)
                    return player.econ_builders
                # Builders are cardinal-only in 2.3.3, so this is the honest
                # number of rounds the walk actually takes.
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    tile = (x + dx, y + dy)
                    if tile in seen or tile in atlas.walls:
                        continue
                    if not (0 <= tile[0] < atlas.width
                            and 0 <= tile[1] < atlas.height):
                        continue
                    seen.add(tile)
                    nxt.append(tile)
            frontier = nxt
            steps += 1
    except Exception:  # noqa: BLE001 - a dead Core loses the match outright
        pass
    return player.econ_builders
