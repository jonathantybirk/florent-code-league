"""Sentinel behavior: snipe the enemy Core through anything, else clean up.

A Sentinel's shot is never blocked -- walls, buildings, and bodies are all
transparent to it -- so a siege Sentinel aligned with the enemy Core kills it
on a fixed clock (500 / 18 damage at a 3-round reload = 84 rounds) no matter
what the defender builds. The Core therefore outranks every other target,
and the store's enemy-Core position is enough: vision is not required for a
legal shot, only range and alignment, which can_fire checks for us.
"""

from typing import TYPE_CHECKING

from fcode import Controller, EntityType, GameError, Position

from constants import (BUILDER_PRIORITY_RADIUS_SQ, D8,
                       HOLD_FIRE_ON_TENDED_BARRIER,
                       HOME_GUARD_RADIUS_SQ, SIEGE_STALL_ROUNDS,
                       SLOT_ENEMY_CORE, SLOT_OWN_CORE,
                       STARVE_THE_ECONOMY, TURRET_QUIET_ROUNDS)
from utils import unpack_core, unpack_enemy

if TYPE_CHECKING:
    from main import Player


# Which enemy building is worth 10 ammunition, best first.
#
# Harvester before conveyor: it is 30 HP against 20, but 20 Ti against 3 to
# replace, and it is the *source*. Killing one stops 2.5 Ti a round until they
# walk a Builder back to the ore, and live Harvesters are the second tiebreak
# criterion outright. Splitter before conveyor for the same reason at 6 Ti
# against 3, and because a splitter is a junction: the lines below it all stop.
#
# Turrets are absent deliberately. They are 25 and 40 HP, they cost three or
# four shots, and destroying one hands back its +20% of cost scale -- we would
# be paying 30-40 Ti of ammunition to make everything they build cheaper.
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
    if not hasattr(player, "quiet_rounds"):
        player.quiet_rounds = 0
        player.core_hp = None
        player.core_stalled = 0
    team = ct.get_team()
    here = ct.get_position()
    targets = [entity_id for entity_id in ct.get_nearby_entities()
               if ct.get_team(entity_id) != team
               and ct.can_fire(ct.get_position(entity_id))
               and not _is_tended_barrier(ct, entity_id)]
    # 1. A Builder Bot in reach, at either end of the map. Defending, the
    # intruder emplacing at our Core is the whole enemy attack, and a Builder
    # killed on our doorstep is an attack that does not come back. Besieging,
    # it is the mender arithmetic: shooting a Core past a mender is 10
    # ammunition a shot spent to lose slowly, and shooting the mender ends it.
    builders = [entity_id for entity_id in targets
                if ct.get_entity_type(entity_id) is EntityType.BUILDER_BOT
                and ct.get_position(entity_id).distance_squared(here)
                <= BUILDER_PRIORITY_RADIUS_SQ]
    if builders:
        ct.fire(ct.get_position(min(builders, key=ct.get_hp)))
        player.quiet_rounds = 0
        return
    # 2. The Core, for as long as firing at it is actually moving its HP.
    if _fire_at_core(player, ct):
        player.quiet_rounds = 0
        return
    # 3. The supply line, which is what the round-1000 tiebreak is made of and
    # which this lineage's Sentinels have never been able to see.
    if STARVE_THE_ECONOMY and _fire_at_economy(ct, team):
        player.quiet_rounds = 0
        return
    # 4. Anything else on the line.
    if targets:
        ct.fire(ct.get_position(min(targets, key=ct.get_hp)))
        player.quiet_rounds = 0
        return

    _stand_down_if_pointless(player, ct)


