# GENERATED from bots/modulah/lib/situation.py -- edit that file, not this copy.
"""The facts a unit should check before deciding anything.

Most bad bot behaviour is not a bad decision. It is a decision made against an
assumption that stopped being true and was never rechecked: walking to a
deposit another Builder already took, feeding a Harvester whose route was cut
twenty rounds ago, mending a Core nothing is shooting at, or retrying the same
illegal build every round for the rest of the game.

The steward lineage has both failure modes on record. A Harvester shot out of
sight "retired its deposit forever", and fixing that recheck was what turned
late economic expansion from -9pp into +2.0pp -- the expansion was never the
problem, the stale assumption was. Separately, 18% of its long-lived Builders
spend their last sixty rounds bouncing between three tiles.

So this module answers two kinds of question:

  * **State** -- is the economy actually alive, is there free ore, what is the
    enemy showing us. Computed once per turn and passed around, rather than
    each brain re-deriving it from raw Controller calls.
  * **Commitment** -- what did this unit decide to do, how long has it been
    trying, and is the reason it decided still true. A commitment that stops
    validating is dropped rather than pursued.
"""

from __future__ import annotations

from fcode import Controller, Environment, EntityType, GameConstants, GameError, Position

from geometry import CARDINALS, building_at, entity_type_of, in_bounds

# A commitment that has not made progress in this many rounds is abandoned.
# Short, because the cost of re-deciding is one turn and the cost of a Builder
# stuck for the rest of the game is the Builder.
STALL_ROUNDS = 8


class Situation:
    """A turn's worth of read-only facts about our position.

    Built once per unit per turn. Every field is derived from what this unit
    can actually see -- there is no shared world model, because a Builder's
    vision is radius ~4.5 and pretending otherwise is how assumptions go stale.
    """

    __slots__ = (
        "round", "team", "titanium", "ammo", "scale",
        "my_harvesters", "free_ore", "enemy_builders", "enemy_turrets",
        "enemy_core", "enemy_core_hp", "core_tile",
    )

    def __init__(self, ct: Controller):
        self.round = ct.get_current_round()
        self.team = ct.get_team()
        self.titanium = ct.get_global_resources()
        self.ammo = ct.get_global_ammo()
        try:
            self.scale = ct.get_scale_percent()
        except GameError:
            self.scale = 0.0

        self.my_harvesters: list[Position] = []
        self.enemy_builders: list[Position] = []
        self.enemy_turrets: list[tuple[Position, EntityType]] = []
        self.enemy_core: Position | None = None
        self.enemy_core_hp: int | None = None
        self.core_tile: Position | None = None

        self._scan(ct)
        self.free_ore = self._free_ore(ct)

    def _scan(self, ct: Controller) -> None:
        for bid in ct.get_nearby_buildings():
            try:
                kind = ct.get_entity_type(bid)
                pos = ct.get_position(bid)
                mine = ct.get_team(bid) == self.team
            except GameError:
                continue
            if mine:
                if kind == EntityType.HARVESTER:
                    self.my_harvesters.append(pos)
                elif kind == EntityType.CORE and self.core_tile is None:
                    self.core_tile = pos
            else:
                if kind in (EntityType.GUNNER, EntityType.SENTINEL):
                    self.enemy_turrets.append((pos, kind))
                elif kind == EntityType.CORE:
                    self.enemy_core = pos
                    try:
                        self.enemy_core_hp = ct.get_hp(bid)
                    except GameError:
                        pass
        for eid in ct.get_nearby_entities():
            try:
                if ct.get_team(eid) == self.team:
                    continue
                if ct.get_entity_type(eid) == EntityType.BUILDER_BOT:
                    self.enemy_builders.append(ct.get_position(eid))
            except GameError:
                continue

    def _free_ore(self, ct: Controller) -> list[Position]:
        """Ore tiles with nothing built on them.

        "Free" is checked every turn rather than remembered. A deposit taken by
        a teammate, or one whose Harvester just died, both look the same to a
        cached list and neither is what it says.
        """
        out = []
        for tile in ct.get_nearby_tiles():
            try:
                if ct.get_tile_env(tile) != Environment.ORE_TITANIUM:
                    continue
            except GameError:
                continue
            if building_at(ct, tile) is None:
                out.append(tile)
        return out

    # --- derived questions --------------------------------------------------

    @property
    def under_attack(self) -> bool:
        return bool(self.enemy_turrets) or bool(self.enemy_builders)

    def afford(self, base_cost: int, reserve: int = 0) -> bool:
        """Can we pay the SCALED price and still keep `reserve` banked?

        Base costs are the wrong number to compare against: every building
        raises the price of the next, so a bot budgeting off base cost
        gradually starts believing it can afford things it cannot.
        """
        price = int(base_cost * (1.0 + self.scale / 100.0))
        return self.titanium >= price + reserve

    def nearest_free_ore(self, pos: Position) -> Position | None:
        if not self.free_ore:
            return None
        return min(self.free_ore, key=lambda t: pos.distance_squared(t))


def harvester_is_connected(ct: Controller, harvester: Position) -> bool:
    """Does this Harvester have somewhere to put its titanium?

    A Harvester with no adjacent conveyor accepting from it is mining into
    nothing. That is the stale assumption that cost the steward lineage its
    late expansion: the deposit looks worked, the economy reads healthy, and no
    titanium has moved for fifty rounds.

    Only checks the first hop -- the Core's econ walk covers the rest of the
    route, and a Builder cannot see far enough to verify more than this.
    """
    for d in CARDINALS:
        n = harvester.add(d)
        if not in_bounds(ct, n):
            continue
        kind = entity_type_of(ct, building_at(ct, n))
        if kind in (EntityType.CONVEYOR, EntityType.SPLITTER, EntityType.CORE):
            return True
    return False


class Commitment:
    """What this unit is trying to do, and whether it is still working.

    A unit sets a commitment with the reason it made sense. Each turn the
    reason is rechecked and progress is measured; a commitment that stops
    validating, or that stops making progress, is dropped so the unit decides
    again rather than grinding.
    """

    __slots__ = ("kind", "target", "since", "last_progress", "_mark")

    def __init__(self, kind: str, target: Position | None, round_no: int, mark=None):
        self.kind = kind
        self.target = target
        self.since = round_no
        self.last_progress = round_no
        self._mark = mark

    def progressed(self, round_no: int) -> None:
        self.last_progress = round_no

    def stalled(self, round_no: int) -> bool:
        return round_no - self.last_progress >= STALL_ROUNDS

    def still_valid(self, ct: Controller, sit: Situation) -> bool:
        """Is the reason this was chosen still true?

        Deliberately conservative: anything not explicitly understood is
        treated as still valid, so a new commitment kind fails towards
        "keep going" rather than towards thrashing.
        """
        if self.target is None:
            return True
        if self.kind == "ore":
            # Someone may have taken it, or it may have been a stale sighting.
            return any(
                t.x == self.target.x and t.y == self.target.y for t in sit.free_ore
            ) or building_at(ct, self.target) is None
        if self.kind == "build":
            return building_at(ct, self.target) is None
        return True
