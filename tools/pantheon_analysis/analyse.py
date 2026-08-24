"""Extract Pantheon's behavioural profile from decoded ladder replays."""
from __future__ import annotations
import glob, json, os, collections
import decode

HERE = os.path.dirname(os.path.abspath(__file__))
MATCHES = json.load(open(f"{HERE}/pantheon/matches.json"))["matches"]
SIDE = {}   # match id -> "TEAM_A"/"TEAM_B" for Pantheon
OPP = {}
for m in MATCHES:
    if m["teamAName"] == "Pantheon":
        SIDE[m["id"]], OPP[m["id"]] = "TEAM_A", m["teamBName"]
    elif m["teamBName"] == "Pantheon":
        SIDE[m["id"]], OPP[m["id"]] = "TEAM_B", m["teamAName"]


def team_of(ent):
    return ent.get("team", "TEAM_A")


class Game:
    def __init__(self, path):
        base = os.path.basename(path)
        self.mid = base.split("_game_")[0]
        self.game_no = int(base.split("_game_")[1].split(".")[0])
        self.side = SIDE.get(self.mid)
        self.opp = OPP.get(self.mid)
        r = decode.decode(path)
        self.raw = r
        self.w, self.h = r["map"]["width"], r["map"]["height"]
        self.grid = r["map"]["grid"]
        self.cores = {c.get("team", "TEAM_A"): c for c in r["map"]["cores"]}
        self.my_core = self.cores[self.side]["pos"] if self.side else None
        other = "TEAM_B" if self.side == "TEAM_A" else "TEAM_A"
        self.enemy_core = self.cores[other]["pos"] if self.side else None
        self.winner = r["winner"]
        self.won = (self.winner == self.side)
        self.entities = {}          # id -> dict(kind, team, spawn, pos, path)
        self.builds = []            # (round, kind, pos, builder_id)
        self.throws = []            # (round, builder_id, frm, to, dist)
        self.walks = []             # (round, builder_id, frm, to)
        self.convert = []           # (round, amount)
        self.fires = []             # (round, frm, to)
        self.econ = []              # (round, titanium, ammo)
        self.deaths = {}            # id -> round
        self.hp = collections.defaultdict(list)
        self._scan(r)

    def _scan(self, r):
        pos_now = {}
        for c in r["map"]["cores"]:
            t = c.get("team", "TEAM_A")
            self.entities[c["id"]] = dict(kind="core", team=t, spawn=-1, pos=c["pos"])
            pos_now[c["id"]] = c["pos"]
        for rnd, ups in enumerate(r["turns"]):
            for u in ups:
                if "placeEntity" in u:
                    e = u["placeEntity"]["entity"]
                    t = team_of(e)
                    p = decode.pos(e.get("position", {}))
                    k = decode.entity_kind(e)
                    self.entities[e["id"]] = dict(kind=k, team=t, spawn=rnd, pos=p,
                                                  hp=e.get("hp"), maxHp=e.get("maxHp"))
                    pos_now[e["id"]] = p
                    if t == self.side:
                        self.builds.append((rnd, k, p))
                elif "moveBuilderBot" in u:
                    mv = u["moveBuilderBot"]
                    i = mv["id"]
                    to = decode.pos(mv.get("to", {}))
                    frm = pos_now.get(i)
                    pos_now[i] = to
                    ent = self.entities.get(i)
                    if not ent or ent["team"] != self.side or frm is None:
                        continue
                    d = max(abs(to[0]-frm[0]), abs(to[1]-frm[1]))
                    (self.throws if d > 1 else self.walks).append((rnd, i, frm, to, d))
                elif "coreConvertAmmo" in u:
                    cv = u["coreConvertAmmo"]
                    if cv.get("team", "TEAM_A") == self.side:
                        self.convert.append((rnd, cv.get("amount", 0)))
                elif "fireTurret" in u:
                    ft = u["fireTurret"]
                    self.fires.append((rnd, decode.pos(ft.get("from", {})),
                                       decode.pos(ft.get("to", {}))))
                elif "removeEntity" in u:
                    self.deaths.setdefault(u["removeEntity"]["id"], rnd)
                elif "updateHp" in u:
                    self.hp[u["updateHp"]["id"]].append((rnd, u["updateHp"].get("delta", 0)))
                elif "updatePlayers" in u:
                    pl = u["updatePlayers"]["players"]
                    side = pl.get("a" if self.side == "TEAM_A" else "b", {})
                    self.econ.append((rnd, side.get("titanium", 0), side.get("ammo", 0)))
        self.rounds = len(r["turns"])

    # ---- derived views -------------------------------------------------
    def rel(self, p):
        """Position relative to own core, oriented so +x points at the enemy."""
        cx, cy = self.my_core
        ex, ey = self.enemy_core
        dx, dy = p[0]-cx, p[1]-cy
        sx = 1 if ex >= cx else -1
        sy = 1 if ey >= cy else -1
        return (dx*sx, dy*sy)

    def my(self, kind):
        return [(i, e) for i, e in self.entities.items()
                if e["team"] == self.side and e["kind"] == kind]

    def core_death_round(self):
        other = "TEAM_B" if self.side == "TEAM_A" else "TEAM_A"
        cid = self.cores[other]["id"]
        return self.deaths.get(cid)


def load_all():
    games = []
    for f in sorted(glob.glob(f"{HERE}/pantheon/rp/*.replay26")):
        mid = os.path.basename(f).split("_game_")[0]
        if mid not in SIDE:
            continue
        try:
            games.append(Game(f))
        except Exception as exc:
            print("skip", f, exc)
    return games


if __name__ == "__main__":
    gs = load_all()
    print(f"{len(gs)} games, {sum(g.won for g in gs)} won")
    sizes = collections.Counter((g.w, g.h) for g in gs)
    print("map sizes:", sizes.most_common())
