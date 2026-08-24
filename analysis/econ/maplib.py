"""Minimal reader/writer for .map26 (protobuf: w=1, h=2, rows=3{cells=1})."""
from pathlib import Path

EMPTY, WALL, ORE = 0, 1, 2


def _varint(b, i):
    v = s = 0
    while True:
        c = b[i]; i += 1
        v |= (c & 0x7F) << s
        if not c & 0x80:
            return v, i
        s += 7


def _put_varint(v):
    out = bytearray()
    while True:
        c = v & 0x7F
        v >>= 7
        out.append(c | (0x80 if v else 0))
        if not v:
            return bytes(out)


def read_map(path):
    b = Path(path).read_bytes()
    i = 0
    w = h = None
    rows = []
    while i < len(b):
        key, i = _varint(b, i)
        field, wire = key >> 3, key & 7
        if wire == 0:
            val, i = _varint(b, i)
            if field == 1:
                w = val
            elif field == 2:
                h = val
        elif wire == 2:
            ln, i = _varint(b, i)
            payload = b[i:i + ln]; i += ln
            if field == 3:
                k2, j = _varint(payload, 0)
                assert k2 == 0x0a, k2
                ln2, j = _varint(payload, j)
                rows.append(list(payload[j:j + ln2]))
        else:
            raise ValueError(wire)
    assert len(rows) == h and all(len(r) == w for r in rows), (w, h, len(rows))
    return w, h, rows


def write_map(path, rows):
    h = len(rows); w = len(rows[0])
    out = bytearray()
    out += b"\x08" + _put_varint(w)
    out += b"\x10" + _put_varint(h)
    for r in rows:
        cells = bytes(r)
        inner = b"\x0a" + _put_varint(len(cells)) + cells
        out += b"\x1a" + _put_varint(len(inner)) + inner
    Path(path).write_bytes(bytes(out))


def render(w, h, rows):
    ch = {EMPTY: ".", WALL: "#", ORE: "O"}
    return "\n".join("".join(ch[c] for c in r) for r in rows)


def _entity_msg(eid, team, x, y):
    """Field 4 entity: {id:1, team:2 (0=A,1=B), pos:3{x:1,y:2}}. Proto3 omits zeros."""
    pos = b"\x08" + _put_varint(x) + b"\x10" + _put_varint(y)
    body = b"\x08" + _put_varint(eid)
    if team:
        body += b"\x10" + _put_varint(team)
    body += b"\x1a" + _put_varint(len(pos)) + pos
    return b"\x22" + _put_varint(len(body)) + body


def write_map_with_cores(path, rows, core_a, core_b):
    h = len(rows); w = len(rows[0])
    out = bytearray()
    out += b"\x08" + _put_varint(w) + b"\x10" + _put_varint(h)
    for r in rows:
        cells = bytes(r)
        inner = b"\x0a" + _put_varint(len(cells)) + cells
        out += b"\x1a" + _put_varint(len(inner)) + inner
    out += _entity_msg(1, 0, core_a[0], core_a[1])
    out += _entity_msg(2, 1, core_b[0], core_b[1])
    Path(path).write_bytes(bytes(out))
