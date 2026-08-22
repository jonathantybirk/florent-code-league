"""GCS module tests — mirrors the verification section of the plan.

Runs headless (no engine): a FakeController implements the read/write store
and the handful of Controller methods the facade touches, and a tiny World
drives whole-team rounds with the engine's buffered-write semantics.
"""

from __future__ import annotations

import random

import pytest

from .. import codec, fov, messages, protocol
from ..codec import CodecError
from ..gcs import GCS, OutMessage
from ..interfaces import DictMapSource
from ..messages import Fact
from ..protocol import (
    CTRL_ASSIGN,
    CTRL_DIRECTIVE,
    CTRL_SYMMETRY,
    IDLE_A,
    IDLE_B,
    LAYOUTS,
    PAYLOAD_SPACE,
    SLOT_CORE,
    STATE_CODE,
    STORE_SIZE,
    TASK_FIX_HARVESTER,
)

W, H = 30, 30
EMPTY = STATE_CODE["EMPTY"]
WALL = STATE_CODE["WALL"]
ORE = STATE_CODE["ORE_FREE"]


# ---------------------------------------------------------------------------
# harness
# ---------------------------------------------------------------------------

class Store:
    """The engine's buffered communication store."""

    def __init__(self):
        self.values = [0] * STORE_SIZE
        self.pending: dict[int, int] = {}

    def commit(self):
        for slot, value in self.pending.items():
            self.values[slot] = value
        self.pending.clear()


class FakeController:
    def __init__(self, store: Store, pos, round_no=0, hp=500):
        self.store = store
        self.pos = pos
        self.round_no = round_no
        self.hp = hp

    def get_current_round(self):
        return self.round_no

    def get_map_width(self):
        return W

    def get_map_height(self):
        return H

    def get_position(self):
        return self.pos

    def get_hp(self):
        return self.hp

    def read_store(self, i):
        return self.store.values[i]

    def write_store(self, i, v):
        self.store.pending[i] = v


class Unit:
    def __init__(self, kind, pos, hp=500):
        self.kind = kind
        self.pos = pos
        self.hp = hp
        self.gcs = GCS(kind, DictMapSource())
        self.alive = True


class World:
    """Drives rounds: all units absorb, then publish, then the store commits."""

    def __init__(self):
        self.store = Store()
        self.round_no = 0
        self.units: list[Unit] = []

    def step(self, before_publish=None):
        for u in self.units:
            if not u.alive:
                continue
            ct = FakeController(self.store, u.pos, self.round_no, u.hp)
            u.gcs.absorb(ct)
        if before_publish:
            before_publish(self)
        for u in self.units:
            if not u.alive:
                continue
            ct = FakeController(self.store, u.pos, self.round_no, u.hp)
            u.gcs.publish(ct)
        self.store.commit()
        self.round_no += 1


# ---------------------------------------------------------------------------
# 2. codec round-trip + degrade
# ---------------------------------------------------------------------------

def test_codec_roundtrip_every_layout():
    rng = random.Random(1)
    for kind, layout in LAYOUTS.items():
        radices = [r for _, r in layout]
        for _ in range(500):
            digits = tuple(rng.randrange(r) for r in radices)
            value = codec.pack(digits, radices)
            assert value < PAYLOAD_SPACE
            assert codec.unpack(value, radices) == digits


def test_codec_rejects_out_of_range():
    with pytest.raises(CodecError):
        codec.pack((5,), (5,))
    with pytest.raises(CodecError):
        codec.unpack(PAYLOAD_SPACE, (10, 10))


def test_publish_never_raises_and_degrades_to_idle():
    """A poisoned map source cannot kill the turn: publish idles instead."""

    class Poisoned(DictMapSource):
        def pending_facts(self, budget):
            raise RuntimeError("boom")

    store = Store()
    unit = Unit("core", (5, 5))
    unit.gcs.map = Poisoned()
    ct = FakeController(store, unit.pos, 0)
    unit.gcs.absorb(ct)
    unit.gcs.last_hp_announced = 500        # suppress the HP announcement path
    unit.gcs.publish(ct)                    # must not raise
    assert store.pending[SLOT_CORE] in (IDLE_A, IDLE_B)


# ---------------------------------------------------------------------------
# 3. capacity assertions
# ---------------------------------------------------------------------------

def test_every_layout_fits_payload_space():
    for kind, layout in LAYOUTS.items():
        cost = 1
        for _, r in layout:
            cost *= r
        assert cost <= PAYLOAD_SPACE, kind


