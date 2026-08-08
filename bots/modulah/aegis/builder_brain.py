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
import navigation
import placement
import roles
import situation
from geometry import (CARDINALS, COMPASS, building_at, entity_type_of,
                      enemy_core_guess, in_bounds, rear_corner)

# Keep this much banked so a cut route can be repaired. Turrets are worth
# more than a fourth Harvester, but neither is worth being unable to rebuild.
BUILD_RESERVE = 40

# Round from which a guard will put up the team's one Launcher.
LAUNCHER_FROM_ROUND = 25

# The opening Gunner: planted from where a Builder already stands, within
# these rounds, and only while enough is banked to keep the supply line going.
OPENING_TURRET_BY = 45
OPENING_TURRET_RESERVE = 120


class BuilderBrain:
    def __init__(self):
        self.slot = None
        self.commit: situation.Commitment | None = None
        self.harvester: Position | None = None
        self.trail: Position | None = None
        self._heading = None
        self._rear_corner = None
        self._core_anchor = None
        self._danger = set()
        self._opened = False

    def run(self, ct: Controller) -> None:
        r = ct.get_current_round()
        if self.slot is None:
            self.slot = comms.claim_builder_slot(ct, r)

        sit = situation.Situation(ct)
        if self._core_anchor is None:
            self._core_anchor = sit.core_tile or self._find_core(ct)
        intel = self._intel(ct, r)
        self._danger = self._reported_danger(ct, intel)
        role = self._role(ct, r, intel, sit)

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
        """Everything the Core published, not just the threat word.

        The turret map and the arrival schedule were being written and read by
        nobody. The Core is the only unit that can see them -- max Sentinel
        reach is dist_sq 32 against CORE_VISION_RADIUS_SQ 36, while a Builder
        sees radius ~4.5 -- so a Builder that ignores them is walking blind
        through ground the Core can describe exactly.
        """
        word = ct.read_store(comms.SLOT_CORE_THREAT)
        info = {"fresh": False, "hp": GameConstants.CORE_MAX_HP,
                "dhp": 0, "burst": 0, "income": 0, "enemy_hp": None,
                "turrets": []}
        if comms.is_fresh(word, r):
            info.update(comms.unpack_threat(word))
            info["fresh"] = True

        econ_word = ct.read_store(comms.SLOT_CORE_ECON)
        if comms.is_fresh(econ_word, r):
            arriving = comms.arrivals_from_now(econ_word, r)
            info["income"] = sum(arriving.values()) * GameConstants.STACK_SIZE
            info["enemy_hp"] = comms.unpack_enemy_core(econ_word)

        anchor = self._core_anchor
        for slot in (comms.SLOT_CORE_TURRET0, comms.SLOT_CORE_TURRET1):
            w = ct.read_store(slot)
            if not comms.is_fresh(w, r) or anchor is None:
                continue
            for rec in comms.unpack_turrets(w):
                idx = rec["facing"] % len(COMPASS)
                info["turrets"].append((
                    Position(anchor.x + rec["dx"], anchor.y + rec["dy"]),
                    EntityType.SENTINEL if rec["is_sentinel"] else EntityType.GUNNER,
                    COMPASS[idx],
                ))
        return info

    def _reported_danger(self, ct: Controller, intel: dict) -> set:
        """Tiles the Core says are covered, from turrets we cannot see ourselves.

        Uses the REPORTED facing, not all eight. Marking every facing paints a
        turret's whole neighbourhood lethal -- up to 36 tiles instead of 5 --
        and with several turrets that is most of the ground between us and the
        ore. Measured: titanium collected fell to 256 and only 1 game in 45
        survived, because Builders had nowhere they were willing to stand.
        Publishing the facing is the entire reason it is in the schema.
        """
        out = set()
        for tpos, kind, facing in intel.get("turrets", ()):
            try:
                for t in ct.get_attackable_tiles_from(tpos, facing, kind):
                    out.add((t.x, t.y))
            except GameError:
                continue
        return out

    def _role(self, ct: Controller, r: int, intel: dict, sit) -> int:
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
            harvesters=len(sit.my_harvesters),
            titanium=sit.titanium,
            round_no=r,
        )
        role = roles.assign(rank, mix)

        # A Builder part-way through a supply route finishes it. Reassigning
        # mid-chain strands the Harvester it already paid for and wastes every
        # conveyor laid so far, and on a 26x26 map the walk home is long
        # enough that this happened constantly: replay of a full-pool loss
        # showed 3 Harvesters and 10 conveyors against the opponent's 3 and
        # 31, i.e. chains started and abandoned rather than never begun.
        #
        # Overridden only when the Core is about to die, where there is no
        # later economy to protect.
        if (role != roles.ROLE_MINER
                and self.harvester is not None
                and intel["burst"] > 0
                and intel["hp"] / max(1, intel["burst"]) > roles.PANIC_ROUNDS):
            return roles.ROLE_MINER
        if role != roles.ROLE_MINER and self.harvester is not None and not intel["burst"]:
            return roles.ROLE_MINER
        return role

    def _visible_enemies(self, ct: Controller) -> list[int]:
        me = ct.get_team()
        out = []
        for eid in ct.get_nearby_entities():
            try:
                if ct.get_team(eid) != me:
                    out.append(eid)
            except GameError:
                continue
        return out

    def _visible_enemy_turret_ids(self, ct: Controller) -> list[int]:
        me = ct.get_team()
        out = []
        for bid in ct.get_nearby_buildings():
            try:
                if ct.get_team(bid) != me and ct.get_entity_type(bid) in (
                        EntityType.GUNNER, EntityType.SENTINEL):
                    out.append(bid)
            except GameError:
                continue
        return out

    def _friendly_launchers(self, ct: Controller) -> int:
        me = ct.get_team()
        n = 0
        for bid in ct.get_nearby_buildings():
            try:
                if ct.get_team(bid) == me and ct.get_entity_type(bid) == EntityType.LAUNCHER:
                    n += 1
            except GameError:
                continue
        return n

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
        if role == roles.ROLE_SIEGE:
            return self._siege(ct, sit, r)
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
        # Gunners by default, and Sentinels only against a confirmed firing
        # solution. A Sentinel's facing is PERMANENT -- can_rotate is
        # Gunner-only -- so one sited at a corridor the enemy does not use is
        # dead weight for the rest of the game. Measured: four Sentinels, 60
        # ammo, 8-11 visible targets, and zero shots fired in an entire match,
        # because betweenness aimed them at ground nobody walked.
        kind = EntityType.GUNNER
        base = GameConstants.GUNNER_BASE_COST
        if not sit.afford(base, BUILD_RESERVE):
            return self._mine(ct, sit, r)

        # Counter-battery first. A Gunner reaches 3 tiles; a Sentinel reaches
        # 5. An enemy sieging with Sentinels sits at range 5 and shells the
        # Core from outside anything a Gunner can answer -- which is why our
        # Gunners saw 8-11 targets and fired 8 shots in a whole match.
        #
        # A Sentinel is the right answer to an enemy turret specifically
        # because the target is a BUILDING and cannot move: its permanent
        # facing, which makes it dead weight against Builders, costs nothing
        # against something that will still be there in fifty rounds.
        if sit.enemy_turrets and sit.afford(GameConstants.SENTINEL_BASE_COST, BUILD_RESERVE):
            turret_ids = self._visible_enemy_turret_ids(ct)
            if turret_ids:
                def sentinel_ok(spot, facing):
                    try:
                        return ct.can_build_sentinel(spot, facing)
                    except GameError:
                        return False
                seat = placement.best_firing_seat(
                    ct, turret_ids, EntityType.SENTINEL, sentinel_ok, ct.get_position()
                )
                if seat is not None:
                    spot, facing, _ = seat
                    try:
                        ct.build_sentinel(spot, facing)
                        self.commit = None
                        return comms.ACT_BUILD_SENTINEL
                    except GameError:
                        pass

        # With enemies in sight, site against a real target the way steward
        # does. Betweenness is the answer to 'where before anyone arrives',
        # not to 'where now that they are here'.
        enemies = self._visible_enemies(ct)
        if enemies:
            def placeable_now(spot, facing):
                try:
                    return ct.can_build_gunner(spot, facing)
                except GameError:
                    return False
            seat = placement.best_firing_seat(
                ct, enemies, kind, placeable_now, ct.get_position()
            )
            if seat is not None:
                spot, facing, _ = seat
                try:
                    ct.build_gunner(spot, facing)
                    self.commit = None
                    return comms.ACT_BUILD_GUNNER
                except GameError:
                    pass

        # One Launcher first, from where we stand. It is the only thing on the
        # board that moves a Builder faster than walking -- dist_sq 26 in a
        # single round, over anything in between -- so unlike a turret it pays
        # back into the economy rather than only out of it. steward runs 1.7
        # of them; we ran none.
        if (self._friendly_launchers(ct) == 0
                and r >= LAUNCHER_FROM_ROUND
                and len(sit.my_harvesters) >= 1
                and sit.afford(GameConstants.LAUNCHER_BASE_COST, BUILD_RESERVE)):
            pos = ct.get_position()
            for d in CARDINALS:
                spot = pos.add(d)
                if not in_bounds(ct, spot) or building_at(ct, spot) is not None:
                    continue
                try:
                    if ct.can_build_launcher(spot):
                        ct.build_launcher(spot)
                        return comms.ACT_NONE
                except GameError:
                    continue

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
            if ct.can_build_gunner(spot, facing):
                ct.build_gunner(spot, facing)
                self.commit = None
                return comms.ACT_BUILD_GUNNER
        except GameError:
            pass

        if not self._step(ct, spot, r):
            self.commit = None
        return comms.ACT_NONE

    def _siege(self, ct: Controller, sit, r: int) -> int:
        """Put a turret on the enemy Core and leave it there.

        The enemy Core is a 2x2 building that cannot move, so a turret aimed
        at it keeps paying for the rest of the game -- the one target where a
        Sentinel's permanent facing costs nothing. Its position needs no
        scouting: every official map is rotationally symmetric, so it is our
        own Core mirrored about the map centre, known at round 0.
        """
        foot = self._footprint(ct, sit)
        if not foot:
            return self._mine(ct, sit, r)
        enemy = sit.enemy_core or enemy_core_guess(ct, foot)

        kind = EntityType.GUNNER
        base = GameConstants.GUNNER_BASE_COST
        if sit.afford(GameConstants.SENTINEL_BASE_COST, BUILD_RESERVE):
            kind, base = EntityType.SENTINEL, GameConstants.SENTINEL_BASE_COST
        if not sit.afford(base, BUILD_RESERVE):
            return self._mine(ct, sit, r)

        def tile_ok(spot, facing):
            try:
                return ct.get_tile_env(spot).name != "WALL"
            except GameError:
                return False

        pos = ct.get_position()
        if pos.distance_squared(enemy) > 64:
            # Still crossing the map; nothing to site yet.
            self._march(ct, enemy, r)
            return comms.ACT_NONE

        seat = placement.siege_seat(ct, enemy, kind, tile_ok, pos)
        if seat is None:
            self._march(ct, enemy, r)
            return comms.ACT_NONE
        spot, facing, _ = seat
        try:
            build = (ct.can_build_sentinel if kind == EntityType.SENTINEL
                     else ct.can_build_gunner)
            if build(spot, facing):
                if kind == EntityType.SENTINEL:
                    ct.build_sentinel(spot, facing)
                else:
                    ct.build_gunner(spot, facing)
                return (comms.ACT_BUILD_SENTINEL if kind == EntityType.SENTINEL
                        else comms.ACT_BUILD_GUNNER)
        except GameError:
            pass
        self._march(ct, spot, r)
        return comms.ACT_NONE

    def _march(self, ct: Controller, goal: Position, r: int) -> None:
        """Cross the map toward goal, preferring tiles nothing is aiming at."""
        try:
            avoid = placement.enemy_covered_tiles(ct)
        except GameError:
            avoid = set()
        d = navigation.step_toward(ct, goal, avoid)
        if d is None:
            return
        try:
            ct.move(d)
        except GameError:
            pass

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
            target = sit.nearest_free_ore(pos, self._rear(ct, sit))
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
                    if d is not None:
                        # That segment fed the Core, so this route is finished.
                        # Release the Builder to open another deposit -- it
                        # used to keep calling _lay forever, which capped the
                        # whole team at one Harvester per Builder and left us
                        # losing tiebreaks we had survived to reach.
                        self.harvester = None
                        self.trail = None
                        self.commit = None
                    return comms.ACT_BUILD_CONVEYOR
            except GameError:
                pass
            self.trail = pos
        if core is not None and self._step(ct, core, r):
            return comms.ACT_NONE
        return comms.ACT_BLOCKED

    # --- helpers -------------------------------------------------------------

    def _rear(self, ct: Controller, sit) -> Position | None:
        """Cached rear footprint corner -- the rotation-safe anchor."""
        if self._rear_corner is None:
            foot = self._footprint(ct, sit)
            if foot:
                self._rear_corner = rear_corner(foot, enemy_core_guess(ct, foot))
        return self._rear_corner

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
        """Move one tile toward target, preferring tiles nothing is aiming at.

        Builders were walking straight down enemy firing lanes and dying:
        traced 3 units -> 1 by round 32 against steward, which then had a free
        run at the Core. Turrets are line weapons, so a lane is a handful of
        tiles and stepping around one usually costs nothing at all -- the
        avoidance is a preference, not a refusal, so a Builder still moves when
        every option is covered rather than standing still and dying anyway.
        """
        pos = ct.get_position()
        dx, dy = target.x - pos.x, target.y - pos.y
        pref = []
        if dx:
            pref.append(CARDINALS[1] if dx > 0 else CARDINALS[3])
        if dy:
            pref.append(CARDINALS[2] if dy > 0 else CARDINALS[0])

        try:
            unsafe = placement.enemy_covered_tiles(ct)
        except GameError:
            unsafe = set()
        # Plus the rays the Core reported for turrets this Builder cannot see.
        unsafe = unsafe | self._danger

        order = pref + [d for d in CARDINALS if d not in pref]
        if unsafe:
            safe = [d for d in order if (pos.add(d).x, pos.add(d).y) not in unsafe]
            order = safe + [d for d in order if d not in safe]

        for d in order:
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
