"""Sentinel behaviour: kill the attack, break the Core, else eat the economy.

A Sentinel's shot is never blocked -- walls, buildings, and bodies are all
transparent to it -- so an aligned Sentinel kills what it is pointed at on a
fixed clock no matter what the defender builds in between.

The target order is the whole of this file, and it is set by three pieces of
2.3.4 arithmetic rather than by preference:

* A Builder Bot restores 4 HP for a flat 1 Ti, unaffected by cost scale. One
  mender standing on a Core therefore cancels two thirds of a Sentinel's 6
  damage a round and two menders outlast a two-Sentinel battery outright.
  Defence is roughly 2.2x more titanium-efficient than offence, so the mender
  outranks the thing it is mending.
* A Core is 500 HP. Against no menders a battery of two takes 42 rounds;
  against two menders it takes forever. Firing into a Core whose HP is not
  falling is 10 ammunition a shot spent on nothing.
* Most games therefore reach round 1000, and the tiebreak order is titanium
  collected, then live Harvesters, then titanium stored. In a game decided that
  way the enemy's Harvesters and conveyor trunk *are* the win condition, and
  they are 30 and 20 HP -- two shots each.

The last of those is the one this lineage has never used. `get_nearby_entities`
returns units, and conveyors, harvesters and barriers are buildings, so every
Sentinel we have ever built has been blind to the enemy economy and has simply
held its fire when no unit was on the line.
"""

from typing import TYPE_CHECKING

from fcode import Controller, EntityType, GameError, Position

from constants import (SIEGE_STALL_ROUNDS, SLOT_ENEMY_CORE,
                       STARVE_THE_ECONOMY)
from utils import unpack_enemy

if TYPE_CHECKING:
    from main import Player


# A Builder Bot this close is worth the shot ahead of anything else, at either
# end of the map. Builder vision is r^2=20, so this is "close enough to be
# doing something to us, or to the Core we are shooting".
BUILDER_PRIORITY_RADIUS_SQ = 16

# Which enemy building is worth 10 ammunition, best first.
#
# Harvester before conveyor: it is 30 HP against 20, but it is 20 Ti against 3
# to replace and it is the *source*. Killing one stops 2.5 Ti a round until
# they walk a Builder back to the ore and rebuild it, and a Harvester is also
# the second tiebreak criterion outright.
#
# Splitter before conveyor for the same reason at 6 Ti against 3, and because a
# splitter is a junction: the lines below it all stop.
#
# Turrets last. They are 25 and 40 HP, they cost us three or four shots, and a
# turret we destroy hands them back its +20% of cost scale -- we would be
# paying 30-40 Ti of ammunition to make everything they build cheaper.
BUILDING_VALUE = {
    EntityType.HARVESTER: 0,
    EntityType.SPLITTER: 1,
    EntityType.CONVEYOR: 2,
    EntityType.BARRIER: 3,
}


def run(player: "Player", ct: Controller) -> None:
    try:
        _run(player, ct)
    except GameError as error:
        print(
            f"PLAN_FAILED id={ct.get_id()} round={ct.get_current_round()} "
            f"action=sentinel run reason=GameError: {error}"
        )
        return


def _run(player: "Player", ct: Controller) -> None:
    if not hasattr(player, "core_hp"):
        player.core_hp = None
        player.core_stalled = 0
    team = ct.get_team()
    here = ct.get_position()
    enemies = [entity_id for entity_id in ct.get_nearby_entities()
               if ct.get_team(entity_id) != team
               and ct.can_fire(ct.get_position(entity_id))]
    # 1. Builder Bots, at both ends of the map and for the same reason.
    #
    # Defending, the intruder emplacing at our Core is the whole enemy attack:
    # their Core will not spawn a replacement while their other Builders still
    # answer the heartbeat, so a Builder killed on our doorstep is an attack
    # that does not come back. 40 HP is three shots.
    #
    # Besieging, it is the mender arithmetic above. Shooting a Core past a
    # mender is paying 10 ammunition a shot to lose slowly; shooting the mender
    # ends it.
    builders = [entity_id for entity_id in enemies
                if ct.get_entity_type(entity_id) is EntityType.BUILDER_BOT
                and ct.get_position(entity_id).distance_squared(here)
                <= BUILDER_PRIORITY_RADIUS_SQ]
    if builders:
        ct.fire(ct.get_position(min(builders, key=ct.get_hp)))
        return
    # 2. The Core, for as long as firing at it is actually moving its HP.
    if _fire_at_core(player, ct):
        return
    # 3. The economy, which is what the round-1000 tiebreak is made of.
    if STARVE_THE_ECONOMY and _fire_at_economy(ct, team):
        return
    # 4. Anything else on the line.
    if enemies:
        ct.fire(ct.get_position(min(enemies, key=ct.get_hp)))


def _fire_at_core(player: "Player", ct: Controller) -> bool:
    """Shoot the enemy Core, and notice when that has stopped working.

    Vision is not required for a legal shot, only range and alignment, so the
    store's remembered position is enough to fire. Reading the Core's HP does
    need vision -- a Sentinel's is r^2=32, the same as its reach, so a seat that
    can shoot the Core can almost always also watch it.

    The stall counter is the mender arithmetic made operational. Two Builders
    healing restore 8 HP a round against a two-Sentinel battery's 12, and one
    restores 4 against a single Sentinel's 6, so a besieged Core whose HP has
    stopped falling is not slow, it is being held -- and every further shot is
    10 ammunition into a Core that will be full again before we return to it.
    """
    packed = ct.read_store(SLOT_ENEMY_CORE)
    if not packed:
        return False
    core, _ = unpack_enemy(packed)
    if core is None:
        return False
    for dx in (0, 1):
        for dy in (0, 1):
            tile = Position(core[0] + dx, core[1] + dy)
            if not ct.can_fire(tile):
                continue
            if STARVE_THE_ECONOMY and ct.is_in_vision(tile):
                core_id = ct.get_tile_building_id(tile)
                if core_id is not None:
                    hp = ct.get_hp(core_id)
                    if player.core_hp is not None and hp >= player.core_hp:
                        player.core_stalled += 1
                    else:
                        player.core_stalled = 0
                    player.core_hp = hp
                    if player.core_stalled >= SIEGE_STALL_ROUNDS:
                        return False
            ct.fire(tile)
            return True
    return False


def _fire_at_economy(ct: Controller, team) -> bool:
    """Break the enemy's supply line, which is what the tiebreak is made of.

    Buildings are not units, so they never appear in `get_nearby_entities` and
    every Sentinel this lineage has built has been blind to them. A Harvester
    is 30 HP and a conveyor 20 -- two shots each -- and a hole anywhere in a
    trunk leaves every Harvester upstream of it mining into a dead end. The
    3 Ti they pay to patch it is not the cost we are imposing; the cost is the
    Builder turns and the rounds of stopped income, and this bot knows exactly
    how expensive that is because REPAIR_ATTEMPT_LIMIT exists to stop it
    happening to us.
    """
    best = None
    for building_id in ct.get_nearby_buildings():
        if ct.get_team(building_id) == team:
            continue
        value = BUILDING_VALUE.get(ct.get_entity_type(building_id))
        if value is None:
            continue
        spot = ct.get_position(building_id)
        if not ct.can_fire(spot):
            continue
        # Lowest HP within a class, so a building already hit is finished
        # rather than abandoned half-dead for the price of the shots so far.
        rank = (value, ct.get_hp(building_id), building_id)
        if best is None or rank < best[0]:
            best = (rank, spot)
    if best is None:
        return False
    ct.fire(best[1])
    return True
