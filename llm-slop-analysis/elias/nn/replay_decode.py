"""Decode a `.replay26` into a full per-turn state trace.

The format is protobuf (`battlecode.Replay`). The schema is not shipped as a
`.proto`; it is embedded as a protobuf.js JSON descriptor in the bundled web
visualiser, `fcode/data/visualiser/assets/main-*.js`, in the object assigned to
`yl` (search for `nested:{battlecode:`). This module reimplements that schema by
hand -- no protobuf runtime is installed and none is needed, the wire format is
five wire types and we only use two.

Schema (verbatim from the visualiser descriptor)::

    Replay { Map map = 1; repeated Turn turns = 3; Team winner = 4; }
    Map    { int32 width = 1; int32 height = 2;
             repeated TileRow rows = 3; repeated CorePosition cores = 4; }
    Turn   { repeated Update updates = 1; }
    Update = oneof {
        1  PlaceEntity{Entity}      9  BotOutput{id,stdout,execTimeUs,tled}
        2  MoveBuilderBot{id,to}   10  IndicatorLine{id,posA,posB,r,g,b}
        3  RemoveEntity{id}        11  IndicatorDot{id,pos,r,g,b}
        4  DistributeResources     12  FireTurret{from,to}
        5  UpdateHp{id,delta}      13  BuilderAttack{id,target}
        6  UpdatePlayers{Players}  14  CoreConvertAmmo{team,amount}
        7  SetActionCooldown{id,v} 15  BuilderHeal{id,target}
        8  SetMoveCooldown{id,v}   16  BuilderBuild{id,target}
    }
    Entity { id=1 team=2 position=3 hp=4 maxHp=5
             oneof kind: builderBot=10 conveyor=11 splitter=12 harvester=15
                         barrier=18 core=20 gunner=21 sentinel=22 launcher=24 }

What is NOT in the replay, and therefore not recoverable from it:
  * the 16 communication-store slots (no update message carries a store write);
  * `rotate()` on a gunner (no direction-change update exists);
  * the distinction between `destroy()`, `self_destruct()` and death by damage
    (all three surface as RemoveEntity);
  * which of several legal builds a `BuilderBuild` was, except by matching the
    PlaceEntity emitted in the same turn;
  * any unit that chose to do nothing (no update is emitted, though BotOutput
    is emitted for every unit that ran, which is what lets us tell "ran and
    passed" from "was not alive").

Usage::

    from replay_decode import load_replay
    rep = load_replay("game.replay26")
    for turn, state, actions in rep.iter_states():
        ...
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterator


# --------------------------------------------------------------------------
# wire-level protobuf
# --------------------------------------------------------------------------

def _read_varint(buf: bytes, i: int) -> tuple[int, int]:
    shift = 0
    value = 0
    while True:
        b = buf[i]
        i += 1
        value |= (b & 0x7F) << shift
        if b < 0x80:
            return value, i
        shift += 7
        if shift > 70:
            raise ValueError("varint too long")


def _zigzag(n: int) -> int:
    return (n >> 1) ^ -(n & 1)


def parse(buf: bytes) -> dict[int, list[Any]]:
    """Parse one message into {field_number: [raw values]}.

    Varints stay ints; length-delimited fields stay bytes. Nothing is typed at
    this level -- the typed readers below decide what a field means.
    """
    out: dict[int, list[Any]] = {}
    i = 0
    n = len(buf)
    while i < n:
        key, i = _read_varint(buf, i)
        fnum, wire = key >> 3, key & 7
        if wire == 0:
            v, i = _read_varint(buf, i)
        elif wire == 2:
            ln, i = _read_varint(buf, i)
            v = buf[i:i + ln]
            i += ln
        elif wire == 5:
            v = int.from_bytes(buf[i:i + 4], "little")
            i += 4
        elif wire == 1:
            v = int.from_bytes(buf[i:i + 8], "little")
            i += 8
        else:
            raise ValueError(f"unsupported wire type {wire}")
        out.setdefault(fnum, []).append(v)
    return out


def _one(fields: dict[int, list[Any]], num: int, default: Any = None) -> Any:
    vals = fields.get(num)
    return vals[-1] if vals else default


def _pos(raw: bytes | None) -> tuple[int, int] | None:
    if raw is None:
        return None
    f = parse(raw)
    return (_one(f, 1, 0), _one(f, 2, 0))


# --------------------------------------------------------------------------
# enums (values verbatim from the visualiser descriptor)
# --------------------------------------------------------------------------

TEAM = {0: "a", 1: "b"}
DIRECTION = {
    0: "centre", 1: "north", 2: "northeast", 3: "east", 4: "southeast",
    5: "south", 6: "southwest", 7: "west", 8: "northwest",
}
ENVIRONMENT = {0: "empty", 1: "wall", 2: "ore_titanium", 3: "ore_axionite"}
RESOURCE = {0: None, 1: "titanium", 2: "raw_axionite", 3: "refined_axionite"}

#: Entity oneof field number -> EntityType string.
KIND_FIELD = {
    10: "builder_bot", 11: "conveyor", 12: "splitter", 15: "harvester",
    18: "barrier", 20: "core", 21: "gunner", 22: "sentinel", 24: "launcher",
}

MAX_HP = {
    "builder_bot": 40, "core": 500, "gunner": 40, "sentinel": 30,
    "launcher": 30, "conveyor": 20, "splitter": 20, "harvester": 30,
    "barrier": 30,
}

#: Cost-scale contribution per living entity (visualiser `computeTimeSeries`
#: takes this from a table; the scale is 100 + sum over living entities).
SCALE_WEIGHT = {
    "conveyor": 0, "splitter": 0, "barrier": 0,
    "harvester": 0, "gunner": 0, "sentinel": 0, "launcher": 0,
    "builder_bot": 0, "core": 0,
}


# --------------------------------------------------------------------------
# typed structures
# --------------------------------------------------------------------------

@dataclass
class Entity:
    id: int
    team: str
    x: int
    y: int
    hp: int
    max_hp: int
    kind: str
    direction: str | None = None
    stored: str | None = None
    stored_id: int | None = None
    ammo_type: str | None = None
    ammo_amount: int = 0
    action_cooldown: int = 0
    move_cooldown: int = 0
    harvester_cooldown: int = 0

    def copy(self) -> "Entity":
        return Entity(**self.__dict__)


@dataclass
class TurnActions:
    """Everything attributable to a decision in one turn."""
    moves: dict[int, tuple[int, int]] = field(default_factory=dict)         # id -> to
    builds: dict[int, tuple[int, int]] = field(default_factory=dict)        # id -> target
    build_kind: dict[int, tuple[str, str | None]] = field(default_factory=dict)  # id -> (kind, dir)
    attacks: dict[int, tuple[int, int]] = field(default_factory=dict)
    heals: dict[int, tuple[int, int]] = field(default_factory=dict)
    fires: list[tuple[tuple[int, int], tuple[int, int]]] = field(default_factory=list)
    removed: list[int] = field(default_factory=list)
    placed: list[Entity] = field(default_factory=list)
    convert_ammo: dict[str, int] = field(default_factory=dict)
    ran: dict[int, dict] = field(default_factory=dict)   # id -> {execTimeUs, tled, stdout}
    ran_order: list[int] = field(default_factory=list)
    resource_moves: list[tuple[tuple[int, int], tuple[int, int]]] = field(default_factory=list)
    indicator_lines: list[tuple] = field(default_factory=list)
    indicator_dots: list[tuple] = field(default_factory=list)
    hp_deltas: list[tuple[int, int]] = field(default_factory=list)


@dataclass
class PlayerState:
    titanium: int = 500
    ammo: int = 0
    titanium_collected: int = 0
    resources_collected: int = 0


@dataclass
class GameState:
    turn: int
    entities: dict[int, Entity]
    players: dict[str, PlayerState]

    def copy(self) -> "GameState":
        return GameState(
            self.turn,
            {i: e.copy() for i, e in self.entities.items()},
            {t: PlayerState(**p.__dict__) for t, p in self.players.items()},
        )


# --------------------------------------------------------------------------
# entity decode
# --------------------------------------------------------------------------

def _entity(raw: bytes) -> Entity | None:
    f = parse(raw)
    pos = _pos(_one(f, 3))
    if pos is None:
        return None
    kind = "barrier"
    sub: dict[int, list[Any]] = {}
    for fnum, name in KIND_FIELD.items():
        if fnum in f:
            kind = name
            sub = parse(f[fnum][-1])
            break
    e = Entity(
        id=_one(f, 1, 0), team=TEAM[_one(f, 2, 0)], x=pos[0], y=pos[1],
        hp=_one(f, 4, 0), max_hp=_one(f, 5, 0), kind=kind,
    )
    if kind == "builder_bot":
        e.action_cooldown = _one(sub, 1, 0)
        e.move_cooldown = _one(sub, 2, 0)
    elif kind in ("conveyor", "splitter"):
        e.direction = DIRECTION[_one(sub, 1, 0)]
        e.stored = RESOURCE[_one(sub, 2, 0)]
    elif kind == "harvester":
        e.harvester_cooldown = _one(sub, 1, 0)
        e.stored = RESOURCE[_one(sub, 2, 0)]
    elif kind == "core":
        e.action_cooldown = _one(sub, 1, 0)
    elif kind in ("gunner", "sentinel"):
        e.direction = DIRECTION[_one(sub, 1, 0)]
        e.ammo_type = RESOURCE[_one(sub, 2, 0)]
        e.ammo_amount = _one(sub, 3, 0)
    elif kind == "launcher":
        e.ammo_type = RESOURCE[_one(sub, 2, 0)]
        e.ammo_amount = _one(sub, 3, 0)
    return e


# --------------------------------------------------------------------------
# replay
# --------------------------------------------------------------------------

class Replay:
    def __init__(self, data: bytes):
        top = parse(data)
        raw_map = parse(_one(top, 1))
        self.width: int = _one(raw_map, 1, 0)
        self.height: int = _one(raw_map, 2, 0)
        self.env: list[list[int]] = []
        for raw_row in raw_map.get(3, []):
            row_fields = parse(raw_row)
            tiles: list[int] = []
            for v in row_fields.get(1, []):
                if isinstance(v, int):
                    tiles.append(v)
                else:                              # packed repeated enum
                    j = 0
                    while j < len(v):
                        t, j = _read_varint(v, j)
                        tiles.append(t)
            self.env.append(tiles)
        self.cores: list[tuple[int, str, int, int]] = []
        for raw_core in raw_map.get(4, []):
            cf = parse(raw_core)
            p = _pos(_one(cf, 3)) or (0, 0)
            self.cores.append((_one(cf, 1, 0), TEAM[_one(cf, 2, 0)], p[0], p[1]))
        self.raw_turns: list[bytes] = list(top.get(3, []))
        w = _one(top, 4)
        self.winner: str | None = TEAM[w] if w is not None else None
        self.total_turns = len(self.raw_turns)

    # -- initial state ----------------------------------------------------
    def initial_state(self) -> GameState:
        ents: dict[int, Entity] = {}
        for cid, team, x, y in self.cores:
            ents[cid] = Entity(cid, team, x, y, 500, 500, "core")
        return GameState(0, ents, {"a": PlayerState(), "b": PlayerState()})

    # -- one turn ---------------------------------------------------------
    def decode_turn(self, idx: int) -> TurnActions:
        ta = TurnActions()
        tf = parse(self.raw_turns[idx])
        for raw_update in tf.get(1, []):
            u = parse(raw_update)
            if 1 in u:
                e = _entity(parse(u[1][-1]).get(1, [b""])[-1])
                if e:
                    ta.placed.append(e)
            elif 2 in u:
                m = parse(u[2][-1])
                ta.moves[_one(m, 1, 0)] = _pos(_one(m, 2)) or (0, 0)
            elif 3 in u:
                ta.removed.append(_one(parse(u[3][-1]), 1, 0))
            elif 4 in u:
                d = parse(u[4][-1])
                for raw_mv in d.get(1, []):
                    mv = parse(raw_mv)
                    fr, to = _pos(_one(mv, 1)), _pos(_one(mv, 2))
                    if fr and to:
                        ta.resource_moves.append((fr, to))
            elif 5 in u:
                h = parse(u[5][-1])
                ta.hp_deltas.append((_one(h, 1, 0), _zigzag_or_signed(_one(h, 2, 0))))
            elif 6 in u:
                pl = parse(parse(u[6][-1]).get(1, [b""])[-1])
                for fnum, team in ((1, "a"), (2, "b")):
                    if fnum in pl:
                        pf = parse(pl[fnum][-1])
                        ta.__dict__.setdefault("_players", {})[team] = PlayerState(
                            titanium=_one(pf, 1, 0),
                            resources_collected=_one(pf, 3, 0),
                            titanium_collected=_one(pf, 4, 0),
                            ammo=_one(pf, 7, 0),
                        )
            elif 7 in u:
                c = parse(u[7][-1])
                ta.__dict__.setdefault("_acd", {})[_one(c, 1, 0)] = _one(c, 2, 0)
            elif 8 in u:
                c = parse(u[8][-1])
                ta.__dict__.setdefault("_mcd", {})[_one(c, 1, 0)] = _one(c, 2, 0)
            elif 9 in u:
                b = parse(u[9][-1])
                uid = _one(b, 1, 0)
                so = _one(b, 2)
                ta.ran[uid] = {
                    "exec_us": _one(b, 3, 0),
                    "tled": bool(_one(b, 4, 0)),
                    "stdout": so.decode("utf-8", "replace") if isinstance(so, bytes) else None,
                }
                ta.ran_order.append(uid)
            elif 10 in u:
                l = parse(u[10][-1])
                ta.indicator_lines.append(
                    (_one(l, 1, 0), _pos(_one(l, 2)), _pos(_one(l, 3)),
                     _one(l, 4, 0), _one(l, 5, 0), _one(l, 6, 0))
                )
            elif 11 in u:
                d = parse(u[11][-1])
                ta.indicator_dots.append(
                    (_one(d, 1, 0), _pos(_one(d, 2)),
                     _one(d, 3, 0), _one(d, 4, 0), _one(d, 5, 0))
                )
            elif 12 in u:
                fr_ = parse(u[12][-1])
                ta.fires.append((_pos(_one(fr_, 1)) or (0, 0), _pos(_one(fr_, 2)) or (0, 0)))
            elif 13 in u:
                a = parse(u[13][-1])
                ta.attacks[_one(a, 1, 0)] = _pos(_one(a, 2)) or (0, 0)
            elif 14 in u:
                c = parse(u[14][-1])
                ta.convert_ammo[TEAM[_one(c, 1, 0)]] = _one(c, 2, 0)
            elif 15 in u:
                h = parse(u[15][-1])
                ta.heals[_one(h, 1, 0)] = _pos(_one(h, 2)) or (0, 0)
            elif 16 in u:
                b = parse(u[16][-1])
                ta.builds[_one(b, 1, 0)] = _pos(_one(b, 2)) or (0, 0)
        # match each BuilderBuild to the PlaceEntity that landed on its target
        by_pos = {(e.x, e.y): e for e in ta.placed}
        for uid, tgt in ta.builds.items():
            e = by_pos.get(tgt)
            if e is not None:
                ta.build_kind[uid] = (e.kind, e.direction)
        return ta

    # -- apply ------------------------------------------------------------
    @staticmethod
    def apply(state: GameState, ta: TurnActions) -> None:
        for e in ta.placed:
            state.entities[e.id] = e
        for uid, to in ta.moves.items():
            if uid in state.entities:
                state.entities[uid].x, state.entities[uid].y = to
        for uid in ta.removed:
            state.entities.pop(uid, None)
        for uid, delta in ta.hp_deltas:
            if uid in state.entities:
                state.entities[uid].hp += delta
        for uid, v in ta.__dict__.get("_acd", {}).items():
            if uid in state.entities:
                state.entities[uid].action_cooldown = v
        for uid, v in ta.__dict__.get("_mcd", {}).items():
            if uid in state.entities:
                state.entities[uid].move_cooldown = v
        for team, ps in ta.__dict__.get("_players", {}).items():
            state.players[team] = ps
        for (fr, to) in ta.resource_moves:
            src = _find_at(state, fr)
            dst = _find_at(state, to)
            if src is None or dst is None:
                continue
            carried = src.stored or ("titanium" if src.kind == "harvester" else None)
            if carried is None:
                continue
            if src.kind == "harvester":
                src.harvester_cooldown = 3
            if dst.kind in ("gunner", "sentinel"):
                dst.ammo_type, dst.ammo_amount = carried, 10
            elif dst.kind == "launcher":
                dst.ammo_type, dst.ammo_amount = None, 0
            elif dst.kind != "core":
                dst.stored = carried
            src.stored = None

    @staticmethod
    def tick_cooldowns(state: GameState) -> None:
        for e in state.entities.values():
            if e.action_cooldown > 0:
                e.action_cooldown -= 1
            if e.move_cooldown > 0:
                e.move_cooldown -= 1
            if e.kind == "harvester" and e.harvester_cooldown > 0:
                e.harvester_cooldown -= 1

    def iter_states(self) -> Iterator[tuple[int, GameState, TurnActions]]:
        """Yield (turn, state_at_start_of_turn, actions_taken_that_turn).

        The state yielded is the state the bots SAW when they decided, i.e.
        after cooldown decay and before that turn's updates are applied.
        """
        state = self.initial_state()
        for t in range(1, self.total_turns + 1):
            state.turn = t
            self.tick_cooldowns(state)
            ta = self.decode_turn(t - 1)
            yield t, state, ta
            self.apply(state, ta)


def _zigzag_or_signed(v: int) -> int:
    """UpdateHp.delta is a proto3 `int32`, so negatives arrive as 10-byte
    two's-complement varints, not zigzag."""
    if v >= (1 << 63):
        v -= 1 << 64
    elif v >= (1 << 31):
        v -= 1 << 32
    return v


def _find_at(state: GameState, pos: tuple[int, int]) -> Entity | None:
    x, y = pos
    for e in state.entities.values():
        if e.kind == "builder_bot":
            continue
        if e.kind == "core":
            if abs(e.x - x) <= 1 and abs(e.y - y) <= 1:
                return e
        elif e.x == x and e.y == y:
            return e
    return None


def load_replay(path: str) -> Replay:
    with open(path, "rb") as fh:
        return Replay(fh.read())
