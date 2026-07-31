"""Timeline of a .replay26.

Event schema recovered from raw dumps (each round is a list of f1 events, each holding one
sub-message whose FIELD NUMBER is the event kind):

    f1  SPAWN   {1:id, 2:team(B only), 3:pos, 4:hp, 5:maxhp, <typefield>:{}}
    f2  MOVE    {1:id, 2:pos}
    f3  DESTROY {1:id}
    f5  HP      {1:id, 2:delta as 64-bit two's complement}
    f7  action cooldown   f8 move cooldown   f9 cooldown tick
    f12 FIRE    {1:from_pos, 2:to_pos}
    f13 builder range-0 shot {1:builder id}
"""
import sys
from mapio import fields

TYPE = {10: 'BUILDER', 11: 'CONVEYOR', 12: 'SPLITTER', 13: 'BARRIER', 15: 'HARVESTER',
        21: 'GUNNER', 22: 'SENTINEL', 24: 'LAUNCHER', 18: 'BARRIER?', 20: 'LAUNCHER?'}


def zz(v):
    return v - (1 << 64) if v >= (1 << 63) else v


def pos(v):
    d = {f: x for f, _, x in fields(v)}
    return (d.get(1, 0), d.get(2, 0))


def parse(path):
    data = open(path, 'rb').read()
    rounds, winner, cond = [], None, None
    for fn, wt, v in fields(data):
        if fn == 3:
            rounds.append(v)
        elif fn == 4 and wt == 0:
            winner = v
        elif fn == 6:
            cond = v
    return rounds, winner, cond


def events(path):
    """Yield (round, kind, payload-dict) for every event."""
    rounds, winner, cond = parse(path)
    for ri, rv in enumerate(rounds):
        for fn, wt, v in fields(rv):
            if fn != 1:
                continue
            for k, kw, kv in fields(v):
                yield ri, k, kv
    return


class Game:
    def __init__(self, path):
        self.path = path
        rounds, self.winner, self.cond = parse(path)
        self.nrounds = len(rounds)
        self.ent = {}       # id -> dict(team,type,pos,maxhp,hp,born,died)
        self.fires = []     # (round, from, to)
        self.chips = []     # (round, builder id)
        self.log = []       # (round, text)
        for ri, rv in enumerate(rounds):
            for fn, wt, v in fields(rv):
                if fn != 1:
                    continue
                for k, kw, kv in fields(v):
                    self._ev(ri, k, kv)

    def _ev(self, ri, k, v):
        if k == 1:
            # spawn is wrapped one extra level: f1{ f1{ f1{ ...body... } } }
            inner = fields(v)
            if len(inner) == 1 and inner[0][0] == 1 and inner[0][1] == 2:
                v = inner[0][2]
            d = {}
            for f, w, x in fields(v):
                d.setdefault(f, []).append(x)
            if 1 not in d or 3 not in d or 5 not in d:
                return
            eid = d[1][0]
            marker = [f for f in d if f not in (1, 2, 3, 4, 5)]
            t = TYPE.get(marker[0], f'T{marker}') if marker else '?'
            self.ent[eid] = dict(team='B' if 2 in d else 'A', type=t,
                                 pos=pos(d[3][0]), maxhp=d[5][0], hp=d[4][0],
                                 born=ri, died=None, dmg=0, healed=0)
            return
        d = {f: x for f, w, x in fields(v)}
        if k == 2:
            e = self.ent.get(d.get(1))
            if e:
                e['pos'] = pos(d[2])
        elif k == 3:
            e = self.ent.get(d.get(1))
            if e and e['died'] is None:
                e['died'] = ri
        elif k == 5:
            e = self.ent.get(d.get(1))
            if e:
                delta = zz(d.get(2, 0))
                e['hp'] += delta
                if delta < 0:
                    e['dmg'] -= delta
                else:
                    e['healed'] += delta
        elif k == 12:
            self.fires.append((ri, pos(d[1]), pos(d[2])))
        elif k == 13:
            self.chips.append((ri, d.get(1)))


def summary(path, verbose=False):
    g = Game(path)
    cond = g.cond.decode() if isinstance(g.cond, bytes) else g.cond
    print(f"== {path}")
    print(f"   winner_field={g.winner} cond={cond} rounds={g.nrounds}")
    for team in ('A', 'B'):
        rows = [(e['born'], i, e) for i, e in g.ent.items() if e['team'] == team]
        rows.sort()
        parts = []
        for born, i, e in rows:
            if e['type'] == 'BUILDER':
                continue
            d = f"d{e['died']}" if e['died'] is not None else ('' if e['hp'] >= e['maxhp'] else f"hp{e['hp']}")
            parts.append(f"r{born}:{e['type'][:4]}{e['pos']}{d}")
        print(f"   {team} buildings: " + "  ".join(parts))
    # fire accounting
    from collections import Counter
    ftgt = Counter()
    for ri, a, b in g.fires:
        ftgt[(a, b)] += 1
    print("   shots (from->to xN):",
          "  ".join(f"{a}->{b} x{n}" for (a, b), n in ftgt.most_common(14)))
    if verbose:
        for ri, a, b in g.fires:
            print(f"      r{ri} FIRE {a} -> {b}")
    return g


if __name__ == '__main__':
    for p in sys.argv[1:]:
        summary(p)
        print()
