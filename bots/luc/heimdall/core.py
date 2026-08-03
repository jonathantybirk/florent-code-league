"""Core opening, doctrine choice, and reinforcement spawning."""

import sys
from typing import TYPE_CHECKING

import doctrine
from fcode import Controller, Direction, Environment, Position

from constants import (MAX_OPENING_BUILDERS, PAD_FIRST_ORDER,
                       SLOT_BUILDER_HEARTBEAT,
                       SLOT_CORE_DAMAGED, SLOT_OWN_CORE)
from utils import pack_core

if TYPE_CHECKING:
    from main import Player


CARDINALS = (Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST)

# Surplus titanium no longer becomes extra Builders. Each one adds +20% to
# every future build cost, so spending a healthy bank on Builders is the most
# expensive way there is to convert titanium into nothing: it drained the
# opening 380 Ti to 18 by round 7 and tripled the price of the defence it was
# meant to build. Reinforcements now mean replacing a dead Builder, nothing
# more; surplus goes into Launchers and Harvesters instead.
MIN_TITANIUM_RESERVE = 60
AMMO_TARGET = 120
# Below this much ammunition the team is effectively disarmed: no turret can
# fire, and MIN_AMMO_FOR_GUNNER gates every Builder turret-building path.
# Refilling to here outranks the construction reserve, which otherwise left
# the pool pinned at 0-1 for whole matches.
COMBAT_AMMO_FLOOR = 80
# The only titanium held back while restoring that floor.
EMERGENCY_RESERVE = 10
# The alarm escalates: 1 recalls the economy Builder to defend, 2 additionally
# pulls the ring Builder onto healing duty. Healing restores 4 HP for a flat
# 1 Ti regardless of scale, so two menders out-heal a Gunner's 10 dmg/round
# and fully cancel a Sentinel's 6 -- defence is titanium-positive.
CRITICAL_HP = 300


def run(player: "Player", ct: Controller) -> None:
    """Run the opening, then keep spawning attackers from surplus titanium."""
    _keep_ammunition(ct)
    if not hasattr(player, "repair_alert"):
        player.repair_alert = False
    hp, max_hp = ct.get_hp(ct.get_id()), ct.get_max_hp(ct.get_id())
    if hp <= max_hp - 50:
        player.repair_alert = True
    elif hp == max_hp:
        player.repair_alert = False
    if not hasattr(player, "builders_spawned"):
        player.builders_spawned = 0
        core = ct.get_position()
        player.doctrine = doctrine.classify(ct)
        print(f"DOCTRINE round={ct.get_current_round()} "
              f"map={ct.get_map_width()}x{ct.get_map_height()} "
              f"core={tuple(core)} choice={doctrine.NAMES[player.doctrine]}",
              file=sys.stderr, flush=True)
        ores = [tile for tile in ct.get_nearby_tiles()
                if ct.get_tile_env(tile) == Environment.ORE_TITANIUM
                and ct.get_tile_building_id(tile) is None]
        ores.sort(key=lambda tile: (tile.distance_squared(core), tile.x, tile.y))
        player.opening_ore_targets = ores
    ct.write_store(SLOT_OWN_CORE,
                   pack_core(ct.get_position(), player.doctrine))
    alarm = int(player.repair_alert)
    if player.repair_alert and hp <= CRITICAL_HP:
        alarm = 2
    ct.write_store(SLOT_CORE_DAMAGED, alarm)

    economy_builders = doctrine.economy_builders(player.doctrine)
    role = player.builders_spawned
    resources = ct.get_global_resources()
    builder_cost = ct.get_builder_bot_cost()
    if resources < builder_cost:
        return
    has_live_builder = (
        ct.read_store(SLOT_BUILDER_HEARTBEAT) >= ct.get_current_round()
    )
    if role >= MAX_OPENING_BUILDERS and has_live_builder:
        return

    # Spawn order has to agree with the role order the Builders assign
    # themselves in builder.py, or a Builder spawns at the wrong end of the
    # map for the job it is about to pick up. Under PAD_FIRST_ORDER that order
    # is pad, then attackers, then miners; the pad and the attackers all want
    # the enemy-facing side of the spawn ring, and only the miners want ore.
    if PAD_FIRST_ORDER:
        mining_role = role - (doctrine.launcher_builders(player.doctrine)
                              + doctrine.attack_builders(player.doctrine))
    else:
        mining_role = role if role < economy_builders else -1
    if 0 <= mining_role < min(economy_builders,
                             len(player.opening_ore_targets)):
        target = player.opening_ore_targets[mining_role]
        goals = [target.add(direction) for direction in CARDINALS
                 if _on_map(ct, target.add(direction))]
    else:
        target = _scout_target(ct, max(0, role - economy_builders))
        goals = [target]

    candidates = [tile for tile in ct.get_nearby_tiles(2) if ct.can_spawn(tile)]
    candidates.sort(key=lambda tile: (
        min(_chebyshev(tile, goal) for goal in goals),
        tile.distance_squared(target),
        tile.x,
        tile.y,
    ))
    if candidates:
        ct.spawn_builder(candidates[0])
        player.builders_spawned += 1


