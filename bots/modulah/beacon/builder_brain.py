"""The Builder: read the Core's intel, act, report what it did.

The report is not bookkeeping. It is what lets the Core separate healing from
damage: the Core sees only a net hp change, and `net = heals - damage`. With
Builders declaring their heals, the Core recovers gross incoming damage, and
the timing lines up exactly -- a write during round R is readable at R+1, and
the Core's hp at its turn in R+1 also covers round R.

Priorities, in order:
  1. mend the Core when it is genuinely in trouble
  2. build the economy
  3. explore toward ore

"Genuinely in trouble" is deliberately a survival-time test rather than an
hp threshold. A Core at 300 hp with nothing in position is fine; a Core at 300
hp facing four aimed Sentinels is not, and only the second should pull every
Builder off the economy.
"""

from __future__ import annotations

import random

from fcode import Controller, Environment, GameConstants, GameError, Position

import comms
from geometry import CARDINALS, building_at, entity_type_of, in_bounds
from fcode import EntityType

# Below this many rounds of survival against the current worst case, Builders
# stop what they are doing and mend. Chosen so a Builder has time to reach the
# Core and land several heals before it matters, rather than arriving to watch
# it die with full cooldowns.
DANGER_ROUNDS = 12


class BuilderBrain:
    def __init__(self):
        self.slot = None
        self.harvester = None
        self.trail = None
        self.chain_done = False
        self.target = None

    def run(self, ct: Controller) -> None:
        round_no = ct.get_current_round()
        if self.slot is None:
            self.slot = comms.claim_builder_slot(ct, round_no)

        intel = self._read_intel(ct, round_no)
        action = self._act(ct, intel)

        ct.write_store(
            self.slot,
            comms.pack_builder(
                action,
                ct.get_hp(),
                round_no,
                target=(self.target.x, self.target.y) if self.target else None,
            ),
        )

    # --- intel --------------------------------------------------------------

    def _read_intel(self, ct: Controller, round_no: int) -> dict:
        """Everything the Core published, or safe defaults if it went quiet.

        A stale slot is treated as no information rather than as good news --
        if the Core stopped writing, something is very wrong, and defaulting
        to "no threat" would be exactly the wrong read.
        """
        threat_word = ct.read_store(comms.SLOT_CORE_THREAT)
        econ_word = ct.read_store(comms.SLOT_CORE_ECON)
        fresh = comms.is_fresh(threat_word, round_no)

        info = {"fresh": fresh, "hp": None, "dhp": 0, "burst": 0, "schedule": [], "turrets": []}
        if fresh:
            info.update(comms.unpack_threat(threat_word))
        if comms.is_fresh(econ_word, round_no):
            info["schedule"] = comms.unpack_econ(econ_word)
        for slot in (comms.SLOT_CORE_TURRET0, comms.SLOT_CORE_TURRET1):
            word = ct.read_store(slot)
            if comms.is_fresh(word, round_no):
                info["turrets"] += comms.unpack_turrets(word)
        return info

    @staticmethod
    def _core_in_danger(intel: dict) -> bool:
        if not intel["fresh"] or intel["hp"] is None:
            return False
        burst = intel["burst"]
        if burst <= 0:
            return False
        return intel["hp"] / burst < DANGER_ROUNDS

    # --- acting -------------------------------------------------------------

    def _act(self, ct: Controller, intel: dict) -> int:
        if self._core_in_danger(intel) and self._mend(ct):
            return comms.ACT_HEAL_CORE
        if self.harvester is None:
            return self._seek_ore(ct)
        if not self.chain_done:
            return self._lay_chain(ct)
        return comms.ACT_NONE

    def _mend(self, ct: Controller) -> bool:
        pos = ct.get_position()
        for d in CARDINALS:
            tile = pos.add(d)
            if not in_bounds(ct, tile):
                continue
            kind = entity_type_of(ct, building_at(ct, tile))
            if kind != EntityType.CORE:
                continue
            try:
                if ct.can_heal(tile):
                    ct.heal(tile)
                    return True
            except GameError:
                pass
            return False
        return self._step_toward(ct, self._core_tile(ct))

    def _core_tile(self, ct: Controller) -> Position | None:
        for tile in ct.get_nearby_tiles():
            kind = entity_type_of(ct, building_at(ct, tile))
            if kind == EntityType.CORE:
                try:
                    if ct.get_team(ct.get_tile_building_id(tile)) == ct.get_team():
                        return tile
                except GameError:
                    continue
        return None

    def _seek_ore(self, ct: Controller) -> int:
        pos = ct.get_position()
        for d in CARDINALS:
            tile = pos.add(d)
            if not in_bounds(ct, tile):
                continue
            try:
                if ct.get_tile_env(tile) == Environment.ORE_TITANIUM and ct.can_build_harvester(tile):
                    ct.build_harvester(tile)
                    self.harvester = tile
                    self.trail = pos
                    self.target = tile
                    return comms.ACT_BUILD_HARVESTER
            except GameError:
                continue

        ore = [t for t in ct.get_nearby_tiles() if self._is_free_ore(ct, t)]
        if ore:
            self.target = min(ore, key=lambda t: pos.distance_squared(t))
            if self._step_toward(ct, self.target):
                return comms.ACT_NONE
        return self._wander(ct)

    @staticmethod
    def _is_free_ore(ct: Controller, tile: Position) -> bool:
        try:
            return ct.get_tile_env(tile) == Environment.ORE_TITANIUM and building_at(ct, tile) is None
        except GameError:
            return False

    def _lay_chain(self, ct: Controller) -> int:
        """Lay conveyor along the tiles already walked, never ahead.

        Building only behind the Builder means a tile's facing is chosen after
        the next tile is known, so a bend gets a conveyor pointing around the
        corner instead of straight past it.
        """
        pos = ct.get_position()
        if self.trail is not None and self.trail != pos:
            core_dir = self._direction_to_core(ct, self.trail)
            if core_dir is not None:
                try:
                    if ct.can_build_conveyor(self.trail, core_dir):
                        ct.build_conveyor(self.trail, core_dir)
                except GameError:
                    pass
                self.chain_done = True
                return comms.ACT_BUILD_CONVEYOR
            facing = self.trail.cardinal_direction_to(pos)
            try:
                if ct.can_build_conveyor(self.trail, facing):
                    ct.build_conveyor(self.trail, facing)
                    self.trail = pos
                    return comms.ACT_BUILD_CONVEYOR
            except GameError:
                pass
            self.trail = pos

        target = self._core_tile(ct)
        if target is None or not self._step_toward(ct, target):
            self.chain_done = True
            return comms.ACT_BLOCKED
        return comms.ACT_NONE

    def _direction_to_core(self, ct: Controller, pos: Position):
        for d in CARDINALS:
            n = pos.add(d)
            if not in_bounds(ct, n):
                continue
            if entity_type_of(ct, building_at(ct, n)) == EntityType.CORE:
                return d
        return None

    # --- movement -----------------------------------------------------------

    def _step_toward(self, ct: Controller, target: Position | None) -> bool:
        if target is None:
            return False
        pos = ct.get_position()
        dx, dy = target.x - pos.x, target.y - pos.y
        preferred = []
        if dx:
            preferred.append(CARDINALS[1] if dx > 0 else CARDINALS[3])
        if dy:
            preferred.append(CARDINALS[2] if dy > 0 else CARDINALS[0])
        for d in preferred + list(CARDINALS):
            try:
                if ct.can_move(d):
                    if self.trail is not None:
                        self.trail = pos
                    ct.move(d)
                    return True
            except GameError:
                continue
        return False

    def _wander(self, ct: Controller) -> int:
        options = []
        for d in CARDINALS:
            try:
                if ct.can_move(d):
                    options.append(d)
            except GameError:
                continue
        if options:
            try:
                ct.move(random.choice(options))
            except GameError:
                pass
            return comms.ACT_NONE
        return comms.ACT_BLOCKED
