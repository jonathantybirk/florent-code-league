"""Builder: one of four, and which one decides everything it ever does.

The Core spawns exactly one Builder per round on rounds 0-3, so a Builder's
spawn round *is* its index, and the Launcher throws in spawn order. Index 0
also builds the Launcher on round 1 before being thrown off it on round 2.
"""

from constants import (ECON_CONVEYORS, GUNNER_RANGE_SQ, LAUNCHER_RADIUS_MAX,
                       LAUNCHER_RADIUS_MIN, PICKUP_RANGE_SQ, RAIDER_GUNNER_MIN,
                       RAIDER_GUNNERS, RAIDER_THROWS, SLOT_LAUNCHER,
                       SLOT_ORE_HINT, SLOT_OWN_CORE, STUCK_ROUNDS,
                       THROW_RANGE_SQ)
from fcode import Environment, Position
from utils import (CARDINALS, chebyshev, dist_sq, facing_toward,
                   nearest_cardinal, pack_pos, read_enemy_core, sight_enemy_core,
                   step_toward, unpack_pos)


def run(player, ct) -> None:
    pos = tuple(ct.get_position())
    sight_enemy_core(ct)

    if player.index is None:
        # First run() lands the round after the spawn, so round-1 => index 0.
        player.index = max(0, ct.get_current_round() - 1)

    own_core = unpack_pos(ct.read_store(SLOT_OWN_CORE))
    if own_core is None:
        return
    enemy = read_enemy_core(ct, own_core)

    player.stuck = player.stuck + 1 if player.last == pos else 0
    player.last = pos

    # Index 0's one job before it is thrown: put the Launcher up on round 1.
    if player.index == 0 and not player.built_launcher:
        if unpack_pos(ct.read_store(SLOT_LAUNCHER)) is not None:
            player.built_launcher = True     # somebody already put one up
        elif _build_launcher(player, ct, pos, own_core, enemy):
            player.built_launcher = True
        else:
            # No legal pad from here. Standing still costs the whole opening,
            # so shuffle toward the enemy and try again next round; the radius
            # rule relaxes after a couple of failures.
            player.pad_attempts += 1
            step_toward(ct, enemy)
        return

    if not player.airborne and dist_sq(pos, own_core) > THROW_RANGE_SQ:
        player.airborne = True   # only a throw moves us that far that fast

    # Waiting for a lift: stand inside the pad's pickup range and do nothing
    # else. A Builder the Launcher cannot reach costs us a whole throw.
    if not player.airborne and _stage_on_pad(player, ct, pos):
        return

    if player.index < RAIDER_THROWS:
        _raid(player, ct, pos, enemy)
    else:
        _mine(player, ct, pos, own_core)


# ---------------------------------------------------------------------------
# Index 0 -- the pad
# ---------------------------------------------------------------------------

def _build_launcher(player, ct, pos, own_core, enemy) -> bool:
    """Launcher at Chebyshev 2-3 from our Core, on the enemy-facing side.

    Every one of the 150 observed sites sat in the enemy-facing quadrant at
    radius 2 or 3 -- close enough that the Builders keep spawning next to it,
    far enough that its throw disc already covers ground toward the enemy.

    Radius 2 is preferred over 3 (83 sites against 67), and for a reason that
    only shows up once you count throws: at radius 2 the Core's spawn ring sits
    almost entirely inside the pad's pickup disc, so each new Builder is in
    range the turn it appears and the four throws land on r2-r5 without a gap.
    """
    if ct.get_action_cooldown() != 0:
        return False
    if ct.get_global_resources() < ct.get_launcher_cost():
        return False

    # The pad goes one step further out than the Builder, straight along the
    # ray from the Core. This is not a guess: across 150 games the Launcher
    # offsets are the round-0 Builder offsets shifted one step outward, count
    # for count -- Builder (2,0) 32 times and Launcher (3,0) 32 times, Builder
    # (1,1) 62 times splitting into Launcher (1,2) 40 and (2,1) 22.
    relaxed = player.pad_attempts >= 2
    lo = 1 if relaxed else LAUNCHER_RADIUS_MIN
    hi = 4 if relaxed else LAUNCHER_RADIUS_MAX

    best, best_key = None, None
    for d in CARDINALS:
        site = tuple(Position(*pos).add(d))
        radius = chebyshev(site, own_core)
        if not (lo <= radius <= hi):
            continue
        if not ct.can_build_launcher(Position(*site)):
            continue
        # Outward first, then whichever of the tied outward tiles faces the
        # enemy -- exactly the 40/22 split above.
        key = (-dist_sq(site, own_core), dist_sq(site, enemy))
        if best_key is None or key < best_key:
            best, best_key = site, key

    if best is None:
        return False
    ct.build_launcher(Position(*best))
    return True


def _stage_on_pad(player, ct, pos) -> bool:
    """Queue next to the Launcher until it throws us. True = handled this turn."""
    pad = unpack_pos(ct.read_store(SLOT_LAUNCHER))
    if pad is None:
        return False
    if dist_sq(pos, pad) <= PICKUP_RANGE_SQ:
        return True          # in range; stand still and wait to be picked up
    step_toward(ct, pad)
    return True


# ---------------------------------------------------------------------------
# Indices 0-1 -- the raid
# ---------------------------------------------------------------------------

