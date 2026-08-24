"""Decode .replay26 event logs into per-round, per-team mechanic time series.

The wire format is undocumented protobuf, reverse-engineered in
llm-slop-analysis/jon/legacy/replay26-file-format.md (x/jon). This module
decodes the subset needed for benchmarking: the initial snapshot (terrain +
cores), spawn/build events, position changes, and HP deltas.

Stdlib only: the engine runs bots in sub-interpreters inside the calling
process, so anything importable from a match runner must stay clean.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

# Spawn-event type-marker field numbers (empirical; see replay26-file-format.md).
MARKERS = {
    10: "builder",
    11: "conveyor",
    12: "splitter",
    15: "harvester",
    17: "barrier",
    21: "gunner",
    22: "sentinel",
    24: "launcher",
}
KNOWN_FIELDS = {1, 2, 3, 4, 5}


def read_varint(data: bytes, offset: int = 0) -> tuple[int, int]:
    value = shift = 0
    while True:
        byte = data[offset]
        offset += 1
        value |= (byte & 0x7F) << shift
        if byte < 0x80:
            return value, offset
        shift += 7


def signed(value: int) -> int:
    """Interpret a varint as a two's-complement 64-bit integer."""
    return value - (1 << 64) if value >= (1 << 63) else value


def fields(data: bytes) -> list[tuple[int, int, object]]:
    offset, result = 0, []
    while offset < len(data):
        key, offset = read_varint(data, offset)
        number, wire = key >> 3, key & 7
        if wire == 0:
            value, offset = read_varint(data, offset)
        elif wire == 1:
            value, offset = data[offset:offset + 8], offset + 8
        elif wire == 2:
            length, offset = read_varint(data, offset)
            value, offset = data[offset:offset + length], offset + length
        elif wire == 5:
            value, offset = data[offset:offset + 4], offset + 4
        else:
            raise ValueError(f"unsupported protobuf wire type {wire}")
        result.append((number, wire, value))
    return result


def message_dict(data: bytes) -> dict[int, list]:
    result: dict[int, list] = {}
    for number, _, value in fields(data):
        result.setdefault(number, []).append(value)
    return result


def position(data: bytes) -> tuple[int, int]:
    msg = message_dict(data)
    return msg.get(1, [0])[0], msg.get(2, [0])[0]


def unwrap(data: bytes) -> list[tuple[int, int, object]]:
    """Strip the 1-2 layers of trivial single-field wrapping around events."""
    while True:
        decoded = fields(data)
        if len(decoded) == 1 and decoded[0][:2] == (1, 2):
            data = decoded[0][2]
        else:
            return decoded


@dataclass
class Entity:
    entity_id: int
    team: str          # "a" or "b"
    kind: str          # builder/conveyor/harvester/gunner/sentinel/launcher/core/...
    spawn_round: int   # -1 for initial cores
    pos: tuple[int, int]
    hp: int
    max_hp: int
    death_round: int | None = None
    move_rounds: list[int] = field(default_factory=list)
    # (round, pos) after each move; spawn position is the implicit start.
    pos_history: list[tuple[int, tuple[int, int]]] = field(default_factory=list)

    def pos_at(self, round_number: int) -> tuple[int, int]:
        pos = self.pos
        for r, p in self.pos_history:
            if r > round_number:
                break
            pos = p
        return pos


@dataclass
class Replay:
    width: int
    height: int
    rounds: int
    winner: int | None          # raw engine field 4 (0 observed for team A)
    win_condition: str
    core_id: dict[str, int]     # team -> entity id of its Core
    entities: dict[int, Entity]
    # (round, entity_id, delta) in event order; negative = damage.
    hp_events: list[tuple[int, int, int]]

    def team_entities(self, team: str, kind: str) -> list[Entity]:
        return [e for e in self.entities.values()
                if e.team == team and e.kind == kind]

    def build_rounds(self, team: str, kind: str) -> list[int]:
        return sorted(e.spawn_round for e in self.team_entities(team, kind))

    def count_at(self, team: str, kind: str, upto_round: int) -> int:
        """Entities of `kind` alive at the end of `upto_round`."""
        return sum(
            1 for e in self.team_entities(team, kind)
            if e.spawn_round <= upto_round
            and (e.death_round is None or e.death_round > upto_round)
        )

    def core_damage_rounds(self, team: str) -> list[tuple[int, int]]:
        """(round, damage) events against `team`'s Core, damage positive."""
        cid = self.core_id[team]
        return [(r, -d) for r, eid, d in self.hp_events if eid == cid and d < 0]

    def core_hp_at(self, team: str, upto_round: int) -> int:
        cid = self.core_id[team]
        hp = self.entities[cid].max_hp
        for r, eid, d in self.hp_events:
            if eid == cid and r <= upto_round:
                hp = min(self.entities[cid].max_hp, hp + d)
        return max(0, hp)