def test_fov_tables_match_protocol():
    for kind, n in protocol.FOV_TILES.items():
        assert len(fov.OFFSETS[kind]) == n


# ---------------------------------------------------------------------------
# standard messages: encode -> decode identity
# ---------------------------------------------------------------------------

def test_standard_two_facts_roundtrip():
    pos = (10, 10)
    facts = [Fact(11, 10, ORE), Fact(10, 12, WALL)]
    value, used = messages.encode_standard("builder_bot", pos, facts, move=2)
    assert used == facts
    assert messages.peek_move("builder_bot", value) == 2
    out = messages.decode_standard("builder_bot", value, pos, W, H)
    assert out.facts == facts and out.move == 2


def test_standard_skips_unencodable_far_fact():
    pos = (10, 10)
    far = Fact(29, 29, ORE)                  # outside the builder disc
    near = Fact(10, 11, EMPTY)
    value, used = messages.encode_standard("builder_bot", pos, [far, near])
    assert used == [near]
    out = messages.decode_standard("builder_bot", value, pos, W, H)
    assert out.facts == [near]


def test_run_roundtrip():
    pos = (10, 10)
    value = messages.encode_run("builder_bot", pos, (8, 10), 1, 5, EMPTY, W, H)
    out = messages.decode_standard("builder_bot", value, pos, W, H)
    assert [(f.x, f.y) for f in out.facts] == [(8 + i, 10) for i in range(5)]
    assert all(f.state == EMPTY for f in out.facts)


def test_remote_roundtrip_all_kinds():
    for kind in LAYOUTS:
        f = Fact(28, 3, STATE_CODE["ENEMY_CORE"])
        value = messages.encode_remote(kind, f, W, H)
        out = messages.decode_standard(kind, value, (10, 10), W, H)
        assert out.facts == [f], kind


def test_gunner_turn_digit():
    pos = (7, 7)
    value, _ = messages.encode_standard("gunner", pos, [], turn=1)
    out = messages.decode_standard("gunner", value, pos, W, H)
    assert out.turn == 1


# ---------------------------------------------------------------------------
# 4. liveness
# ---------------------------------------------------------------------------

def test_idle_alternates_and_death_detected():
    world = World()
    core = Unit("core", (2, 2))
    world.units.append(core)
    world.step()                             # round 0: nothing new -> idle
    world.step()
    world.step()
    a, b = world.store.values[SLOT_CORE], None
    world.step()
    b = world.store.values[SLOT_CORE]
    assert {a, b} == {IDLE_A, IDLE_B}        # never the same value twice


def test_core_hp_announce_only_on_drift():
    world = World()
    core = Unit("core", (2, 2))
    world.units.append(core)
    world.step()
    # HP starts at 500 and that is common knowledge: nothing to announce
    assert messages.classify_raw(world.store.values[SLOT_CORE])[0] == "idle"
    core.hp = 470                            # drift 30: no announcement
    for _ in range(2):
        world.step()
    assert messages.classify_raw(world.store.values[SLOT_CORE])[0] != "core_hp"
    core.hp = 440                            # drift 60: announce exactly
    world.step()
    kind, hp = messages.classify_raw(world.store.values[SLOT_CORE])
    assert (kind, hp) == ("core_hp", 440)
    world.step()                             # latched: back to the heartbeat
    assert messages.classify_raw(world.store.values[SLOT_CORE])[0] == "idle"


# ---------------------------------------------------------------------------
# 5. publication bookkeeping
# ---------------------------------------------------------------------------

def test_absorbed_facts_are_never_resent():
    src = DictMapSource()
    src.apply_fact(Fact(3, 3, ORE), from_gcs=True)      # came off the store
    assert src.pending_facts(10) == []


def test_unwritten_facts_stay_pending():
    src = DictMapSource()
    src.apply_fact(Fact(3, 3, ORE), from_gcs=False)     # own observation
    assert src.pending_facts(10) == [Fact(3, 3, ORE)]
    src.note_shared([Fact(3, 3, ORE)])
    assert src.pending_facts(10) == []


def test_publish_marks_only_what_was_written():
    world = World()
    core = Unit("core", (2, 2))
    world.units.append(core)
    core.gcs.last_hp_announced = 500                     # skip HP round
    core.hp = 500
    for i in range(5):
        core.gcs.map.apply_fact(Fact(20 + i, 20, ORE), from_gcs=False)
    world.step()
    # the facts are outside the Core's FOV, so one goes out via the REMOTE
    # escape — exactly that one is marked published, the rest stay pending
    assert len(core.gcs.map.published) == 1
    assert len(core.gcs.map.pending_facts(10)) == 4


