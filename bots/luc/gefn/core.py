"""Atlas-aware Core opening, doctrine choice, and reinforcement spawning."""

import sys
from typing import TYPE_CHECKING

import doctrine
from fcode import Controller, Direction, EntityType, Environment, Position

from atlas import identify_visible
from constants import (REPLACEMENT_BANK_THRESHOLD,
                       REPLACEMENT_COOLDOWN_ROUNDS,
                       ECON_BUILDER_ROUND, ECON_EXPAND_BUILDERS,
                       ECON_EXPAND_RESERVE, ECON_MAX_TOTAL_BUILDERS,
                       ECON_WATCHDOG_ENABLED, ECON_WATCHDOG_MAX_SPAWNS,
                       ECON_WATCHDOG_MIN_ROUND, ECON_WATCHDOG_ROUNDS,
                       MAX_OPENING_BUILDERS, PAD_FIRST_ORDER,
                       SHOOTER_POS_SHIFT,
                       SLOT_BUILDER_HEARTBEAT,
                       SLOT_CORE_DAMAGED, SLOT_ENEMY_CORE, SLOT_OWN_CORE)
from utils import pack_core, pack_enemy, pack_pos

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
    # Income tracking must read the bank before this turn's own ammo
    # conversion spends from it. The stored value is taken after conversion
    # and before any spawn, so a spawn's cost can only make the next delta
    # look *smaller* -- the watchdog can miss an income round right after
    # spending, never invent one.
    bank_now = ct.get_global_resources()
    current_round = ct.get_current_round()
    if not hasattr(player, "watchdog_prev_bank"):
        player.watchdog_prev_bank = bank_now
        player.last_income_round = current_round
        player.watchdog_spawns = 0
    if bank_now > player.watchdog_prev_bank:
        player.last_income_round = current_round
    income_dead = (
        ECON_WATCHDOG_ENABLED
        and current_round >= ECON_WATCHDOG_MIN_ROUND
        and current_round - player.last_income_round >= ECON_WATCHDOG_ROUNDS
        and player.watchdog_spawns < ECON_WATCHDOG_MAX_SPAWNS
    )
    # While income is dead, ammo conversion must not eat the one bank that can
    # still buy the rebuild: hold back a Builder and the Harvester it exists
    # to place. The COMBAT_AMMO_FLOOR emergency override still wins over this
    # -- turrets that cannot fire while under fire lose faster than a dead
    # economy does.
    rebuild_reserve = (
        ct.get_builder_bot_cost() + ct.get_harvester_cost() if income_dead
        else 0
    )
    _keep_ammunition(ct, rebuild_reserve)
    player.watchdog_prev_bank = ct.get_global_resources()
    if not hasattr(player, "repair_alert"):
        player.repair_alert = False
    hp, max_hp = ct.get_hp(ct.get_id()), ct.get_max_hp(ct.get_id())
    if hp <= max_hp - 50:
        player.repair_alert = True
    elif hp == max_hp:
        player.repair_alert = False
    if not hasattr(player, "atlas"):
        player.atlas = None
    if not hasattr(player, "builders_spawned"):
        player.builders_spawned = 0
        player.last_spawn_round = -999
        core = ct.get_position()
        player.atlas = identify_visible(ct, tuple(core))
        # The corner rule reads only dimensions and our own Core position, so
        # it works identically with or without an atlas hit.
        player.doctrine = doctrine.classify(ct)
        print(f"DOCTRINE round={ct.get_current_round()} "
              f"map={ct.get_map_width()}x{ct.get_map_height()} "
              f"core={tuple(core)} choice={doctrine.NAMES[player.doctrine]}",
              file=sys.stderr, flush=True)
        ores = ([Position(*tile) for tile in player.atlas.ores]
                if player.atlas is not None else
                [tile for tile in ct.get_nearby_tiles()
                 if ct.get_tile_env(tile) == Environment.ORE_TITANIUM
                 and ct.get_tile_building_id(tile) is None])
        ores.sort(key=lambda tile: (tile.distance_squared(core), tile.x, tile.y))
        player.opening_ore_targets = ores
    ct.write_store(SLOT_OWN_CORE,
                   pack_core(ct.get_position(), player.doctrine))
    alarm = int(player.repair_alert)
    if player.repair_alert and hp <= CRITICAL_HP:
        alarm = 2
    # The guard will not answer a shooter it cannot see, and its vision is a
    # fraction of the Core's. Publish the nearest visible enemy turret so the
    # guard knows where to walk; see SHOOTER_POS_SHIFT for why the alarm slot
    # carries it.
    shooter = 0
    if alarm:
        try:
            core_pos = ct.get_position()
            turrets = [
                ct.get_position(entity_id)
                for entity_id in ct.get_nearby_entities()
                if ct.get_team(entity_id) != ct.get_team()
                and ct.get_entity_type(entity_id) in (EntityType.GUNNER,
                                                      EntityType.SENTINEL)
            ]
            if turrets:
                turrets.sort(key=lambda t: (t.distance_squared(core_pos),
                                            t.x, t.y))
                shooter = pack_pos(turrets[0])
        except Exception as error:  # noqa: BLE001 - beacon must not kill the Core
            print(
                f"PLAN_FAILED id={ct.get_id()} round={ct.get_current_round()} "
                f"action=locate shooter reason={type(error).__name__}: {error}"
            )
    ct.write_store(SLOT_CORE_DAMAGED, alarm | (shooter << SHOOTER_POS_SHIFT))
    if player.atlas is not None:
        ct.write_store(SLOT_ENEMY_CORE, pack_enemy(player.atlas.enemy_core, True))

    economy_builders = doctrine.economy_builders(player.doctrine)
    opening_builders = doctrine.max_opening_builders(player.doctrine)
    role = player.builders_spawned
    resources = ct.get_global_resources()
    builder_cost = ct.get_builder_bot_cost()
    if resources < builder_cost:
        return
    has_live_builder = (
        ct.read_store(SLOT_BUILDER_HEARTBEAT) >= ct.get_current_round()
    )
    # Past the opening, buy income. See ECON_EXPAND_BUILDERS: a Builder bought
    # out of genuine surplus late in a long game is the win condition rather
    # than an attrition body, because the round-1000 tiebreak is decided on
    # titanium collected.
    #
    # The cap is on total spawns, not on a live headcount, because buffered
    # store writes make a live headcount impossible to publish -- see
    # ECON_MAX_TOTAL_BUILDERS. It shares the replacement cooldown so a rich bank
    # cannot convert the whole allowance in four consecutive rounds.
    expanding = (
        ECON_EXPAND_BUILDERS
        and ct.get_current_round() >= ECON_BUILDER_ROUND
        and resources >= builder_cost + ECON_EXPAND_RESERVE
        and role < ECON_MAX_TOTAL_BUILDERS
        and ct.get_current_round() >= player.last_spawn_round
        + REPLACEMENT_COOLDOWN_ROUNDS
    )
    # The revive path: income is dead, so neither the bank threshold nor the
    # heartbeat will ever fire again on their own. Spawn a miner (every
    # post-opening Builder is one, see LATE_BUILDERS_MINE) at whatever the
    # bank can pay. Ore targets are required -- without a known deposit the
    # spawn arithmetic below produces an attacker, which revives nothing.
    # The cooldown is the watchdog window itself, not the replacement
    # cooldown: a fresh miner needs the walk plus a Harvester before any
    # income can prove it worked, and stacking three bodies on the same dead
    # economy inside twelve rounds is how the bank dies for good.
    reviving = (
        income_dead
        and len(player.opening_ore_targets) > 0
        and ct.get_current_round() >= player.last_spawn_round
        + ECON_WATCHDOG_ROUNDS
    )
    if (role >= opening_builders and has_live_builder and not expanding
            and not reviving):
        # ...unless the bank says the workforce is too small to spend it.
        #
        # The heartbeat only proves that *one* Builder is alive, so a team that
        # loses two of its three never replaces them: it keeps mining into a
        # bank nothing is left to spend. Measured on sweden against
        # ragnarok_fair, this bot is down to one Builder by round 45 and dies
        # on round 103 holding 358 titanium, beaten by an opponent that mined
        # none at all.
        #
        # A healthy three-Builder team does not bank this much -- it converts
        # income into Harvesters and turrets as it arrives -- so a bank this
        # large is itself the signal that the workforce cannot keep up. That
        # makes it a better trigger than a headcount, which the comms store
        # cannot carry: writes are invisible to other units until the next
        # round, so a per-round bitmask never accumulates.
        #
        # The +20% cost scale a replacement adds was already refunded when the
        # Builder it replaces died, so this restores the intended composition
        # rather than inflating past it.
        if (resources < REPLACEMENT_BANK_THRESHOLD
                or ct.get_current_round() < player.last_spawn_round
                + REPLACEMENT_COOLDOWN_ROUNDS):
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
    ore_count = len(player.opening_ore_targets)
    if role >= opening_builders and ore_count:
        # Expansion Builders are miners (builder.py forces the role), so they
        # want the ore side of the spawn ring. Left to the arithmetic above they
        # take `mining_role = -1` and spawn facing the enemy Core -- the whole
        # ring's width away from the job they are about to be given, which on a
        # large map is twenty rounds of walking back.
        #
        # They cycle past the opening's own deposits: those are already claimed
        # and belted, and a second body on a saturated trunk is the one thing
        # the round-1000 tiebreak does not pay for.
        mining_role = (economy_builders + role - opening_builders) % ore_count
        mines = True
    else:
        mines = 0 <= mining_role < min(economy_builders, ore_count)
    if mines:
        target = player.opening_ore_targets[mining_role]
        goals = [target.add(direction) for direction in CARDINALS
                 if _on_map(ct, target.add(direction))]
    else:
        target = (Position(*player.atlas.enemy_core) if player.atlas is not None
                  else _scout_target(ct, max(0, role - economy_builders)))
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
        player.last_spawn_round = ct.get_current_round()
        if reviving:
            player.watchdog_spawns += 1
            print(f"WATCHDOG round={ct.get_current_round()} "
                  f"revive={player.watchdog_spawns} bank={resources} "
                  f"quiet_since={player.last_income_round}",
                  file=sys.stderr, flush=True)


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


def _keep_ammunition(ct, extra_reserve: int = 0) -> None:
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
            extra_reserve,
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