def _scout_target(ct: Controller, index: int) -> Position:
    """Split symmetry candidates when visible ore jobs run out.

    Farthest candidate first: a two-player map is built to be fair, so the
    Cores are placed as far apart as the symmetry allows. Measured on the
    published pool the farthest of the three candidates is the true enemy
    Core on 28 of 42 map-sides against 4 of 42 for nearest-first.
    """
    core = ct.get_position()
    candidates = [
        Position(ct.get_map_width() - 2 - core.x,
                 ct.get_map_height() - 2 - core.y),
        Position(ct.get_map_width() - 2 - core.x, core.y),
        Position(core.x, ct.get_map_height() - 2 - core.y),
    ]
    unique = []
    for candidate in candidates:
        if candidate not in unique:
            unique.append(candidate)
    unique.sort(key=lambda c: -core.distance_squared(c))
    return unique[index % len(unique)]


def _chebyshev(a: Position, b: Position) -> int:
    return max(abs(a.x - b.x), abs(a.y - b.y))


def _on_map(ct: Controller, position: Position) -> bool:
    return 0 <= position.x < ct.get_map_width() and 0 <= position.y < ct.get_map_height()


def _keep_ammunition(ct) -> None:
    """Turn titanium into ammunition, or no turret we own can fire at all.

    Engine 2.3.3 replaced 2.2.0's per-turret ammunition with a global pool the
    Core fills by conversion: 1 titanium for 1 ammunition, at most once per
    team per turn, no action cooldown, usable the same turn.
    """
    try:
        held = ct.get_global_ammo()
        if held >= AMMO_TARGET:
            return
        # Scaled Harvester and Launcher costs can exceed the old fixed 60-Ti
        # reserve. Converting down to 60 made waiting Builders permanently
        # unaffordable even while the replay showed 80 Ti between rounds.
        construction_reserve = max(
            MIN_TITANIUM_RESERVE,
            ct.get_harvester_cost(),
            ct.get_launcher_cost(),
        )
        amount = min(
            AMMO_TARGET - held,
            ct.get_global_resources() - construction_reserve,
        )
        if held < COMBAT_AMMO_FLOOR:
            amount = max(amount, min(
                COMBAT_AMMO_FLOOR - held,
                ct.get_global_resources() - EMERGENCY_RESERVE,
            ))
        if amount > 0 and ct.can_convert_ammo(amount):
            ct.convert_ammo(amount)
    except Exception as error:  # noqa: BLE001 - never let this kill the Core
        print(
            f"PLAN_FAILED id={ct.get_id()} round={ct.get_current_round()} "
            f"action=convert ammunition reason={type(error).__name__}: {error}"
        )
        return
