"""Slot ownership, liveness, and per-round decode of the whole store.

Every unit runs its own SlotRegistry instance.  All inputs are common
knowledge — the store snapshot, the global round number, and the protocol's
fixed conventions — so every instance converges on the same picture without
any extra messages.

Round bookkeeping (writes in round T are readable in the round-T+1 snapshot):
  - an ASSIGN decoded in snapshot T   =>  round T is the resync round: every
    unit writes its absolute position; snapshot T+1 decodes as RESYNC format;
  - rounds T+1 .. T+ONBOARD_ROUNDS are the onboarding window: the Core streams
    absolute-coordinate chains through its own slot and all turret/launcher
    slots (speaker=1); those turrets stay silent and are exempt from liveness
    reclamation; snapshots T+2 .. T+W+1 decode those slots as ONBOARD format.
  - the Core must not spawn (and therefore not ASSIGN) while a resync or
    onboarding window is active, so the formats never overlap.

Liveness: a live owner's slot value differs every round it is scheduled to
write.  An unchanged value on a scheduled round means the owner is dead and
the slot is reclaimed immediately.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import messages
from .messages import ControlEvent, Fact
from . import protocol as P
from .protocol import (
    BUILDER_SLOTS_FROM,
    CTRL_ASSIGN,
    CTRL_GRANT,
    CTRL_SYMMETRY,
    GRANT_KINDS,
    TAKEOVER_GRACE,
    SLOT_CORE,
    STATE_CODE,
    TURRET_RESERVED_SLOTS,
)

_MOVE_DELTAS = {1: (0, -1), 2: (1, 0), 3: (0, 1), 4: (-1, 0)}   # N, E, S, W
_EIGHT = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")



@dataclass
class Owner:
    kind: str                                # builder_bot / gunner / sentinel / launcher / core
    spawn_round: int
    pos: tuple[int, int] | None = None       # dead-reckoned (builders) or fixed
    facing: int | None = None                # eight-direction index (turrets)
    period: int = 1                          # round-robin: write when
    phase: int = 0                           #   round % period == phase
    has_written: bool = False                # liveness diff starts after this


@dataclass
class RoundResult:
    """Everything the store said this round, for the caller to apply."""
    facts: list[Fact] = field(default_factory=list)
    events: list[tuple[int, ControlEvent]] = field(default_factory=list)  # (slot, ev)
    core_hp: int | None = None
    deaths: list[int] = field(default_factory=list)                       # slots
    assigned_slot: int | None = None    # set on the round OUR unit learns its slot
    # grants that lost a same-snapshot collision: (sender slot, args); the
    # sender re-grants with a fresh pick
    lost_grants: list[tuple[int, tuple]] = field(default_factory=list)
    # per-slot decode detail (for tooling/visualisation): slot -> dict with
    # raw, changed, format, facts, move/turn/aux, events
    per_slot: dict[int, dict] = field(default_factory=dict)


class SlotRegistry:
    def __init__(self, map_w: int, map_h: int):
        self.map_w = map_w
        self.map_h = map_h
        # slot 0 is the Core's by convention, so every registry starts with it
        self.owners: dict[int, Owner] = {SLOT_CORE: Owner("core", 0)}
        self.prev_snapshot: list[int] | None = None
        self.core_hp: int = 500
        # windows (rounds, inclusive) derived from decoded ASSIGNs
        self.resync_write_round: int | None = None      # round whose WRITES are resync
        self.onboard_until: int | None = None           # last onboarding write-round
        # the Core's per-slot model of what each unit already knows
        self.known: dict[int, set[tuple[int, int]]] = {}
        self.symmetry_heard: bool = False       # a SYMMETRY has been on the store
        # set by a turret/launcher that has no slot yet: unknown-owner slots
        # are then read speculatively as builder messages, keeping only a
        # GRANT that names this exact tile (builders are the only granters)
        self.grant_probe_pos: tuple[int, int] | None = None

    # ------------------------------------------------------------------
    # per-round decode of the whole store
    # ------------------------------------------------------------------
    def absorb_snapshot(self, snapshot: list[int], round_no: int) -> RoundResult:
        """Decode all 16 slots of this round's snapshot (writes of round_no-1).

        Call exactly once per unit per round, before deciding what to write.
        """
        result = RoundResult()
        wrote_round = round_no - 1
        resync = self.is_resync_round(wrote_round)
        onboard = self._in_onboard_window(wrote_round)

        self._grants: list[tuple[int, tuple]] = []      # (sender slot, args)
        for slot in range(P.GCS_SLOTS):
            value = snapshot[slot]
            prev = self.prev_snapshot[slot] if self.prev_snapshot else None
            detail = {"raw": value, "changed": prev is not None and value != prev,
                      "format": "-",
                      "facts": [], "events": []}
            result.per_slot[slot] = detail
            n_facts, n_events = len(result.facts), len(result.events)
            try:
                self._absorb_slot(slot, value, wrote_round, resync, onboard, result, detail)
            except ValueError as exc:                       # decision 7: never raise
                detail["format"] = f"undecodable: {exc}"
                print(f"[GCS] slot {slot} round {round_no}: undecodable ({exc})")
            detail["facts"] = [(f.x, f.y, f.state) for f in result.facts[n_facts:]]
            detail["events"] = [(ev.kind, list(ev.args)) for _, ev in result.events[n_events:]]

        self._settle_grants(wrote_round, result)
        self._liveness(snapshot, wrote_round, resync, onboard, result)
        self._apply_windows(result, wrote_round)
        self.prev_snapshot = list(snapshot)

        for f in result.facts:                              # feed the knowledge model
            for known in self.known.values():
                known.add((f.x, f.y))
        return result

    def _absorb_slot(self, slot, value, wrote_round, resync, onboard, result, detail):
        raw_kind, raw_detail = messages.classify_raw(value)
        if raw_kind == "core_hp":
            detail["format"] = f"core_hp={raw_detail}"
            if slot == SLOT_CORE:
                self.core_hp = raw_detail
                result.core_hp = raw_detail
            return
        if raw_kind in ("idle", "free"):
            detail["format"] = raw_kind
            return
        owner = self.owners.get(slot)
        prev = self.prev_snapshot[slot] if self.prev_snapshot else None
        if value == prev:
            detail["format"] = "stale"
            return                       # unchanged: stale content, nothing new

        if onboard and slot == SLOT_CORE:
            detail["format"] = "onboard"
            decoded = messages.decode_onboard(value, self.map_w, self.map_h, False)
            result.facts.extend(decoded.facts)
            return
        if onboard and owner is not None and owner.kind not in ("builder_bot", "core"):
            detail["format"] = "onboard(borrowed)"
            decoded = messages.decode_onboard(value, self.map_w, self.map_h, True)
            result.facts.extend(decoded.facts)
            return

        if resync:
            # self-describing: position + kind, so even a slot we have never
            # heard of becomes a known owner
            detail["format"] = "resync"
            decoded = messages.decode_resync(value, self.map_w, self.map_h)
            if owner is None or owner.kind != decoded.kind:
                owner = Owner(decoded.kind, spawn_round=wrote_round)
                self.owners[slot] = owner
                self.known.setdefault(slot, set())
            owner.pos = decoded.position
            owner.has_written = True
            detail["position"] = decoded.position
            result.facts.extend(decoded.facts)
            return

        if owner is None:
            # a slot whose owner we have not learned yet cannot be interpreted
            # safely — skip until the next resync round tells us
            detail["format"] = "empty" if value == 0 else "unknown owner"
            if value and self.grant_probe_pos is not None:
                self._probe_grant(slot, value, wrote_round, result, detail)
            return

        # standard format — dead-reckon builders before resolving FOV indices
        if owner.kind == "builder_bot" and owner.pos is not None:
            move = messages.peek_move(owner.kind, value)
            if move in _MOVE_DELTAS:
                dx, dy = _MOVE_DELTAS[move]
                owner.pos = (owner.pos[0] + dx, owner.pos[1] + dy)
        pos_known = owner.pos is not None
        decoded = messages.decode_standard(owner.kind, value,
                                           owner.pos if pos_known else (0, 0),
                                           self.map_w, self.map_h)
        owner.has_written = True
        detail["format"] = "standard" + ("" if pos_known else " (pos unknown)")
        detail["move"], detail["turn"], detail["aux"] = decoded.move, decoded.turn, decoded.aux
        if not pos_known:
            # FOV-relative facts can't be resolved without the sender's
            # position; control events and REMOTE facts (absolute) survive.
            decoded.facts.clear()
        if owner.kind == "gunner" and decoded.turn and owner.facing is not None:
            owner.facing = (owner.facing + (1 if decoded.turn == 1 else -1)) % 8
        result.facts.extend(decoded.facts)
        for ev in decoded.events:
            result.events.append((slot, ev))
            if ev.kind == CTRL_ASSIGN and slot == SLOT_CORE:
                self._on_assign(ev, wrote_round)
            elif ev.kind == CTRL_SYMMETRY:
                self.symmetry_heard = True
            elif ev.kind == CTRL_GRANT:
                self._grants.append((slot, ev.args))

    def _settle_grants(self, wrote_round, result):
        """Apply this snapshot's GRANTs.  Two builders may have picked the
        same free slot in the same round; everyone resolves it identically:
        the grant from the lowest sender slot stands, the others are lost
        and their senders re-grant."""
        taken: dict[int, int] = {}
        for sender, args in sorted(self._grants, key=lambda g: g[0]):
            x, y, gslot, gkind, facing = args
            if gslot in taken:
                result.lost_grants.append((sender, args))
                continue
            taken[gslot] = sender
            self.owners[gslot] = Owner(GRANT_KINDS[gkind], spawn_round=wrote_round,
                                       pos=(x, y), facing=(facing - 1) if facing else None)
            self.known.setdefault(gslot, set())

    def _probe_grant(self, slot, value, wrote_round, result, detail):
        """We are a slotless turret: read an unknown slot as a builder message
        and take a GRANT for our own tile if there is one."""
        try:
            decoded = messages.decode_standard("builder_bot", value, (0, 0),
                                               self.map_w, self.map_h)
        except ValueError:
            return
        for ev in decoded.events:
            if ev.kind != CTRL_GRANT:
                continue
            x, y, gslot, gkind, facing = ev.args
            plausible = (0 <= x < self.map_w and 0 <= y < self.map_h and gkind < len(GRANT_KINDS)
                         and facing <= 8 and SLOT_CORE < gslot < P.GCS_SLOTS and gslot != slot)
            if not plausible:
                continue
            # every grant counts for collision settlement, not just ours;
            # only a grant for our own tile proves this slot is a builder's
            if (x, y) == self.grant_probe_pos:
                self.owners.setdefault(slot, Owner("builder_bot", spawn_round=0))
                detail["format"] = "grant (probed)"
            self._grants.append((slot, ev.args))
            result.events.append((slot, ev))

    def _on_assign(self, ev: ControlEvent, wrote_round: int):
        slot, period, phase = ev.args
        self.owners[slot] = Owner("builder_bot", spawn_round=wrote_round,
                                  period=period, phase=phase)
        self.known.setdefault(slot, set())
        # the round we are IN right now (wrote_round + 1) is the resync round
        self.resync_write_round = wrote_round + 1
        self.onboard_until = wrote_round + 1 + P.ONBOARD_ROUNDS

    def _liveness(self, snapshot, wrote_round, resync, onboard, result):
        if self.prev_snapshot is None:
            return
        for slot, owner in list(self.owners.items()):
            if slot == SLOT_CORE:
                continue                     # the Core is never reclaimed
            if not owner.has_written:
                if wrote_round - owner.spawn_round > TAKEOVER_GRACE and not onboard:
                    result.deaths.append(slot)       # never took the slot
                    del self.owners[slot]
                    self.known.pop(slot, None)
                continue
            if snapshot[slot] != self.prev_snapshot[slot]:
                continue
            if onboard and owner.kind != "builder_bot" and slot != SLOT_CORE:
                continue                     # turret silent while the Core borrows
            if resync:
                continue
            if wrote_round % owner.period != owner.phase:
                continue                     # off-phase round-robin turn
            result.deaths.append(slot)
            del self.owners[slot]
            self.known.pop(slot, None)

    def _apply_windows(self, result, wrote_round):
        if self.onboard_until is not None and wrote_round > self.onboard_until:
            self.resync_write_round = None
            self.onboard_until = None

    # ------------------------------------------------------------------
    # writer side
    # ------------------------------------------------------------------
    def my_slot(self, unit_key) -> int | None:
        """Slot owned by the unit identified by unit_key.

        unit_key: ('spawn_round', R) for builders, ('pos', (x, y)) for
        turrets/launchers, ('core',) for the Core.
        """
        if unit_key == ("core",):
            return SLOT_CORE
        for slot, owner in self.owners.items():
            if unit_key[0] == "spawn_round" and owner.kind == "builder_bot" \
                    and owner.spawn_round == unit_key[1]:
                return slot
            if unit_key[0] == "pos" and owner.kind != "builder_bot" \
                    and owner.pos == unit_key[1]:
                return slot
        return None

    def may_write(self, slot: int, round_no: int) -> bool:
        owner = self.owners.get(slot) if slot != SLOT_CORE else Owner("core", 0)
        if owner is None:
            return False
        if self._in_onboard_window(round_no) and owner.kind not in ("core", "builder_bot"):
            return False                     # turret slots belong to the Core now
        return round_no % owner.period == owner.phase

    def is_resync_round(self, round_no: int) -> bool:
        """Writes in round_no are RESYNC format: the round after an ASSIGN
        became readable."""
        return self.resync_write_round == round_no

    def _in_onboard_window(self, round_no: int) -> bool:
        return (self.onboard_until is not None
                and self.resync_write_round is not None
                and self.resync_write_round < round_no <= self.onboard_until)

    in_onboard_window = _in_onboard_window

    # ------------------------------------------------------------------
    # Core-side helpers
    # ------------------------------------------------------------------
    def pick_builder_slot(self) -> int | None:
        """Lowest free builder slot, evicting turrets down to the reserved pool."""
        turret_floor = P.turret_slots_from() - TURRET_RESERVED_SLOTS + 1
        for slot in range(BUILDER_SLOTS_FROM, P.GCS_SLOTS):
            owner = self.owners.get(slot)
            if owner is None:
                return slot
            if owner.kind != "builder_bot" and slot < turret_floor:
                return slot                  # builders may evict turrets here
        return None                          # store full: round-robin territory

    def pick_turret_slot(self, spread: int = 0, avoid=()) -> int | None:
        """A free turret-pool slot (the pool grows downward from the top).
        `spread` (the granting builder's own slot) staggers which free slot
        different builders pick in the same round, so same-round collisions
        are rare; `avoid` excludes slots just lost to a collision."""
        free = [s for s in range(P.turret_slots_from(), SLOT_CORE, -1)
                if s not in self.owners and s not in avoid]
        if not free:
            return None
        return free[spread % len(free)]

    def core_unknown(self, slot: int, tiles) -> list[tuple[int, int]]:
        """Of `tiles`, those the unit in `slot` does not know yet (the Core
        streams only these, preferring tiles behind the unit's travel — that
        ordering is applied by the caller, which knows the unit's heading)."""
        known = self.known.get(slot, set())
        return [t for t in tiles if t not in known]

    def note_streamed(self, slot: int, tiles):
        self.known.setdefault(slot, set()).update(tiles)
