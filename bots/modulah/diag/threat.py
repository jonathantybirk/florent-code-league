# GENERATED from bots/modulah/lib/threat.py -- edit that file, not this copy.
"""What is hitting the Core, how fast, and how bad it could suddenly get.

Three quantities, deliberately different in kind:

  hp     where we are now
  dhp    how fast it is changing -- backward-looking, 4-round mean
  burst  how bad one round could get -- forward-looking upper bound

The third exists because the first two are reactive. If the enemy has just
finished three Sentinels that have not fired yet, `dhp` still reads 0 while
`burst` jumps to 54. That gap is the only early warning available, and it is
precisely when Builders should stop laying conveyor and start mending.

The Core is the right unit to compute all of this. Max Sentinel reach is
dist_sq 32 and CORE_VISION_RADIUS_SQ is 36, so nothing that can damage the
Core is invisible to it -- while a Builder sees radius ~4.5 and cannot.
"""

from __future__ import annotations

from fcode import EntityType, GameConstants, GameError, Position

from geometry import (
    COMPASS,
    RAY_LEN,
    TURRET_DAMAGE,
    TURRET_DPR,
    can_ray_reach,
    touches_footprint,
)

# SENTINEL_FIRE_COOLDOWN is 2, so a 4-round window holds exactly two Sentinel
# shots regardless of phase. An odd window holds one or two depending on when
# you happened to sample, which invents variation that is not in the game.
TREND_WINDOW = 4

TURRET_KINDS = (EntityType.GUNNER, EntityType.SENTINEL)


def visible_enemy_turrets(ct) -> list[tuple[int, Position, EntityType]]:
    me = ct.get_team()
    out = []
    for bid in ct.get_nearby_buildings():
        try:
            if ct.get_team(bid) == me:
                continue
            kind = ct.get_entity_type(bid)
            if kind in TURRET_KINDS:
                out.append((bid, ct.get_position(bid), kind))
        except GameError:
            continue
    return out


def adjacent_enemy_builders(ct, footprint) -> int:
    me = ct.get_team()
    n = 0
    for uid in ct.get_nearby_units():
        try:
            if ct.get_team(uid) == me:
                continue
            if ct.get_entity_type(uid) != EntityType.BUILDER_BOT:
                continue
            if touches_footprint(ct.get_position(uid), footprint):
                n += 1
        except GameError:
            continue
    return n


def _reaches_core(ct, tpos: Position, kind: EntityType, footprint, aimed_only: bool):
    """Can this turret put damage on the Core, and along which facing?

    The cheap geometric filter runs first. Turrets are line weapons with 8
    facings, so an offset that is neither axial nor exactly diagonal is
    unreachable at any facing -- an enemy Sentinel at offset (3, 4) sits well
    inside dist_sq 32 and still can never hit that tile. Only offsets that
    survive that test are worth a can_fire_from call, which is a pyo3
    crossing and the expensive part of this sweep.
    """
    current = None
    if aimed_only:
        try:
            current = ct.get_direction(ct.get_tile_building_id(tpos))
        except GameError:
            return None

    for tile in footprint:
        dx, dy = tile.x - tpos.x, tile.y - tpos.y
        if not can_ray_reach(kind, dx, dy):
            continue
        facing = tpos.direction_to(tile)
        if aimed_only and facing != current:
            continue
        try:
            if ct.can_fire_from(tpos, facing, kind, tile):
                return facing
        except GameError:
            continue
    return None


def max_burst(ct, footprint, aimed_only: bool = False) -> int:
    """Worst-case damage the Core could take in a single round.

    By default this counts every turret POSITIONED to hit the Core, not only
    those currently aimed at it: `rotate` costs 10 Ti and one round, so a
    turret on a ray is one round from being live. Aimed-only reads 0 right up
    until it doesn't, which is useless as a trigger.

    This is an upper bound, not a forecast. Enemy ammo (SENTINEL_AMMO_COST is
    10 a shot) and enemy cooldowns are both unreadable, so a full-strength
    reading is usually unaffordable for them. That is the right shape for
    "can I survive the worst round" -- but do not treat it as an estimate.
    """
    total = 0
    for _bid, tpos, kind in visible_enemy_turrets(ct):
        if _reaches_core(ct, tpos, kind, footprint, aimed_only) is not None:
            total += TURRET_DAMAGE[kind]
    total += adjacent_enemy_builders(ct, footprint) * GameConstants.BUILDER_BOT_ATTACK_DAMAGE
    return total