def _raid(player, ct, pos, enemy) -> None:
    """Walk at the enemy Core and ring it with Gunners at Chebyshev 2-4."""
    radius = chebyshev(pos, enemy)

    if (player.gunners < RAIDER_GUNNERS
            and dist_sq(pos, enemy) <= GUNNER_RANGE_SQ + 8
            and ct.get_action_cooldown() == 0
            and ct.get_global_resources() >= ct.get_gunner_cost()):
        if _place_gunner(ct, pos, enemy):
            player.gunners += 1
            return

    # Too far to place, or the ring here is full: close on the Core. Sitting
    # still at radius 3 with nothing buildable is how a raider does nothing for
    # 900 rounds, so there is no idle branch that leaves us stationary.
    if radius > RAIDER_GUNNER_MIN:
        if step_toward(ct, enemy):
            return

    if ct.get_action_cooldown() == 0:
        _heal(ct, pos)


def _place_gunner(ct, pos, enemy) -> bool:
    """Gunner on an adjacent tile that can actually shoot the enemy Core.

    A Gunner's reach is dist_sq <= 13 and it only fires along its own facing,
    so "near the Core" is not the constraint -- being in range *and* on a ray
    through it is. Ranking sites by Chebyshev radius instead put most of the
    ring outside range, where they never fired, the ammunition pool never
    drained, and the Core took 114 rounds to fall instead of 38.
    """
    best, best_key = None, None
    for d in CARDINALS:
        site = tuple(Position(*pos).add(d))
        facing = facing_toward(site, enemy)
        if not ct.can_build_gunner(Position(*site), facing):
            continue
        reach = dist_sq(site, enemy)
        dx, dy = enemy[0] - site[0], enemy[1] - site[1]
        on_ray = (dx == 0 or dy == 0 or abs(dx) == abs(dy))
        # In range and on a ray beats in range; both beat merely being close.
        key = (0 if (reach <= GUNNER_RANGE_SQ and on_ray) else
               1 if reach <= GUNNER_RANGE_SQ else 2, reach)
        if best_key is None or key < best_key:
            best, best_key = (site, facing), key
    if best is None:
        return False
    ct.build_gunner(Position(*best[0]), best[1])
    return True


# ---------------------------------------------------------------------------
# Indices 2-3 -- the far economy
# ---------------------------------------------------------------------------

def _mine(player, ct, pos, own_core) -> None:
    """Harvester on the ore we were thrown at, then a conveyor run homeward."""
    if ct.get_action_cooldown() == 0:
        if player.harvester is None:
            if _build_harvester(player, ct, pos):
                return
        elif player.conveyors < ECON_CONVEYORS:
            if _build_conveyor(player, ct, pos, own_core):
                return

    target = player.target
    if target is None or tuple(pos) == tuple(target) or player.stuck >= STUCK_ROUNDS:
        target = player.target = _pick_ore(ct, pos, own_core)
    if target is not None:
        step_toward(ct, target)


def _build_harvester(player, ct, pos) -> bool:
    if ct.get_global_resources() < ct.get_harvester_cost():
        return False
    for d in CARDINALS:
        site = Position(*pos).add(d)
        if ct.can_build_harvester(site):
            ct.build_harvester(site)
            player.harvester = tuple(site)
            player.target = None
            return True
    return False


def _build_conveyor(player, ct, pos, own_core) -> bool:
    """Lay the belt back toward the Core, one tile per turn as we walk home."""
    if ct.get_global_resources() < ct.get_conveyor_cost():
        return False
    facing = nearest_cardinal(Position(*pos).direction_to(Position(*own_core)))
    for d in CARDINALS:
        site = Position(*pos).add(d)
        if not ct.can_build_conveyor(site, facing):
            continue
        # Only worth it if it moves resources homeward.
        if dist_sq(tuple(site), own_core) >= dist_sq(pos, own_core):
            continue
        ct.build_conveyor(site, facing)
        player.conveyors += 1
        return True
    return False


def _pick_ore(ct, pos, own_core):
    """Nearest uncovered ore we can see, else the hint, else press outward."""
    best, best_key = None, None
    for tile in ct.get_nearby_tiles():
        try:
            if ct.get_tile_env(tile) not in (Environment.ORE_TITANIUM,
                                             Environment.ORE_AXIONITE):
                continue
            if ct.get_tile_building_id(tile) is not None:
                continue
        except Exception:
            continue
        t = tuple(tile)
        key = dist_sq(t, pos)
        if best_key is None or key < best_key:
            best, best_key = t, key
    if best is not None:
        ct.write_store(SLOT_ORE_HINT, pack_pos(best))
        return best

    hint = unpack_pos(ct.read_store(SLOT_ORE_HINT))
    if hint is not None and dist_sq(hint, pos) > 4:
        return hint

    # Nothing visible and no hint: keep pushing outward from home rather than
    # standing still. An idle economy Builder is the whole throw wasted.
    w, h = ct.get_map_width(), ct.get_map_height()
    away = (pos[0] + (pos[0] - own_core[0]), pos[1] + (pos[1] - own_core[1]))
    return (min(max(away[0], 0), w - 1), min(max(away[1], 0), h - 1))


def _heal(ct, pos) -> None:
    for d in CARDINALS:
        site = Position(*pos).add(d)
        try:
            if ct.can_heal(site):
                ct.heal(site)
                return
        except Exception:
            return
