"""Atlas-aware Core opening, doctrine choice, and reinforcement spawning."""

import sys
from collections import deque
from typing import TYPE_CHECKING

import doctrine
from fcode import Controller, Direction, Environment, Position

from atlas import identify_visible
from constants import (LAUNCH_RANGE_SQ, LAUNCHER_BUILDER_INDEX,
                       MAX_OPENING_BUILDERS,
                       PANTHEON_RAIDERS,
                       RING_RADIUS, SLOT_BUILDER_HEARTBEAT, SLOT_CORE_DAMAGED,
                       SLOT_ENEMY_CORE, SLOT_OWN_CORE)
from utils import pack_core, pack_enemy

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
    if not hasattr(player, "atlas"):
        player.atlas = None
    if not hasattr(player, "builders_spawned"):
        player.builders_spawned = 0
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
    ct.write_store(SLOT_CORE_DAMAGED, alarm)
    if player.atlas is not None:
        ct.write_store(SLOT_ENEMY_CORE, pack_enemy(player.atlas.enemy_core, True))

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

    if role == LAUNCHER_BUILDER_INDEX:
        # The pad Builder is spawned *onto* the pad's doorstep, not sent to ore
        # and walked back. Pantheon has its Launcher up on round 1 in 150 of
        # 150 games; ragnarok's Builder walks to the ring and gets there on
        # round 3, and two rounds of a four-round ferry is half the opening.
        target = _pad_site(ct, player)
        goals = [target.add(direction) for direction in CARDINALS
                 if _on_map(ct, target.add(direction))] or [target]
    elif role >= PANTHEON_RAIDERS and (role - PANTHEON_RAIDERS) < len(
            player.opening_ore_targets):
        target = player.opening_ore_targets[role - PANTHEON_RAIDERS]
        goals = [target.add(direction) for direction in CARDINALS
                 if _on_map(ct, target.add(direction))]
    else:
        target = (Position(*player.atlas.enemy_core) if player.atlas is not None
                  else _scout_target(ct, role - economy_builders))
        goals = [target]

    candidates = [tile for tile in ct.get_nearby_tiles(8) if ct.can_spawn(tile)]
    if role == LAUNCHER_BUILDER_INDEX:
        # The round-0 Builder goes on the ring of tiles orthogonally adjacent
        # to the Core footprint -- 25 of 25 in fresh v20 games against
        # tempest_fast -- and specifically on the one with the shortest *walk*
        # to the enemy Core: 24 of 25, against 11 of 25 for ranking that ring
        # by straight-line distance. It is the same objective the throws and
        # the pad already use, applied one step earlier.
        #
        # The Core is 2x2, so this ring is the footprint's neighbours. The rule
        # that stood here treated the Core as a point and stepped out along an
        # eight-way ray, which put the Builder on the wrong tile on nearly
        # every map and diverged from the real game on round 0.
        ring = {tuple(t) for t in _core_ring(ct, tuple(ct.get_position()))}
        on_ring = [t for t in candidates if tuple(t) in ring]
        if on_ring:
            enemy = tuple(target_core(ct, player))
            walk = _walk_from(ct, player, enemy)
            core = tuple(ct.get_position())
            # Ties are the common case -- the ring usually has two tiles the
            # same walk from the enemy Core -- and they are broken by which pad
            # the tile yields, not by the tile itself. The pad sits one step
            # further out, so each ring tile fixes a different throw disc;
            # the one whose disc reaches nearest the enemy Core wins.
            # Ties are the common case: the ring usually holds two tiles the
            # same walk from the enemy Core. Broken by which pad the tile
            # yields -- the pad sits one step further out, so each ring tile
            # fixes a different throw disc, and the disc that reaches nearest
            # the enemy Core wins.
            #
            # A fixed compass order (north, east, south, west) was tried here
            # instead and is a measured failure: it fixes crossfire, jackpot,
            # sprint and twins on round 0 and breaks duel and aurora, for
            # 14% action agreement against 17%. Something does separate those
            # cases -- they are exact ties on walk, on straight line and on pad
            # delivery -- but it is not a static direction preference.
            candidates = sorted(on_ring, key=lambda tile: (
                walk.get(tuple(tile), 1 << 20),
                _pad_delivery(ct, walk, core, tuple(tile)),
                tile.distance_squared(Position(*enemy)),
                tile.x, tile.y,
            ))
        else:
            candidates.sort(key=lambda tile: (
                min(_chebyshev(tile, goal) for goal in goals),
                tile.distance_squared(target), tile.x, tile.y))
    elif getattr(player, "pad_tile", None) is not None and role < MAX_OPENING_BUILDERS:
        # Every opening Builder is a passenger, so it has to spawn where the
        # pad can pick it up: dist_sq <= 2. On duel Pantheon spawns all four on
        # the column beside its pad -- (3,8), (3,7), (3,9), (3,8), the last
        # reusing the tile the first vacated when it was thrown -- and orders
        # them by which is nearest the enemy Core. Spawning outside that disc
        # is a passenger the ferry never collects.
        pad = Position(*player.pad_tile)
        enemy = Position(*target_core(ct, player))
        near = [t for t in candidates if t.distance_squared(pad) <= 2]
        if near:
            candidates = sorted(near, key=lambda tile: (
                tile.distance_squared(enemy), tile.x, tile.y))
        else:
            candidates.sort(key=lambda tile: (
                min(_chebyshev(tile, goal) for goal in goals),
                tile.distance_squared(target), tile.x, tile.y))
    else:
        candidates.sort(key=lambda tile: (
            min(_chebyshev(tile, goal) for goal in goals),
            tile.distance_squared(target),
            tile.x,
            tile.y,
        ))
    if candidates:
        chosen = candidates[0]
        ct.spawn_builder(chosen)
        if role == LAUNCHER_BUILDER_INDEX:
            # The pad goes one cardinal step further out from this tile, so it
            # is fixed the moment the round-0 Builder is placed.
            player.pad_tile = _outward(ct, tuple(ct.get_position()),
                                       tuple(chosen))
        player.builders_spawned += 1


