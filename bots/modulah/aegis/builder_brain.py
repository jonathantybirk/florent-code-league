"""Builders: take a role from the team picture, then act on rechecked facts.

The role comes from lib/roles, which reads the Core's published threat rather
than each Builder's own narrow view -- a Builder cannot see what is shooting
the Core (radius ~4.5 against a Sentinel's reach of dist_sq 32), so a Builder
deciding locally whether to mend is deciding blind.

Every task runs through a Commitment. A Builder that walks to a deposit
rechecks each turn that the deposit is still free, and abandons anything that
has not made progress in STALL_ROUNDS. That is aimed squarely at the failure
the steward lineage measured on itself: 18% of its long-lived Builders spend
their last sixty rounds bouncing between three tiles.
"""

from __future__ import annotations

from fcode import Controller, EntityType, GameConstants, GameError, Position

import comms
import placement
import roles
import situation
from geometry import CARDINALS, building_at, entity_type_of, in_bounds

# Keep this much banked so a cut route can be repaired. Turrets are worth
# more than a fourth Harvester, but neither is worth being unable to rebuild.
BUILD_RESERVE = 40


class BuilderBrain:
    def __init__(self):
        self.slot = None
        self.commit: situation.Commitment | None = None
        self.harvester: Position | None = None
        self.trail: Position | None = None
        self._heading = None

    def run(self, ct: Controller) -> None:
        r = ct.get_current_round()
        if self.slot is None:
            self.slot = comms.claim_builder_slot(ct, r)

        sit = situation.Situation(ct)
        intel = self._intel(ct, r)
        role = self._role(ct, r, intel)

        if self.commit is not None:
            if self.commit.stalled(r) or not self.commit.still_valid(ct, sit):
                self.commit = None

        action = self._act(ct, sit, intel, role, r)

        ct.write_store(
            self.slot,
            comms.pack_builder(
                action, ct.get_hp(), r,
                target=(self.commit.target.x, self.commit.target.y)
                if self.commit and self.commit.target else None,
            ),
        )

    # --- team picture --------------------------------------------------------

    def _intel(self, ct: Controller, r: int) -> dict:
        word = ct.read_store(comms.SLOT_CORE_THREAT)
        info = {"fresh": False, "hp": GameConstants.CORE_MAX_HP,
                "dhp": 0, "burst": 0}
        if comms.is_fresh(word, r):
            info.update(comms.unpack_threat(word))
            info["fresh"] = True
        return info

    def _role(self, ct: Controller, r: int, intel: dict) -> int:
        """Rank among live Builders decides which slice of the mix we take.

        Rank is derived from the store rather than negotiated, because the
        store is a round behind and Builders cannot agree on anything within a
        round. Every Builder computes the same ordering from the same
        snapshot, so the roles partition cleanly.
        """
        live = [s for s in comms.BUILDER_SLOTS if comms.is_fresh(ct.read_store(s), r)]
        if self.slot not in live:
            live.append(self.slot)
        # Dense rank: position among live slots, so ranks run 0..n-1 and the
        # mix actually reaches everybody. The fixed BUILDER_SLOTS index looks
        # more stable but is wrong -- slots are claimed scattered, so a
        # Builder holding slot 9 ranked 5 and never fell inside a two-role
        # mix. Traced: every Builder read MINER at dhp=-16 with no turret on
        # the board.
        #
        # This is what thrashed before; the cause was the population growing
        # five Builders in five rounds, which spawn pacing has since fixed.
        live.sort()
        rank = live.index(self.slot)
        mix = roles.desired_mix(
            len(live), intel["hp"], GameConstants.CORE_MAX_HP,
            intel["burst"], intel["dhp"],
            friendly_turrets=self._friendly_turrets(ct),
        )
        return roles.assign(rank, mix)

    def _friendly_turrets(self, ct: Controller) -> int:
        me = ct.get_team()
        n = 0
        for bid in ct.get_nearby_buildings():
            try:
                if ct.get_team(bid) == me and ct.get_entity_type(bid) in (
                        EntityType.GUNNER, EntityType.SENTINEL):
                    n += 1
            except GameError:
                continue
        return n

    # --- acting --------------------------------------------------------------

    def _act(self, ct, sit, intel, role, r) -> int:
        if role == roles.ROLE_MENDER:
            return self._mend(ct, sit, r)
        if role == roles.ROLE_GUARD:
            return self._guard(ct, sit, r)
        return self._mine(ct, sit, r)

    def _mend(self, ct: Controller, sit, r: int) -> int:
        core = sit.core_tile or self._find_core(ct)
        if core is None:
            return self._mine(ct, sit, r)
        pos = ct.get_position()
        for d in CARDINALS:
            tile = pos.add(d)
            if not in_bounds(ct, tile):
                continue
            if entity_type_of(ct, building_at(ct, tile)) != EntityType.CORE:
                continue
            try:
                if ct.can_heal(tile):
                    ct.heal(tile)
                    return comms.ACT_HEAL_CORE
            except GameError:
                pass
            return comms.ACT_NONE  # in position, nothing to mend this turn
        self._step(ct, core, r)
        return comms.ACT_NONE

    def _guard(self, ct: Controller, sit, r: int) -> int:
        """Site a home turret on the approach carrying the most attacker traffic.

        Split into "where should a turret stand" and "can I build it from here",
        because can_build_gunner bundles both and the Builder is almost never
        already standing next to the best seat. Asking the bundled question
        rejected every good site and silently fell through to mining -- the bot
        banked 400 titanium while its Core died with no turret on the board.
        """
        kind = EntityType.GUNNER
        base = GameConstants.GUNNER_BASE_COST
        if sit.enemy_turrets and sit.afford(GameConstants.SENTINEL_BASE_COST, BUILD_RESERVE):
            kind, base = EntityType.SENTINEL, GameConstants.SENTINEL_BASE_COST
        if not sit.afford(base, BUILD_RESERVE):
            return self._mine(ct, sit, r)

        foot = self._footprint(ct, sit)
        if not foot:
            core = self._find_core(ct)
            if core is not None:
                self._step(ct, core, r)
                return comms.ACT_NONE
            return self._mine(ct, sit, r)

        # Tile-level legality only: empty, in bounds, not a wall. Builder
        # adjacency is checked at build time, once we have walked there.
        def placeable(spot, facing):
            try:
                if building_at(ct, spot) is not None:
                    return False
                return ct.get_tile_env(spot).name != "WALL"
            except GameError:
                return False

        # Hold the chosen seat across turns; re-scoring every round makes the
        # Builder chase a moving target and never arrive.
        if not (self.commit and self.commit.kind == "turret" and self.commit.target
                and building_at(ct, self.commit.target) is None):
            site = placement.best_defensive_site(ct, foot, kind, placeable)
            if site is None:
                return self._mine(ct, sit, r)
            self.commit = situation.Commitment("turret", site[0], r)
            self._facing = site[1]

        spot = self.commit.target
        facing = getattr(self, "_facing", None)
        if facing is None:
            self.commit = None
            return self._mine(ct, sit, r)

        try:
            build = (ct.can_build_sentinel if kind == EntityType.SENTINEL
                     else ct.can_build_gunner)
            if build(spot, facing):
                if kind == EntityType.SENTINEL:
                    ct.build_sentinel(spot, facing)
                else:
                    ct.build_gunner(spot, facing)
                self.commit = None
                return (comms.ACT_BUILD_SENTINEL if kind == EntityType.SENTINEL
                        else comms.ACT_BUILD_GUNNER)
        except GameError:
            pass

        if not self._step(ct, spot, r):
            self.commit = None
        return comms.ACT_NONE

    def _mine(self, ct: Controller, sit, r: int) -> int:
        if self.harvester is not None and not situation.harvester_is_connected(ct, self.harvester):
            # The route died, or was never finished. Relaying beats mining
            # into a dead end -- this is the recheck whose absence retired
            # deposits permanently in the steward lineage.
            #
            # Do NOT reset trail here. Trail is the tile we last stood on and
            # is what _lay builds on; re-anchoring it to the current position
            # every turn makes trail == pos permanently and the build branch
            # unreachable, which is why this bot mined literally zero.
            if self.trail is None:
                self.trail = ct.get_position()
            return self._lay(ct, r)

        if self.harvester is None:
            pos = ct.get_position()
            for d in CARDINALS:
                tile = pos.add(d)
                if not in_bounds(ct, tile):
                    continue
                try:
                    if (ct.get_tile_env(tile).name == "ORE_TITANIUM"
                            and sit.afford(GameConstants.HARVESTER_BASE_COST, BUILD_RESERVE)
                            and ct.can_build_harvester(tile)):
                        ct.build_harvester(tile)
                        self.harvester, self.trail = tile, pos
                        self.commit = situation.Commitment("build", None, r)
                        return comms.ACT_BUILD_HARVESTER
                except GameError:
                    continue
            target = sit.nearest_free_ore(pos)
            if target is not None:
                if self.commit is None or self.commit.kind != "ore":
                    self.commit = situation.Commitment("ore", target, r)
                if self._step(ct, target, r):
                    return comms.ACT_NONE
            return self._wander(ct)
        return self._lay(ct, r)

    def _lay(self, ct: Controller, r: int) -> int:
        """Extend the conveyor behind us, so bends get the right facing."""
        pos = ct.get_position()
        core = self._find_core(ct)
        if self.trail is not None and self.trail != pos:
            d = self._core_dir(ct, self.trail)
            facing = d if d is not None else self.trail.cardinal_direction_to(pos)
            try:
                if ct.can_build_conveyor(self.trail, facing):
                    ct.build_conveyor(self.trail, facing)
                    self.trail = pos
                    if self.commit:
                        self.commit.progressed(r)
                    return comms.ACT_BUILD_CONVEYOR
            except GameError:
                pass
            self.trail = pos
        if core is not None and self._step(ct, core, r):
            return comms.ACT_NONE
        return comms.ACT_BLOCKED

    # --- helpers -------------------------------------------------------------

    def _footprint(self, ct: Controller, sit) -> list[Position]:
        core = sit.core_tile or self._find_core(ct)
        if core is None:
            return []
        out = []
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                p = Position(core.x + dx, core.y + dy)
                if in_bounds(ct, p) and entity_type_of(ct, building_at(ct, p)) == EntityType.CORE:
                    out.append(p)
        return out

    def _find_core(self, ct: Controller) -> Position | None:
        me = ct.get_team()
        for bid in ct.get_nearby_buildings():
            try:
                if ct.get_team(bid) == me and ct.get_entity_type(bid) == EntityType.CORE:
                    return ct.get_position(bid)
            except GameError:
                continue
        return None

    def _core_dir(self, ct: Controller, pos: Position):
        for d in CARDINALS:
            n = pos.add(d)
            if in_bounds(ct, n) and entity_type_of(ct, building_at(ct, n)) == EntityType.CORE:
                return d
        return None

    def _step(self, ct: Controller, target: Position, r: int) -> bool:
        pos = ct.get_position()
        dx, dy = target.x - pos.x, target.y - pos.y
        pref = []
        if dx:
            pref.append(CARDINALS[1] if dx > 0 else CARDINALS[3])
        if dy:
            pref.append(CARDINALS[2] if dy > 0 else CARDINALS[0])
        for d in pref + list(CARDINALS):
            try:
                if ct.can_move(d):
                    if self.trail is not None:
                        self.trail = pos
                    ct.move(d)
                    if self.commit:
                        self.commit.progressed(r)
                    return True
            except GameError:
                continue
        return False

    def _wander(self, ct: Controller) -> int:
        """Explore by holding a heading until it fails.

        Taking the first legal cardinal every turn is not exploration -- it is
        a Builder walking north until it finds a wall and then vibrating
        against it, which is exactly how a bot mines 70 titanium in 1000
        rounds. Committing to a heading and only re-rolling when it is blocked
        covers ground, and re-rolling deterministically off the unit id keeps
        two Builders from picking the same one.
        """
        if self._heading is not None:
            try:
                if ct.can_move(self._heading):
                    ct.move(self._heading)
                    return comms.ACT_NONE
            except GameError:
                pass
        order = list(CARDINALS)
        start = (ct.get_id() + ct.get_current_round()) % len(order)
        for i in range(len(order)):
            d = order[(start + i) % len(order)]
            try:
                if ct.can_move(d):
                    self._heading = d
                    ct.move(d)
                    return comms.ACT_NONE
            except GameError:
                continue
        self._heading = None
        return comms.ACT_BLOCKED