def decode(path: str | Path) -> Replay:
    top = fields(Path(path).read_bytes())

    snapshot_raw = next(value for number, _, value in top if number == 1)
    snapshot = message_dict(snapshot_raw)
    width = snapshot.get(1, [0])[0]
    height = snapshot.get(2, [0])[0]

    entities: dict[int, Entity] = {}
    core_id: dict[str, int] = {}
    # Snapshot field 4: the two Cores. Field 1 = entity id, field 2 = team
    # (absent = A, 1 = B), field 3 = position. Verified against the twins
    # atlas anchors: id 1 team A at (2,2), id 2 team B at (2,17).
    for raw in snapshot.get(4, []):
        core = message_dict(raw)
        cid = core[1][0]
        team = "b" if core.get(2, [0])[0] == 1 else "a"
        pos = position(core[3][0]) if 3 in core else (0, 0)
        entities[cid] = Entity(cid, team, "core", -1, pos, 500, 500)
        core_id[team] = cid

    hp_events: list[tuple[int, int, int]] = []
    round_number = -1
    winner = None
    win_condition = ""
    for number, _, value in top:
        if number == 4:
            winner = value
            continue
        if number == 6:
            win_condition = value.decode("ascii", "replace")
            continue
        if number != 3:
            continue
        round_number += 1
        for _, _, raw_event in fields(value):
            event = unwrap(raw_event)
            numbers = {f for f, _, _ in event}
            values = {f: v for f, _, v in event}
            if {1, 3, 4, 5}.issubset(numbers):
                # Spawn/build event (a field-1 chain, flattened by unwrap).
                markers = numbers - KNOWN_FIELDS
                kind = MARKERS.get(next(iter(markers)), f"unknown{markers}") \
                    if markers else "builder?"
                team = "b" if values.get(2, 0) == 1 else "a"
                eid = values[1]
                entities[eid] = Entity(
                    eid, team, kind, round_number, position(values[3]),
                    values[4], values[5],
                )
                continue
            if len(event) != 1:
                continue
            number, _, payload = event[0]
            if number == 2 and isinstance(payload, bytes):
                # Position change: {1: id, 2: pos}.
                msg = message_dict(payload)
                eid = msg.get(1, [None])[0]
                if eid in entities and 2 in msg:
                    # Entity.pos stays the spawn position; history has the rest.
                    entities[eid].move_rounds.append(round_number)
                    entities[eid].pos_history.append(
                        (round_number, position(msg[2][0]))
                    )
            elif number == 5 and isinstance(payload, bytes):
                # HP delta: {1: id, 2: two's-complement varint}.
                msg = message_dict(payload)
                eid = msg.get(1, [None])[0]
                if eid in entities and 2 in msg:
                    hp_events.append((round_number, eid, signed(msg[2][0])))

    # Derive death rounds from cumulative HP.
    hp_now = {eid: e.hp for eid, e in entities.items()}
    for r, eid, delta in hp_events:
        if entities[eid].death_round is not None:
            continue
        hp_now[eid] = min(entities[eid].max_hp, hp_now[eid] + delta)
        if hp_now[eid] <= 0:
            entities[eid].death_round = r

    return Replay(
        width=width, height=height, rounds=round_number + 1, winner=winner,
        win_condition=win_condition, core_id=core_id, entities=entities,
        hp_events=hp_events,
    )