def target_core(ct: Controller, player):
    """Best available guess at the enemy Core's north-west cell."""
    if player.atlas is not None:
        return tuple(player.atlas.enemy_core)
    return tuple(_scout_target(ct, 0))


# North, east, south, west -- the order ties are settled in.
_OUTWARD_ORDER = ((0, -1), (1, 0), (0, 1), (-1, 0))


def _outward_order(ct: Controller, core, spawn):
    """Rank of this tile's outward direction in the fixed compass order."""
    foot = {(core[0] + a, core[1] + b) for a in (0, 1) for b in (0, 1)}
    for index, (dx, dy) in enumerate(_OUTWARD_ORDER):
        if (spawn[0] - dx, spawn[1] - dy) in foot:
            return index
    return len(_OUTWARD_ORDER)


def _pad_delivery(ct: Controller, walk, core, spawn):
    """Shortest walk to the enemy Core from anywhere this tile's pad can throw."""
    pad = _outward(ct, core, spawn)
    if pad is None:
        return 1 << 20
    best = 1 << 20
    for dx in range(-5, 6):
        for dy in range(-5, 6):
            if dx * dx + dy * dy > LAUNCH_RANGE_SQ:
                continue
            value = walk.get((pad[0] + dx, pad[1] + dy))
            if value is not None and value < best:
                best = value
    return best


def _outward(ct: Controller, core, spawn):
    """One cardinal step further out from `spawn`, away from the footprint."""
    foot = {(core[0] + a, core[1] + b) for a in (0, 1) for b in (0, 1)}
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        if (spawn[0] - dx, spawn[1] - dy) in foot:
            out = (spawn[0] + dx, spawn[1] + dy)
            if _on_map(ct, Position(*out)) and out not in foot:
                return out
    return None


def _core_ring(ct: Controller, core):
    """Tiles orthogonally adjacent to the 2x2 Core footprint."""
    foot = {(core[0] + a, core[1] + b) for a in (0, 1) for b in (0, 1)}
    out = []
    for x, y in sorted(foot):
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            q = (x + dx, y + dy)
            if q not in foot and _on_map(ct, Position(*q)) and q not in out:
                out.append(q)
    return out


def _walk_from(ct: Controller, player, enemy):
    """Walking distance to the enemy Core over the terrain we know.

    With an atlas hit the walls are exact from round 0; without one the wall
    set is empty and this degrades to straight-line ordering, not to nonsense.
    """
    walls = set(player.atlas.walls) if player.atlas is not None else set()
    # Our own Core blocks movement, and it is a 2x2 block sitting right next to
    # every tile being ranked. Leaving it out lets paths route straight through
    # it and mis-orders the ring.
    here = tuple(ct.get_position())
    walls |= {(here[0] + a, here[1] + b) for a in (0, 1) for b in (0, 1)}
    w, h = ct.get_map_width(), ct.get_map_height()
    srcs = [(enemy[0] + a, enemy[1] + b) for a in (0, 1) for b in (0, 1)
            if 0 <= enemy[0] + a < w and 0 <= enemy[1] + b < h]
    dist = {s: 0 for s in srcs}
    queue = deque(srcs)
    while queue:
        x, y = queue.popleft()
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            n = (x + dx, y + dy)
            if (0 <= n[0] < w and 0 <= n[1] < h and n not in dist
                    and n not in walls):
                dist[n] = dist[(x, y)] + 1
                queue.append(n)
    return dist


def _pad_site(ct: Controller, player) -> Position:
    """The enemy-facing ring tile the first Launcher goes on.

    Mirrors _launcher_ring_targets in builder.py: the Core is 2x2, so the ring
    sits RING_RADIUS clear of the footprint and the enemy-facing site is the
    one the ferry wants.
    """
    core = ct.get_position()
    enemy = (Position(*player.atlas.enemy_core) if player.atlas is not None
             else _scout_target(ct, 0))
    dx = (enemy.x > core.x) - (enemy.x < core.x)
    dy = (enemy.y > core.y) - (enemy.y < core.y)
    if dx > 0:
        x = core.x + 1 + RING_RADIUS
    elif dx < 0:
        x = core.x - RING_RADIUS
    else:
        x = min((core.x, core.x + 1), key=lambda v: abs(enemy.x - v))
    if dy > 0:
        y = core.y + 1 + RING_RADIUS
    elif dy < 0:
        y = core.y - RING_RADIUS
    else:
        y = min((core.y, core.y + 1), key=lambda v: abs(enemy.y - v))
    x = max(0, min(ct.get_map_width() - 1, x))
    y = max(0, min(ct.get_map_height() - 1, y))
    return Position(x, y)


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