def _fire_at_core(player: "Player", ct: Controller) -> bool:
    """Shoot the enemy Core, and notice when that has stopped working.

    Vision is not required for a legal shot, only range and alignment, so the
    store's remembered position is enough to fire. Reading the Core's HP does
    need vision -- a Sentinel's is the same radius as its reach, so a seat that
    can shoot the Core can nearly always also watch it.

    The stall counter is the mender arithmetic made operational: a besieged Core
    whose HP has stopped falling is being held, not killed slowly, and the
    Sentinel's ammunition is worth more spent on the supply line feeding it.
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
    """Break the enemy's supply line.

    Buildings are not units, so they never appear in `get_nearby_entities` and
    every Sentinel this lineage has built has been blind to them. A Harvester is
    30 HP and a conveyor 20 -- two shots each -- and a hole anywhere in a trunk
    leaves every Harvester upstream of it mining into a dead end. The 3 Ti they
    pay to patch it is not the cost being imposed; the cost is the Builder turns
    and the rounds of stopped income, which this bot knows the price of exactly
    because REPAIR_ATTEMPT_LIMIT exists to stop it happening to us.
    """
    best = None
    for building_id in ct.get_nearby_buildings():
        if ct.get_team(building_id) == team:
            continue
        value = BUILDING_VALUE.get(ct.get_entity_type(building_id))
        if value is None:
            continue
        if _is_tended_barrier(ct, building_id):
            continue
        spot = ct.get_position(building_id)
        if not ct.can_fire(spot):
            continue
        # Lowest HP within a class, so a building already hit is finished rather
        # than abandoned half-dead for the price of the shots already spent.
        rank = (value, ct.get_hp(building_id), building_id)
        if best is None or rank < best[0]:
            best = (rank, spot)
    if best is None:
        return False
    ct.fire(best[1])
    return True


def _stand_down_if_pointless(player: "Player", ct: Controller) -> None:
    """Retire a Sentinel that has had nothing to shoot for a long time.

    The Gunner has had this since vigil; the Sentinel never did, and it is the
    unit that needs it most. A Sentinel is 30 Ti and **+20%** on every price the
    team pays for as long as it stands, and unlike a Gunner it *cannot rotate* --
    so a Sentinel whose line has gone quiet has not merely stopped being useful,
    it has no way of ever becoming useful again. The enemy walked around it and
    it will point at that empty corridor for the remaining nine hundred rounds,
    charging rent on every Harvester and every barrier we build.

    Cost scale is a census of what is alive rather than what was ever built, so
    self-destructing refunds the 20% the moment it happens.

    Turrets close to our own Core are exempt whatever they have seen, exactly as
    for Gunners: they are insurance against the one rush that does arrive, and
    the round they are needed is the round it is too late to rebuild them.
    """
    if _enemy_on_the_line(ct):
        # Has a target and merely cannot shoot it: out of ammunition, or still
        # reloading. That is the opposite of pointless -- the turret is doing
        # its job and the team is failing to supply it, and retiring it would
        # answer an ammunition shortage by destroying the thing waiting on the
        # ammunition. `can_fire` folds ammo and cooldown into its answer, so
        # the raw attack pattern is what has to be consulted here.
        player.quiet_rounds = 0
        return
    player.quiet_rounds += 1
    if player.quiet_rounds < TURRET_QUIET_ROUNDS:
        return
    home, _ = unpack_core(ct.read_store(SLOT_OWN_CORE))
    if home is not None:
        if ct.get_position().distance_squared(Position(*home)) <= HOME_GUARD_RADIUS_SQ:
            return
    # Nothing after this call runs; the engine tears the unit down inside it.
    ct.self_destruct()


def _enemy_on_the_line(ct: Controller) -> bool:
    """Is anything of theirs standing in this turret's raw attack pattern?

    `get_attackable_tiles` ignores ammunition, cooldown and occupancy, which is
    exactly what is wanted: the question is whether this turret still covers
    something worth covering, not whether it can pull the trigger this round.
    """
    try:
        tiles = ct.get_attackable_tiles()
    except GameError:
        return False
    for tile in tiles:
        for lookup in (ct.get_tile_builder_bot_id, ct.get_tile_building_id):
            entity_id = lookup(tile)
            if entity_id is not None and ct.get_team(entity_id) != ct.get_team():
                return True
    return False


def _is_tended_barrier(ct: Controller, target_id: int) -> bool:
    """Skip a barrier whose Builder is still standing beside it.

    Same trade as the Gunner's, and worse: 18 damage for 10 Ti of ammunition
    against a 30 HP barrier they replace for 3. Two shots to break it, 20 Ti
    spent, and the Builder next to it puts it straight back. Every other target
    on this list is worth more than the wall, which is why this only filters
    barriers rather than deferring the whole volley -- with the wall skipped,
    min() simply picks the next-weakest real target.
    """
    if not HOLD_FIRE_ON_TENDED_BARRIER:
        return False
    if ct.get_entity_type(target_id) != EntityType.BARRIER:
        return False
    here = ct.get_position(target_id)
    for direction in D8:
        neighbour = here.add(direction)
        bot_id = ct.get_tile_builder_bot_id(neighbour)
        if bot_id is not None and ct.get_team(bot_id) != ct.get_team():
            return True
    return False
