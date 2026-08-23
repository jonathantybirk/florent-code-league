"""Turret-vs-turret threat geometry: is a tile safe from a known enemy
turret, which known enemy turrets could a candidate placement threaten, and
-- given a friendly turret that ended up in enemy line of fire anyway --
which adjacent tile (if any) a healer can stand on without itself being
shot.

Pure calculation, no `ct` calls and no `run()` -- same shape as
bots/test/econ2: a library meant to be wired into a real bot's run() later,
not a probe or a standalone bot. Nothing here populates the enemy-turret
data it operates on; see EnemyTurret and the README's "Data source"
section for what a caller is responsible for.

## The tactical idea

A Gunner's threat is a circle (GUNNER_RANGE_SQ) -- it can rotate for 10 Ti
+ 1 round of cooldown, so over time it can face any of its 8 possible
directions, and range is the only thing that keeps you safe from one.
A Sentinel's threat is a single ray along its *fixed* facing (it never
rotates) reaching further (SENTINEL_RANGE_SQ) -- so the way to be safe from
a Sentinel is to stay off its one line, at any distance, not to out-range
it. This is the "offensive advantage" the caller gets once an enemy turret
is placed and its type/facing has been observed: a Sentinel built outside a
spotted Gunner's circle but on a line the Sentinel is free to face can
threaten the Gunner while staying permanently out of its own reach; a
Gunner tucked off a spotted Sentinel's one ray is safe from it regardless
of distance. threatens()/is_safe() below are the primitives for checking
either side of that trade; best_cluster_placement() ranks candidate tiles
by how many known enemies a single new turret could threaten while staying
safe from all of them.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

from fcode import Direction, EntityType, GameConstants, Position

GUNNER_RANGE_SQ = GameConstants.GUNNER_VISION_RADIUS_SQ  # 13
SENTINEL_RANGE_SQ = GameConstants.SENTINEL_VISION_RADIUS_SQ  # 32

# Turrets (unlike Builder Bot movement/conveyors) can face any of the 8
# compass directions, not just the 4 cardinals -- see
# common/toolbox.py's try_rotate_toward_enemy, which rotates a Gunner
# through this same set.
_ALL_DIRECTIONS = tuple(d for d in Direction if d != Direction.CENTRE)
_CARDINALS = (Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST)


@dataclass(frozen=True)
class EnemyTurret:
    """One observed (or last-known) enemy turret. Nothing in this module
    populates this -- a caller builds these from its own vision-gated
    scouting/reporting, the same division of labor econ2's self.map has
    with whatever fills it in.

    direction is the turret's facing if it's ever been observed, else None.
    For a GUNNER, a cached direction can go stale the instant the real one
    rotates -- there's no notification of that, so treat a non-None
    direction on a Gunner as "last known," not "current" (threatens()
    below doesn't use it for exactly this reason -- see its docstring).
    last_seen_round is caller-supplied bookkeeping only; nothing here reads
    it, on purpose -- deciding when a sighting is too stale to trust is a
    judgment call for the caller, not this module.
    """

    position: Position
    etype: EntityType
    direction: Direction | None = None
    last_seen_round: int | None = None


def _on_ray(origin: Position, direction: Direction, point: Position, range_sq: int) -> bool:
    """True if point lies on origin's forward ray along direction (origin
    itself excluded), within range_sq. direction's delta components are
    each in {-1, 0, 1} (one of the 8 compass directions), so "on the ray"
    is just "point - origin is a positive integer multiple of that delta."
    """
    dx, dy = direction.delta()
    px, py = point.x - origin.x, point.y - origin.y

    if dx == 0:
        if px != 0 or py == 0 or (py > 0) != (dy > 0):
            return False
    elif dy == 0:
        if py != 0 or px == 0 or (px > 0) != (dx > 0):
            return False
    else:
        if px == 0 or py == 0 or abs(px) != abs(py):
            return False
        if (px > 0) != (dx > 0) or (py > 0) != (dy > 0):
            return False

    return origin.distance_squared(point) <= range_sq


def threatens(turret: EnemyTurret, tile: Position) -> bool:
    """Whether turret could hit tile, ever -- the conservative direction
    always: no obstruction modeling (a wall we haven't actually observed
    must never be the reason we call a tile "safe" -- same "None means
    unknown, not confirmed empty" caution as econ2's self.map), and a
    Gunner's cached direction is ignored entirely rather than trusted,
    since it can rotate for a flat 10 Ti any round it isn't on cooldown --
    the only thing that keeps you safe from one is its range, not whatever
    way it happened to be facing when last seen.

    A LAUNCHER never counts as a threat here: it deals no direct damage to
    a building (it only picks up/throws Builder Bots), so it can't hurt a
    placed turret -- see safe_heal_tile's docstring for why it still
    matters to a healer standing next to one.
    """
    if turret.etype == EntityType.GUNNER:
        return turret.position.distance_squared(tile) <= GUNNER_RANGE_SQ
    if turret.etype == EntityType.SENTINEL:
        # Fixed at build time, never rotates -- unlike a Gunner, a cached
        # facing IS trustworthy once observed. Unknown facing is the
        # conservative opposite: assume it could be facing any of the 8
        # ways, so every axis through it is live until proven otherwise.
        directions = (turret.direction,) if turret.direction is not None else _ALL_DIRECTIONS
        return any(_on_ray(turret.position, d, tile, SENTINEL_RANGE_SQ) for d in directions)
    return False


def is_safe(tile: Position, enemies: Iterable[EnemyTurret]) -> bool:
    """True if no known enemy turret threatens tile."""
    return not any(threatens(e, tile) for e in enemies)


def gunner_coverage(position: Position, enemies: Iterable[EnemyTurret]) -> int:
    """Count of known enemy turrets a Gunner built at position could
    eventually hit by rotating to face it. Since rotation is cheap and
    free to redo, "could hit" is just "within range" -- unlike
    best_sentinel_facing, there's no single-line commitment to model.
    """
    return sum(
        1
        for e in enemies
        if e.position != position and position.distance_squared(e.position) <= GUNNER_RANGE_SQ
    )


def best_sentinel_facing(position: Position, enemies: Iterable[EnemyTurret]) -> tuple[Direction | None, int]:
    """The one facing (of the 8) a Sentinel built at position should commit
    to in order to threaten the most known enemies, and that count. Unlike
    gunner_coverage, a Sentinel can never retarget off its build-time
    facing, so only enemies exactly on one chosen ray ever count --
    (None, 0) if no facing threatens anything.
    """
    enemies = list(enemies)
    best_dir: Direction | None = None
    best_count = 0
    for d in _ALL_DIRECTIONS:
        count = sum(1 for e in enemies if _on_ray(position, d, e.position, SENTINEL_RANGE_SQ))
        if count > best_count:
            best_dir, best_count = d, count
    return best_dir, best_count


@dataclass(frozen=True)
class Placement:
    """One scored candidate turret placement. facing is the commit-at-build
    direction for a SENTINEL, always None for a GUNNER (its facing is a
    live rotation choice, not part of the placement itself -- see
    gunner_coverage)."""

    position: Position
    turret_type: EntityType
    facing: Direction | None
    coverage: int


def best_cluster_placement(
    candidates: Iterable[Position],
    enemies: Sequence[EnemyTurret],
    turret_types: tuple[EntityType, ...] = (EntityType.GUNNER, EntityType.SENTINEL),
) -> Placement | None:
    """Highest-coverage safe placement among candidates: the tile (and
    turret type, and facing for a Sentinel) that threatens the most known
    enemy turrets while itself being threatened by none of them. None if no
    candidate is both safe and threatens at least one enemy.

    candidates is caller-supplied on purpose -- generating a reasonable
    search area (near a builder's current position, within vision, etc.)
    is bot-specific the way warden_'s _guard_position is; this function
    only ranks whatever's handed to it. Coverage ignores obstruction (see
    threatens) and is therefore a ranking heuristic, not a final answer --
    a caller must still confirm with ct.can_build_*/ct.can_fire_from live
    before actually committing titanium, the same way econ2's expected_flow
    is a model to compare against reality, not reality itself.
    """
    best: Placement | None = None
    for pos in candidates:
        if not is_safe(pos, enemies):
            continue
        if EntityType.GUNNER in turret_types:
            coverage = gunner_coverage(pos, enemies)
            if coverage > 0 and (best is None or coverage > best.coverage):
                best = Placement(pos, EntityType.GUNNER, None, coverage)
        if EntityType.SENTINEL in turret_types:
            facing, coverage = best_sentinel_facing(pos, enemies)
            if coverage > 0 and (best is None or coverage > best.coverage):
                best = Placement(pos, EntityType.SENTINEL, facing, coverage)
    return best


def safe_heal_tile(turret_position: Position, enemies: Iterable[EnemyTurret]) -> Position | None:
    """First orthogonally-adjacent tile to turret_position (heal is
    orthogonal-only -- see docs/official/docs/game-rules-builder-bot.txt)
    that is itself safe from every known enemy turret, or None if every
    adjacent tile is threatened.

    This is "if a turret ends up in enemy line of fire, heal it from a
    safe tile if possible": a friendly turret that had to be built into a
    threatened tile (no safe placement existed, or the enemy moved up
    after the fact) still shouldn't force its healer to stand somewhere
    threatened too. Note threatens() treats LAUNCHER as no threat to a
    turret's HP, but a Launcher next to the *healer's* candidate tile can
    still grab and fling the healer itself (it works on Builder Bots from
    either team) -- that's a different risk than the one this function
    checks, and isn't modeled here.

    Doesn't check in_bounds/tile occupancy/can_move -- a caller walking
    toward the returned tile still needs its own legality gate, same
    division of labor as the rest of this module.
    """
    enemies = list(enemies)
    for d in _CARDINALS:
        tile = turret_position.add(d)
        if is_safe(tile, enemies):
            return tile
    return None
