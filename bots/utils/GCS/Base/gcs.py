"""Per-unit GCS facade.

The common path is two calls per round:

    result = gcs.absorb(ct)     # decode all 16 slots, feed the internal map
    gcs.publish(ct)             # write the most valuable thing we know

plus flexible variants: publish(ct, message=...) sends a caller-built message,
queue() hands in an out-of-band message that competes on priority, and
send_raw() writes a u32 directly.  Everything routes through the ownership and
round-robin gate, and absorb()/publish() never raise into the bot (decision 7):
failures print a diagnostic and degrade.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import interfaces, messages
from .messages import Fact
from .registry import RoundResult, SlotRegistry
from . import protocol as P
from .protocol import (
    CORE_HP_ANNOUNCE_DRIFT,
    CORE_HP_MAX,
    CTRL_ASSIGN,
    CTRL_DIRECTIVE,
    CTRL_GRANT,
    CTRL_STATUS,
    CTRL_SYMMETRY,
    GRANT_KINDS,
    STATUS_FIELDS,
    NEWBORN_FIRST_RUN_DELAY,
    SLOT_CORE,
    STATE_CODE,
    TASK_FIX_CONVEYOR_BASE,
    TASK_FIX_HARVESTER,
)


@dataclass
class OutMessage:
    """A caller-built message for publish()/queue().

    type: 'facts' | 'run' | 'remote' | 'control' | 'raw'
    the payload fields mirror the encoders in messages.py.
    """
    type: str
    facts: list[Fact] | None = None
    aux: int = 0
    run: tuple | None = None          # (start, direction, length, state)
    remote: Fact | None = None
    control: tuple[int, int] | None = None    # (kind, packed args)
    raw: int | None = None
    grant: tuple | None = None                # (x, y, kind, facing, avoid): slot picked at send time


class GCS:
    def __init__(self, kind: str, map_source=None, on_directive=None):
        self.kind = kind
        self.map = map_source if map_source is not None else interfaces.DictMapSource()
        self.on_directive = on_directive or interfaces.on_directive
        self.registry: SlotRegistry | None = None
        self.slot: int | None = None
        self.spawn_round: int | None = None
        self.pos: tuple[int, int] | None = None
        self.last_pub_pos: tuple[int, int] | None = None   # where we last wrote from
        self.last_written: int | None = None
        self.restate_cursor = 0                # cycles through known facts
        self.symmetry_announced = False
        self.status: dict[str, int] = {}       # latched STATUS fields heard
        self.queued: list[tuple[float, OutMessage]] = []
        # Core only: everyone knows HP starts at CORE_HP_MAX, so the first
        # announcement happens only once the Core has drifted from it
        self.last_hp_announced: int = CORE_HP_MAX

    # ------------------------------------------------------------------
    # absorb
    # ------------------------------------------------------------------
    def absorb(self, ct) -> RoundResult:
        try:
            return self._absorb(ct)
        except Exception as exc:                          # decision 7
            import traceback
            print(f"[GCS] absorb failed: {exc!r} | " + traceback.format_exc().replace("\n", " | ")[-600:])
            return RoundResult()

    def _absorb(self, ct) -> RoundResult:
        round_no = ct.get_current_round()
        if self.registry is None:
            self.registry = SlotRegistry(ct.get_map_width(), ct.get_map_height())
            # the engine first runs a unit the round after it was spawned
            self.spawn_round = round_no - NEWBORN_FIRST_RUN_DELAY
            if self.kind == "core":
                self.slot = SLOT_CORE
        if self.kind == "core":
            self.registry.owners[SLOT_CORE].pos = tuple(_pos_of(ct))
        self.pos = tuple(_pos_of(ct))

        if self.slot is None and self.kind not in ("core", "builder_bot"):
            self.registry.grant_probe_pos = self.pos       # listen for our GRANT
        else:
            self.registry.grant_probe_pos = None
        snapshot = [ct.read_store(i) for i in range(P.GCS_SLOTS)]
        result = self.registry.absorb_snapshot(snapshot, round_no)

        if self.slot is None:
            self.slot = self.registry.my_slot(self._unit_key())
            if self.slot is not None:
                result.assigned_slot = self.slot

        for f in result.facts:
            self.map.apply_fact(f, from_gcs=True)
        for _slot, ev in result.events:
            if ev.kind == CTRL_SYMMETRY and hasattr(self.map, "set_symmetry"):
                self.map.set_symmetry(ev.args[0])
            elif ev.kind == CTRL_STATUS:
                field, val = ev.args
                if field < len(STATUS_FIELDS):
                    self.status[STATUS_FIELDS[field]] = val
            elif ev.kind == CTRL_GRANT:
                x, y, _s, gkind, facing = ev.args
                name = "OUR_" + GRANT_KINDS[gkind].upper()
                if facing:
                    name += "_" + ("N", "NE", "E", "SE", "S", "SW", "W", "NW")[facing - 1]
                self.map.apply_fact(Fact(x, y, STATE_CODE[name]), from_gcs=True)
        # a grant of ours lost a same-round collision: grant again, elsewhere
        for sender, args in result.lost_grants:
            if sender == self.slot:
                x, y, lost_slot, gkind, facing = args
                self.grant_turret(x, y, GRANT_KINDS[gkind], (facing - 1) if facing else None,
                                  avoid=(lost_slot,))
        core_pos = self.registry.owners[SLOT_CORE].pos
        if core_pos is not None and hasattr(self.map, "note_core_block"):
            self.map.note_core_block(core_pos)        # the whole 2x2, exactly
        self._dispatch_directives(result)
        return result

    def _unit_key(self):
        if self.kind == "core":
            return ("core",)
        if self.kind == "builder_bot":
            # the ASSIGN for the bot spawned in round R is written in round R
            return ("spawn_round", self.spawn_round)
        return ("pos", self.pos)

    def _dispatch_directives(self, result: RoundResult):
        for _slot, ev in result.events:
            if ev.kind != CTRL_DIRECTIVE:
                continue
            x, y, task = ev.args
            if TASK_FIX_CONVEYOR_BASE <= task < TASK_FIX_CONVEYOR_BASE + 15:
                # addressed: only the builder holding that slot acts
                if self.kind == "builder_bot" and self.slot == task:
                    self.on_directive(x, y, task)
            elif self.kind == "builder_bot":
                self.on_directive(x, y, task)     # unaddressed: everyone hears

    # ------------------------------------------------------------------
    # publish
    # ------------------------------------------------------------------
    def publish(self, ct, message: OutMessage | None = None) -> list[Fact]:
        try:
            return self._publish(ct, message)
        except Exception as exc:                          # decision 7
            print(f"[GCS] publish failed: {exc!r}")
            try:
                self._publish_restate(ct, self._move_digit())
            except Exception as exc2:
                print(f"[GCS] fallback failed too: {exc2!r}")
            return []

    def _publish(self, ct, message) -> list[Fact]:
        round_no = ct.get_current_round()
        reg = self.registry
        if reg is None or self.slot is None:
            return []                       # no slot yet (newborn round): silent
        # Re-read our position: call publish() AFTER moving and the message
        # describes where we are now, so readers' dead reckoning is exact.
        self.pos = tuple(_pos_of(ct))
        if not reg.may_write(self.slot, round_no):
            return []                       # off-phase, or the Core borrowed us

        # whoever works out the map's symmetry first announces it, once;
        # nobody repeats it after it has been on the store
        if (not self.symmetry_announced and not reg.symmetry_heard
                and self.map.symmetry() is not None):
            self.symmetry_announced = True
            self.core_announce_symmetry(self.map.symmetry())

        priority = 0.0
        if message is None and self.queued:
            self.queued.sort(key=lambda pair: -pair[0])
            priority, message = self.queued.pop(0)

        # An ASSIGN must go out in the spawn round itself, so queued control
        # messages outrank the HP announcement; the HP waits a round.
        if self.kind == "core" and message is None and self._core_hp_due(ct):
            self._write(ct, self.slot, messages.core_hp_value(ct.get_hp()))
            self.last_hp_announced = ct.get_hp()
            if reg.in_onboard_window(round_no):
                self._core_stream(ct, round_no, skip_own=True)
            return []

        if reg.is_resync_round(round_no):
            if message is not None:
                self.queued.append((priority, message))   # deferred, same rank
            return self._publish_resync(ct)

        if self.kind == "core" and reg.in_onboard_window(round_no):
            if message is not None:
                self.queued.append((priority, message))   # deferred, same rank
            self._core_stream(ct, round_no, skip_own=False)
            return []

        # a GRANT mid-onboarding would make the new turret write into a slot
        # the Core may be streaming through: hold it until the window closes
        if message is not None and message.type == "grant" and reg.in_onboard_window(round_no):
            self.queued.append((priority, message))
            message = None

        if message is not None:
            return self._publish_message(ct, message)
        return self._publish_facts(ct)

    def _publish_facts(self, ct) -> list[Fact]:
        candidates = self.map.pending_facts(8)
        move = self._move_digit()
        value, used = messages.encode_standard(
            self.kind, self.pos, candidates, move=move, aux=0)
        if value is None or not used:
            # nothing new fits the FOV-relative format: one new fact via the
            # REMOTE escape (escapes keep the move/turn prefix, so nothing
            # is lost), else restate old knowledge
            for f in candidates:
                value = messages.encode_remote(self.kind, f, self.registry.map_w,
                                               self.registry.map_h, move=move)
                if value is not None and value != self.last_written:
                    self._write(ct, self.slot, value)
                    self.map.note_shared([f])
                    return [f]
            return self._publish_restate(ct, move)
        if value == self.last_written:      # liveness: never repeat a value
            value, used = messages.encode_standard(
                self.kind, self.pos, candidates, move=move, parity=1)
            if value is None or value == self.last_written:
                return self._publish_restate(ct, move)
        self._write(ct, self.slot, value)
        self.map.note_shared(used)
        return used

    def _publish_restate(self, ct, move: int) -> list[Fact]:
        """Nothing new to say: the store never idles, so restate something
        already known — cycling through known facts so teammates that
        missed them (newborns, latecomers) pick them up and the value never
        repeats.  In-FOV facts go out two at a time in standard format; a
        fact outside the FOV goes via REMOTE.  Only a completely empty map
        falls back to an empty standard message (move/turn still carried)."""
        known = self.map.known_facts()
        w, h = self.registry.map_w, self.registry.map_h
        for _ in range(max(1, len(known))):
            if known:
                i = self.restate_cursor % len(known)
                self.restate_cursor += 1
                pair = known[i:i + 2] if i + 1 < len(known) else known[i:i + 1] + known[:1]
                value, used = messages.encode_standard(self.kind, self.pos, pair, move=move)
                if (value is None or not used):
                    value = messages.encode_remote(self.kind, known[i], w, h, move=move)
                if value is not None and value != self.last_written:
                    self._write(ct, self.slot, value)
                    return []
            else:
                break
        for parity in (0, 1):
            value, _ = messages.encode_standard(self.kind, self.pos, [],
                                                move=move, parity=parity)
            if value is not None and value != self.last_written:
                self._write(ct, self.slot, value)
                return []
        print("[GCS] could not produce a distinct value this round")
        return []

    def _publish_message(self, ct, m: OutMessage) -> list[Fact]:
        move = self._move_digit()
        w, h = self.registry.map_w, self.registry.map_h
        value, used = None, []
        if m.type == "facts":
            value, used = messages.encode_standard(
                self.kind, self.pos, m.facts or [], move=move, aux=m.aux)
        elif m.type == "run" and m.run:
            start, direction, length, state = m.run
            value = messages.encode_run(self.kind, self.pos, start, direction,
                                        length, state, w, h, move=move)
        elif m.type == "remote" and m.remote:
            value = messages.encode_remote(self.kind, m.remote, w, h, move=move)
        elif m.type == "control" and m.control:
            value = messages.encode_control(self.kind, *m.control, move=move)
        elif m.type == "grant" and m.grant:
            x, y, gkind, facing, avoid, fixed = m.grant
            slot = fixed if fixed is not None else \
                self.registry.pick_turret_slot(spread=self.slot or 0, avoid=avoid)
            if slot is None:
                print("[GCS] no free slot for a grant; dropped")
                return self._publish_restate(ct, move)
            args = messages.grant_args(x, y, slot, GRANT_KINDS.index(gkind),
                                       0 if facing is None else facing + 1, self.registry.map_h)
            value = messages.encode_control(self.kind, CTRL_GRANT, args, move=move)
        elif m.type == "raw" and m.raw is not None:
            value = m.raw
        if value is None or value == self.last_written:
            print(f"[GCS] message {m.type} unencodable or repeated; restating instead")
            return self._publish_restate(ct, move)
        self._write(ct, self.slot, value)
        if used:
            self.map.note_shared(used)
        return used

    def _publish_resync(self, ct) -> list[Fact]:
        candidates = self.map.pending_facts(4)
        best = candidates[0] if candidates else None
        value = messages.encode_resync(self.kind, self.pos, best,
                                       self.registry.map_w, self.registry.map_h)
        if value is None:
            return self._publish_restate(ct, 0)
        self._write(ct, self.slot, value)
        if best is not None:
            self.map.note_shared([best])
            return [best]
        return []

    # ------------------------------------------------------------------
    # flexible senders
    # ------------------------------------------------------------------
    def queue(self, message: OutMessage, priority: float = 5.0) -> None:
        self.queued.append((priority, message))

    def send_raw(self, ct, value: int) -> bool:
        """Escape hatch: write a u32 directly, still gated by ownership and
        the never-repeat liveness rule."""
        round_no = ct.get_current_round()
        if (self.registry is None or self.slot is None
                or not self.registry.may_write(self.slot, round_no)
                or value == self.last_written):
            return False
        self._write(ct, self.slot, value)
        return True

    # ------------------------------------------------------------------
    # Core helpers
    # ------------------------------------------------------------------
    def core_announce_assign(self, slot: int, period: int = 1, phase: int = 0):
        """Queue the ASSIGN for a builder spawned THIS round (Core only).
        Must be the only control the Core sends this round, and must not be
        sent while a resync/onboarding window is active."""
        args = messages.assign_args(slot, period, phase)
        # strictly above every other message: it must go out THIS round
        self.queue(OutMessage("control", control=(CTRL_ASSIGN, args)), priority=1000.0)

    def core_announce_symmetry(self, kind: int):
        """Queue a SYMMETRY announcement (any unit may send one)."""
        self.queue(OutMessage("control", control=(CTRL_SYMMETRY, kind)), priority=90.0)

    def grant_turret(self, x: int, y: int, kind: str, facing: int | None, slot: int | None = None,
                     avoid=()):
        """Builder: announce the friendly turret/launcher we just built at
        (x, y) and grant it a slot, in absolute coordinates (CONTROL/GRANT) —
        the turret's own registry is empty when it reads this, so a
        FOV-relative fact would mean nothing to it.  The slot is picked when
        the message actually goes out (grants can be held back by a window,
        and a slot picked earlier may be taken by then).
        kind: 'gunner' / 'sentinel' / 'launcher'; facing: 0..7 (N,NE,..) or None."""
        self.queue(OutMessage("grant", grant=(x, y, kind, facing, tuple(avoid), slot)), priority=500.0)

    def send_status(self, field: str, value: int, priority: float = 300.0):
        """Queue a team-state scalar (CONTROL/STATUS): field is one of
        protocol.STATUS_FIELDS, value 0..511.  Readers latch it."""
        self.queue(OutMessage("control", control=(CTRL_STATUS,
                              messages.status_args(STATUS_FIELDS.index(field), value))),
                   priority=priority)

    def send_directive(self, x: int, y: int, task: int):
        """Core: any task.  Builders: FIX_HARVESTER only (protocol rule)."""
        if self.kind != "core" and task != TASK_FIX_HARVESTER:
            print(f"[GCS] builders may only send FIX_HARVESTER, not task {task}")
            return
        args = messages.directive_args(x, y, task, self.registry.map_h)
        self.queue(OutMessage("control", control=(CTRL_DIRECTIVE, args)), priority=80.0)

    def _core_hp_due(self, ct) -> bool:
        if self.kind != "core":
            return False
        return abs(ct.get_hp() - self.last_hp_announced) > CORE_HP_ANNOUNCE_DRIFT

    def _core_stream(self, ct, round_no: int, skip_own: bool):
        """Onboarding: stream archive facts through our own slot and every
        turret/launcher slot (speaker=1), skipping what each unit knows."""
        reg = self.registry
        wrote_own = False
        targets = [] if skip_own else [(SLOT_CORE, False)]
        targets += [(s, True) for s, o in reg.owners.items()
                    if o.kind not in ("builder_bot", "core")]
        # PLACEHOLDER ordering: the internal-map module should rank by value
        # and prefer tiles behind each receiver's direction of travel.
        archive = self.map.pending_facts(64)
        all_known = self.map.known_facts()
        for slot, borrowed in targets:
            known = reg.known.get(slot, set())
            fresh = [f for f in archive if (f.x, f.y) not in known]
            if not fresh and slot == SLOT_CORE and all_known:
                # own slot must change every round and stays in chain
                # format for the whole window: restate, cycling
                i = self.restate_cursor % len(all_known)
                self.restate_cursor += 1
                fresh = all_known[i:i + 2] or all_known[:2]
            if not fresh:
                if slot == SLOT_CORE:
                    self._publish_restate(ct, 0)   # empty map: parity message
                continue
            abs_fact = fresh[0]
            rel_fact = fresh[1] if len(fresh) > 1 else None
            value = messages.encode_onboard(abs_fact, rel_fact,
                                            reg.map_w, reg.map_h, borrowed)
            if value is None or value == self.last_written:
                continue
            self._write(ct, slot, value)
            if slot == SLOT_CORE:
                wrote_own = True
            reg.note_streamed(slot, [(abs_fact.x, abs_fact.y)]
                              + ([(rel_fact.x, rel_fact.y)] if rel_fact else []))
        return wrote_own

    # ------------------------------------------------------------------
    # plumbing
    # ------------------------------------------------------------------
    def _move_digit(self) -> int:
        """Our displacement since our previous write, as a cardinal step.

        A builder sharing a slot (period > 1) that moves more than once
        between its writes cannot express that; readers' reckoning of it
        then drifts until the next resync round.  Known limitation.
        """
        if self.kind != "builder_bot" or self.last_pub_pos is None or self.pos is None:
            return 0
        dx = self.pos[0] - self.last_pub_pos[0]
        dy = self.pos[1] - self.last_pub_pos[1]
        return {(0, -1): 1, (1, 0): 2, (0, 1): 3, (-1, 0): 4}.get((dx, dy), 0)

    def _write(self, ct, slot: int, value: int) -> None:
        ct.write_store(slot, value)
        if slot == self.slot:
            self.last_written = value
            self.last_pub_pos = self.pos



def _pos_of(ct):
    p = ct.get_position()
    return (p.x, p.y) if hasattr(p, "x") else tuple(p)
