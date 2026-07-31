import sys


def read_varint(data, offset):
    value = 0
    shift = 0
    while True:
        b = data[offset]
        offset += 1
        value |= (b & 0x7F) << shift
        if b < 0x80:
            return value, offset
        shift += 7


def fields(data, offset=0, end=None):
    if end is None:
        end = len(data)
    out = []
    while offset < end:
        key, offset = read_varint(data, offset)
        fn, wt = key >> 3, key & 0x07
        if wt == 0:
            v, offset = read_varint(data, offset)
        elif wt == 1:
            v, offset = data[offset:offset + 8], offset + 8
        elif wt == 2:
            ln, offset = read_varint(data, offset)
            v, offset = data[offset:offset + ln], offset + ln
        elif wt == 5:
            v, offset = data[offset:offset + 4], offset + 4
        else:
            raise ValueError(wt)
        out.append((fn, wt, v))
    return out


def dump(path):
    data = open(path, 'rb').read()
    top = fields(data)
    w = h = None
    rows = []
    cores = []
    for fn, wt, v in top:
        if fn == 1:
            w = v
        elif fn == 2:
            h = v
        elif fn == 3:
            sub = fields(v)
            for sfn, swt, sv in sub:
                if sfn == 1:
                    rows.append(sv)
        elif fn == 4:
            sub = fields(v)
            core = {}
            for sfn, swt, sv in sub:
                if sfn == 1:
                    core['owner'] = sv
                elif sfn == 2:
                    core['f2'] = sv
                elif sfn == 3:
                    pos = {}
                    for pfn, pwt, pv in fields(sv):
                        pos[pfn] = pv
                    core['pos'] = pos
            cores.append(core)
    return w, h, rows, cores


def varint(n):
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        if n:
            out.append(b | 0x80)
        else:
            out.append(b)
            return bytes(out)


def tag(fn, wt):
    return varint((fn << 3) | wt)


def ld(fn, payload):
    return tag(fn, 2) + varint(len(payload)) + payload


def encode(w, h, grid, cores):
    """grid: list of h strings/bytes each of len w with values 0/1/2.
    cores: list of (owner, x, y)."""
    out = bytearray()
    out += tag(1, 0) + varint(w)
    out += tag(2, 0) + varint(h)
    for y in range(h):
        row = bytes(grid[y])
        assert len(row) == w
        out += ld(3, ld(1, row))
    for (owner, x, y) in cores:
        pos = tag(1, 0) + varint(x) + tag(2, 0) + varint(y)
        body = tag(1, 0) + varint(owner)
        if owner == 2:
            body += tag(2, 0) + varint(1)
        body += ld(3, pos)
        out += ld(4, body)
    return bytes(out)


if __name__ == '__main__':
    w, h, rows, cores = dump(sys.argv[1])
    print('w', w, 'h', h, 'nrows', len(rows))
    for y, r in enumerate(rows):
        print(y, ''.join('.#o'[b] if b < 3 else '?' for b in r))
    print(cores)
    # round trip check
    enc = encode(w, h, rows, [(c['owner'], c['pos'].get(1, 0), c['pos'].get(2, 0)) for c in cores])
    orig = open(sys.argv[1], 'rb').read()
    print('roundtrip identical:', enc == orig, len(enc), len(orig))