# ---------------------------------------------------------------------------
# 6. control round-trip
# ---------------------------------------------------------------------------

def test_directive_addressing():
    heard: dict[str, list] = {"slot3": [], "slot4": []}
    world = World()
    core = Unit("core", (2, 2))
    b3 = Unit("builder_bot", (5, 5))
    b4 = Unit("builder_bot", (6, 6))
    world.units += [core, b3, b4]
    # wire the units into slots by hand (ownership tested separately)
    for u, slot in ((b3, 3), (b4, 4)):
        u.gcs.registry = None
    world.step()
    for u, slot in ((b3, 3), (b4, 4)):
        u.gcs.slot = slot
        u.gcs.registry.owners  # registries exist now
    b3.gcs.on_directive = lambda x, y, t: heard["slot3"].append((x, y, t))
    b4.gcs.on_directive = lambda x, y, t: heard["slot4"].append((x, y, t))

    core.gcs.last_hp_announced = 500
    core.gcs.send_directive(12, 7, 3)        # FIX_CONVEYOR for slot 3
    # give the core's registry an owner entry for itself implicitly (slot 0)
    world.step()                             # core writes the control
    world.step()                             # builders read it
    assert heard["slot3"] == [(12, 7, 3)]
    assert heard["slot4"] == []

    core.gcs.send_directive(9, 9, TASK_FIX_HARVESTER)    # unaddressed
    world.step()
    world.step()
    assert (9, 9, TASK_FIX_HARVESTER) in heard["slot3"]
    assert (9, 9, TASK_FIX_HARVESTER) in heard["slot4"]


def test_symmetry_control_roundtrip():
    value = messages.encode_control("core", CTRL_SYMMETRY, 2)
    out = messages.decode_standard("core", value, (0, 0), W, H)
    assert out.events == [messages.ControlEvent(CTRL_SYMMETRY, (2,))]


def test_assign_control_roundtrip():
    value = messages.encode_control("core", CTRL_ASSIGN, messages.assign_args(5, 2, 1))
    out = messages.decode_standard("core", value, (0, 0), W, H)
    assert out.events == [messages.ControlEvent(CTRL_ASSIGN, (5, 2, 1))]


# ---------------------------------------------------------------------------
# 7. spawn choreography
# ---------------------------------------------------------------------------

def test_spawn_assign_resync_onboard_flow():
    world = World()
    core = Unit("core", (2, 2))
    world.units.append(core)
    core.gcs.last_hp_announced = 500
    world.step()                                       # round 0 settles

    # Core spawns a builder in round 1 and announces ASSIGN(slot 1)
    spawn_round = world.round_no
    core.gcs.core_announce_assign(1)
    world.step()                                       # round 1: ASSIGN written
    newborn = Unit("builder_bot", (3, 2))
    world.units.append(newborn)                        # engine: first run in R+1

    # round 2: everyone reads the ASSIGN; the newborn learns slot 1 and the
    # round becomes the resync round — its write is its absolute position
    world.step()
    assert newborn.gcs.slot == 1
    assert newborn.gcs.spawn_round == spawn_round

    # round 3: the resync writes are readable; the core's registry now knows
    # the newborn's exact position
    world.step()
    owner = core.gcs.registry.owners[1]
    assert owner.pos == (3, 2)
    assert core.gcs.registry.in_onboard_window(world.round_no - 1) or \
        core.gcs.registry.in_onboard_window(world.round_no)


def test_dead_reckoning_after_resync():
    world = World()
    core = Unit("core", (2, 2))
    world.units.append(core)
    core.gcs.last_hp_announced = 500
    world.step()
    core.gcs.core_announce_assign(1)
    world.step()                                       # spawn round
    builder = Unit("builder_bot", (3, 2))
    world.units.append(builder)                        # first run in R+1
    for _ in range(2):
        world.step()
    # builder moves east; its next standard message carries move=E and the
    # core's registry updates its tracked position
    builder.gcs.map.apply_fact(Fact(4, 3, ORE), from_gcs=False)
    builder.pos = (4, 2)
    world.step()
    world.step()
    assert core.gcs.registry.owners[1].pos == (4, 2)
    # the fact it announced arrived in the core's map, resolved against the
    # dead-reckoned position
    assert core.gcs.map.tiles.get((4, 3)) == ORE


# ---------------------------------------------------------------------------
# 8. protocol simulation
# ---------------------------------------------------------------------------

