"""Full-schema .replay26 decoder, generated from the visualiser's protobuf JSON."""
from __future__ import annotations
from pathlib import Path
import json

SCHEMA = json.load(open(Path(__file__).parent / "schema.json"))["nested"]["battlecode"]["nested"]

ENUMS = {n: {v: k for k, v in b["values"].items()} for n, b in SCHEMA.items() if "values" in b}
MSGS = {n: b["fields"] for n, b in SCHEMA.items() if "fields" in b}
# field-number -> (name, type) per message
BYNUM = {n: {f["id"]: (k, f["type"], f.get("rule")) for k, f in fs.items()} for n, fs in MSGS.items()}

ENTITY_KINDS = {10: "builder", 11: "conveyor", 12: "splitter", 15: "harvester",
                18: "barrier", 20: "core", 21: "gunner", 22: "sentinel", 24: "launcher"}


def read_varint(data, off):
    val = shift = 0
    while True:
        b = data[off]; off += 1
        val |= (b & 0x7F) << shift
        if b < 0x80:
            return val, off
        shift += 7


def raw_fields(data):
    off, out = 0, []
    while off < len(data):
        key, off = read_varint(data, off)
        num, wire = key >> 3, key & 7
        if wire == 0:
            v, off = read_varint(data, off)
        elif wire == 1:
            v, off = data[off:off+8], off+8
        elif wire == 2:
            ln, off = read_varint(data, off)
            v, off = data[off:off+ln], off+ln
        elif wire == 5:
            v, off = data[off:off+4], off+4
        else:
            raise ValueError(f"wire {wire}")
        out.append((num, wire, v))
    return out


def zigzag(v):
    return (v >> 1) ^ -(v & 1)


def parse(data, msgname):
    """Decode bytes as message `msgname` into a dict of name -> value / [values]."""
    spec = BYNUM.get(msgname, {})
    out = {}
    for num, wire, v in raw_fields(data):
        if num not in spec:
            continue
        name, typ, rule = spec[num]
        # Packed repeated scalars/enums arrive as one length-delimited blob.
        if rule == "repeated" and wire == 2 and typ not in MSGS and typ != "string":
            off = 0
            for _ in iter(int, 1):
                if off >= len(v):
                    break
                n, off = read_varint(v, off)
                out.setdefault(name, []).append(ENUMS[typ].get(n, n) if typ in ENUMS else n)
            continue
        if typ in MSGS:
            val = parse(v, typ)
        elif typ in ENUMS:
            val = ENUMS[typ].get(v, v)
        elif typ == "string":
            val = v.decode("utf8", "replace") if isinstance(v, bytes) else v
        elif typ == "bool":
            val = bool(v)
        elif typ == "int32":
            val = v - (1 << 64) if v >= (1 << 63) else v
        else:
            val = v
        if rule == "repeated":
            out.setdefault(name, []).append(val)
        else:
            out[name] = val
    return out


def entity_kind(ent: dict) -> str:
    for num, kind in ENTITY_KINDS.items():
        nm = BYNUM["Entity"][num][0]
        if nm in ent:
            return kind
    return "?"


def pos(p):
    return (p.get("x", 0), p.get("y", 0))


def decode(path):
    """Return dict with map, per-round update lists, fully typed."""
    top = raw_fields(Path(path).read_bytes())
    out = {"map": None, "turns": [], "winner": None}
    for num, wire, v in top:
        if num == 1:
            m = parse(v, "Map")
            grid = [[t for t in row.get("tiles", [])] for row in m.get("rows", [])]
            out["map"] = {"width": m.get("width"), "height": m.get("height"),
                          "grid": grid,
                          "cores": [{"id": c["id"], "team": c.get("team", "TEAM_A"),
                                     "pos": pos(c["position"])} for c in m.get("cores", [])]}
        elif num == 3:
            turn = parse(v, "Turn")
            out["turns"].append(turn.get("updates", []))
        elif num == 4:
            out["winner"] = ENUMS["Team"].get(v, v)
    return out