def sustained_threat(ct, footprint) -> float:
    """Damage per round if everything in position fired as often as it could.

    Divides by fire cooldown, so a Sentinel counts 9/round rather than 18.
    Better than max_burst for "is this survivable over time" questions.
    """
    total = 0.0
    for _bid, tpos, kind in visible_enemy_turrets(ct):
        if _reaches_core(ct, tpos, kind, footprint, aimed_only=False) is not None:
            total += TURRET_DPR[kind]
    total += adjacent_enemy_builders(ct, footprint) * GameConstants.BUILDER_BOT_ATTACK_DAMAGE
    return total


def turret_records(ct, footprint, anchor: Position, limit: int = 4):
    """The most dangerous enemy turrets, as store-ready tuples.

    Ranked by damage first and proximity second, so the four that fit in the
    store are the four worth knowing about. Offsets are relative to the Core
    anchor and clamped to the 4-bit field; anything that can reach the Core is
    inside dist_sq 32 and fits comfortably.
    """
    scored = []
    for _bid, tpos, kind in visible_enemy_turrets(ct):
        facing = _reaches_core(ct, tpos, kind, footprint, aimed_only=False)
        if facing is None:
            continue
        dx, dy = tpos.x - anchor.x, tpos.y - anchor.y
        if not (-8 <= dx <= 7 and -8 <= dy <= 7):
            continue
        try:
            live = ct.get_direction(ct.get_tile_building_id(tpos))
        except GameError:
            live = facing
        idx = COMPASS.index(live) if live in COMPASS else 0
        scored.append(
            (TURRET_DAMAGE[kind], -(dx * dx + dy * dy),
             (dx, dy, kind == EntityType.SENTINEL, idx))
        )
    scored.sort(key=lambda s: (s[0], s[1]), reverse=True)
    return [s[2] for s in scored[:limit]]


class CoreMonitor:
    """Rolling hp history for the Core. One instance, owned by the Core.

    The Core keeps state across rounds for free -- its Player instance
    persists -- so the trend lives here rather than in the store. The store
    only carries what units OTHER than the Core cannot work out for
    themselves.
    """

    __slots__ = ("_hp", "_round", "healers_last_round")

    def __init__(self):
        self._hp: list[tuple[int, int]] = []   # (round, hp)
        self._round = -1
        self.healers_last_round = 0

    def observe(self, ct) -> None:
        r = ct.get_current_round()
        if r == self._round:
            return
        self._round = r
        self._hp.append((r, ct.get_hp()))
        if len(self._hp) > TREND_WINDOW + 1:
            self._hp.pop(0)

    @property
    def hp(self) -> int:
        return self._hp[-1][1] if self._hp else GameConstants.CORE_MAX_HP

    def dhp(self) -> float:
        """Mean hp change per round over the trend window.

        Negative means losing. Uses whatever history exists, so it is honest
        (if noisy) in the opening rounds rather than pretending to a full
        window it does not have.
        """
        if len(self._hp) < 2:
            return 0.0
        (r0, h0), (r1, h1) = self._hp[0], self._hp[-1]
        span = max(1, r1 - r0)
        return (h1 - h0) / span

    def gross_damage_last_round(self, healers: int) -> float:
        """Split the net hp change into healing and incoming damage.

        Only possible because the Builders report what they did. The timing
        lines up exactly: a Builder's write during round R is readable at R+1,
        and the Core's hp at its turn in R+1 also covers round R. Same window.
        """
        if len(self._hp) < 2:
            return 0.0
        delta = self._hp[-1][1] - self._hp[-2][1]
        return healers * GameConstants.HEAL_AMOUNT - delta

    def rounds_until_death(self, burst: int) -> float:
        """How many rounds of the current worst case the Core absorbs.

        The number that should actually decide heal-versus-build. Infinite
        when nothing is in position, which reads better than a large integer.
        """
        if burst <= 0:
            return float("inf")
        return self.hp / burst