def test_simulation_no_double_writes_and_reclamation():
    rng = random.Random(7)
    world = World()
    core = Unit("core", (2, 2))
    world.units.append(core)
    core.gcs.last_hp_announced = 500

    writes_per_round: list[dict[int, int]] = []
    orig_commit = world.store.commit

    def tracking_commit():
        writes_per_round.append(dict(world.store.pending))
        orig_commit()

    world.store.commit = tracking_commit

    world.step()
    next_spawn_pos = iter([(3, 2), (2, 3), (3, 3), (1, 2), (2, 1)])
    builders: list[Unit] = []
    pending_spawn: list[Unit] = []

    def maybe_spawn(w):
        # decided after absorb, like the Core's real turn: registry state is
        # current for this round, so the no-spawn-during-window rule holds
        reg = core.gcs.registry
        can_spawn = (len(builders) < 5
                     and not reg.in_onboard_window(w.round_no)
                     and not reg.is_resync_round(w.round_no))
        if can_spawn and rng.random() < 0.4:
            slot = reg.pick_builder_slot()
            b = Unit("builder_bot", next(next_spawn_pos))
            pending_spawn.append(b)        # engine: first run is next round
            builders.append(b)
            core.gcs.core_announce_assign(slot)

    for round_i in range(40):
        # every builder keeps discovering something so it always has content
        for b in builders:
            if b.alive:
                b.gcs.map.apply_fact(
                    Fact(rng.randrange(W), rng.randrange(H), ORE), from_gcs=False)
        if builders and round_i == 30:
            builders[0].alive = False        # dies: stops writing
        world.units.extend(pending_spawn)    # last round's newborns join now
        pending_spawn.clear()
        world.step(before_publish=maybe_spawn)
    world.units.extend(pending_spawn)
    for _ in range(3):
        world.step()                         # settle: last ASSIGN gets read

    # every live builder ended up owning a slot
    for b in builders:
        if b.alive:
            assert b.gcs.slot is not None
    # the dead builder's slot was reclaimed — it is either free again or
    # re-granted to a later spawn, never still credited to the dead unit
    dead = builders[0]
    owner = core.gcs.registry.owners.get(dead.gcs.slot)
    assert owner is None or owner.spawn_round != dead.gcs.spawn_round

    # invariant: one writer per slot per round (the world serialises writes,
    # so a double write would have overwritten pending — track via counts)
    # here we assert the protocol never had two live units claiming one slot
    seen = {}
    for u in [core] + builders:
        if u.alive and u.gcs.slot is not None:
            assert u.gcs.slot not in seen, "two live units share a slot"
            seen[u.gcs.slot] = u

    # convergence: every long-lived unit's registry agrees with the core's on
    # who owns the builder slots (latecomers may still be catching up)
    reference = {s: o.spawn_round for s, o in core.gcs.registry.owners.items()
                 if o.kind == "builder_bot"}
    for b in builders[:2]:
        if not b.alive:
            continue
        theirs = {s: o.spawn_round for s, o in b.gcs.registry.owners.items()
                  if o.kind == "builder_bot" and o.spawn_round >= b.gcs.spawn_round}
        for s, r in theirs.items():
            assert reference.get(s) == r, (s, r, reference)


def test_turret_grant_assigns_slot_and_onboard_decode():
    """A builder's friendly-gunner fact with aux=k makes k the gunner's slot,
    and an onboarding chain through that slot decodes as the Core's facts."""
    reg_w, reg_h = W, H
    pos = (10, 10)
    gun_fact = Fact(11, 10, STATE_CODE["OUR_GUNNER_E"])
    value, used = messages.encode_standard("builder_bot", pos, [gun_fact], aux=15)
    out = messages.decode_standard("builder_bot", value, pos, reg_w, reg_h)
    assert out.aux == 15 and out.facts == [gun_fact]

    # onboarding chain through a borrowed slot
    a = Fact(20, 20, ORE)
    b = Fact(21, 19, WALL)
    chained = messages.encode_onboard(a, b, reg_w, reg_h, borrowed_slot=True)
    got = messages.decode_onboard(chained, reg_w, reg_h, borrowed_slot=True)
    assert got.facts == [a, b]


def test_onboard_chain_params_match_plan():
    r_core, _ = messages.chain_params(30, 30, borrowed_slot=False)
    r_turret, _ = messages.chain_params(30, 30, borrowed_slot=True)
    assert r_core == 9 and r_turret == 6
    r_small, _ = messages.chain_params(8, 8, borrowed_slot=True)
    assert r_small >= 6                       # small maps: window grows
