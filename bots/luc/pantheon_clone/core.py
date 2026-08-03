"""Core: four Builders on rounds 0-3, then feed the raiders' Gunners."""

from constants import (AMMO_BUFFER, AMMO_START_ROUND, OPENING_AMMO,
                       OPENING_BUILDERS, PICKUP_RANGE_SQ, SLOT_LAUNCHER,
                       SLOT_OWN_CORE, SPAWN_REACH_SQ)
from fcode import Position
from utils import dist_sq, pack_pos, read_enemy_core, unpack_pos


def run(player, ct) -> None:
    pos = tuple(ct.get_position())
    ct.write_store(SLOT_OWN_CORE, pack_pos(pos))

    _convert(ct)

    if player.spawned >= OPENING_BUILDERS:
        return
    if ct.get_global_resources() < ct.get_builder_bot_cost():
        return

    # The Core's spawn radius is sqrt(8), NOT one tile -- Pantheon uses the
    # reach. Its round-0 Builder sits at offsets like (2,0) and (2,1) from the
    # Core (32 and 24 of 150) as often as at the adjacent diagonal, which puts
    # the pad a full tile further forward before a single unit has moved.
    # Offsets beyond dist_sq 5 never appear, so the (2,2) corners are excluded.
    enemy = read_enemy_core(ct, pos)
    pad = unpack_pos(ct.read_store(SLOT_LAUNCHER))

    # Rule: step as far along the eight-way ray at the enemy as the spawn reach
    # allows. Scored against the 150 real openings this reproduces 49% of the
    # round-0 tiles, against 41% for a single step and 15% for "whichever legal
    # tile is nearest the enemy" -- Pantheon commits to the straight line out,
    # it does not shave distance.
    # Only the round-0 Builder goes deep. Once the pad is up the rest spawn on
    # the Core's own ring: in all seven games checked against the real replays
    # the round-1 Builder is at distance 1 from the Core, never out on the ray,
    # and it is always a tile the pad can already pick up from.
    if player.spawned == 0:
        ray = _ray_sites(pos, enemy)
        sites = _spawn_sites(pos)

        def rank(p):
            return (ray.index(p) if p in ray else len(ray), dist_sq(p, enemy))
    else:
        sites = [p for p in _spawn_sites(pos) if dist_sq(p, pos) <= 2]

        def rank(p):
            reachable = 0 if (pad is None or dist_sq(p, pad) <= PICKUP_RANGE_SQ) else 1
            return (reachable, dist_sq(p, enemy))

    for site in sorted(sites, key=rank):
        if ct.can_spawn(Position(*site)):
            ct.spawn_builder(Position(*site))
            player.spawned += 1
            return


def _ray_sites(core, enemy):
    """Tiles along the eight-way ray at the enemy, farthest legal one first."""
    ux = (enemy[0] > core[0]) - (enemy[0] < core[0])
    uy = (enemy[1] > core[1]) - (enemy[1] < core[1])
    out = [(core[0] + ux * k, core[1] + uy * k) for k in (2, 1)
           if 0 < (ux * k) ** 2 + (uy * k) ** 2 <= SPAWN_REACH_SQ]
    return out


def _spawn_sites(core):
    """Every tile the Core may spawn on, minus the corners Pantheon never uses.

    The action radius is sqrt(8), but no opening in the sample spawns past
    dist_sq 5 -- the (2,2) corners sit exactly on the boundary and are never
    used, so the reachable set is effectively dist_sq <= 5.
    """
    return [(core[0] + dx, core[1] + dy)
            for dx in (-2, -1, 0, 1, 2) for dy in (-2, -1, 0, 1, 2)
            if 0 < dx * dx + dy * dy <= SPAWN_REACH_SQ]


def _convert(ct) -> None:
    """Convert 2 on round 0, then hold a small pool topped up from round 6.

    Pantheon banks no ammunition -- peak pool 8, but ~139 converted over a game,
    which is a tiny buffer refilled every round as the raiders spend it. Getting
    this wrong is expensive and silent: a Gunner beside the enemy Core with no
    ammunition is a Gunner that does not shoot, and the Core takes 50 hits to
    kill. An earlier version keyed the buffer off a Gunner counter in the store;
    two raiders doing read-modify-write in the same round clobber each other, it
    undercounted, and the raid starved at 23 ammunition a game.
    """
    if ct.get_current_round() == 0:
        if ct.can_convert_ammo(OPENING_AMMO):
            ct.convert_ammo(OPENING_AMMO)
        return

    # Nothing converts before the raiders are in place; titanium spent on ammo
    # before then is titanium not spent getting them there.
    if ct.get_current_round() < AMMO_START_ROUND:
        return

    ammo = ct.get_global_ammo()
    if ammo >= AMMO_BUFFER:
        return
    spare = ct.get_global_resources() - ct.get_builder_bot_cost()
    amount = min(AMMO_BUFFER - ammo, spare)
    if amount > 0 and ct.can_convert_ammo(amount):
        ct.convert_ammo(amount)
