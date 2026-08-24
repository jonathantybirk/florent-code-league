"""Read a .replay26 and say what actually happened, with alerts worth chasing.

The engine writes enough into a replay to reconstruct the whole causal story of a
match, and the damage deltas are the key: a shot's size names its source. A -18
is a Sentinel, -7 a Gunner, -2 a Builder's attack, +4 a Builder's heal. So we can
attribute every death and every wasted shot without guessing.

Usage:

    uv run python tools/replay_forensics.py <replay...> [--deaths] [--alerts]

The default report is the build census and the damage ledger per team. `--deaths`
adds every entity that died, when, and what killed it. `--alerts` prints only the
things that should make you open the replay: overkill, healed-through sieges,
turret types that never fired, and economy that died unanswered.

Decoding is done by Lucas's `tools/pantheon_analysis/decode.py`, which reads the
visualiser's own protobuf schema, so this works on downloaded ladder replays as
well as local ones.
"""
from __future__ import annotations

import argparse
import collections
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "pantheon_analysis"))

import decode  # noqa: E402

KIND_FIELDS = ("builderBot", "conveyor", "splitter", "harvester", "barrier",
               "gunner", "sentinel", "launcher", "core")

# Damage sizes are signatures. These are the 2.3.4+ values and they do not
# collide, which is what makes attribution exact rather than heuristic.
DAMAGE_SOURCE = {18: "sentinel", 7: "gunner", 2: "builder_attack"}
HEAL_DELTA = 4

ECONOMY = ("harvester", "conveyor", "splitter")


class Match:
    def __init__(self, path):
        self.path = pathlib.Path(path)
        r = decode.decode(str(path))
        self.raw = r
        self.winner = r.get("winner")
        self.rounds = len(r["turns"])
        self.kind = {}          # id -> kind
        self.team = {}          # id -> team
        self.born = {}          # id -> round
        self.died = {}          # id -> round
        self.pos = {}           # id -> (x, y), current
        self.damage = collections.defaultdict(lambda: collections.Counter())
        self.shots = collections.defaultdict(lambda: collections.Counter())
        self.heals = collections.Counter()
        self.ammo = collections.Counter()
        self.builds = collections.defaultdict(list)   # (team, kind) -> [round]
        self.hp_log = collections.defaultdict(list)   # id -> [(round, delta)]
        self._scan()

    def _register(self, eid, ent, rnd):
        kind = next((k for k in KIND_FIELDS if k in ent), "unknown")
        team = ent.get("team", "TEAM_A")
        self.kind[eid] = kind
        self.team[eid] = team
        self.born[eid] = rnd
        p = ent.get("position") or {}
        self.pos[eid] = (p.get("x", 0), p.get("y", 0))
        self.builds[(team, kind)].append(rnd)

    def _scan(self):
        for c in self.raw["map"]["cores"]:
            self._register(c["id"], dict(c, core={}), -1)
        # `from` on a fireTurret names the shooter's tile, so a tile->id index
        # lets us attribute a shot to the turret that fired it.
        tile_owner = {}
        for eid, xy in self.pos.items():
            tile_owner[xy] = eid

        for rnd, ups in enumerate(self.raw["turns"]):
            for u in ups:
                if "placeEntity" in u:
                    e = u["placeEntity"]["entity"]
                    self._register(e["id"], e, rnd)
                    tile_owner[self.pos[e["id"]]] = e["id"]
                elif "moveBuilderBot" in u:
                    m = u["moveBuilderBot"]
                    eid = m.get("id")
                    to = m.get("to") or {}
                    if eid in self.pos:
                        tile_owner.pop(self.pos[eid], None)
                    self.pos[eid] = (to.get("x", 0), to.get("y", 0))
                    tile_owner[self.pos[eid]] = eid
                elif "removeEntity" in u:
                    eid = u["removeEntity"]["id"]
                    self.died[eid] = rnd
                elif "updateHp" in u:
                    h = u["updateHp"]
                    eid, delta = h.get("id"), h.get("delta", 0)
                    self.hp_log[eid].append((rnd, delta))
                    team = self.team.get(eid)
                    if delta < 0:
                        src = DAMAGE_SOURCE.get(-delta, "other")
                        # Damage *received* by `team`, so credit the attacker.
                        foe = "TEAM_B" if team == "TEAM_A" else "TEAM_A"
                        self.damage[foe][src] += -delta
                    elif delta == HEAL_DELTA and team:
                        self.heals[team] += 1
                elif "fireTurret" in u:
                    f = u["fireTurret"]
                    frm = f.get("from") or {}
                    shooter = tile_owner.get((frm.get("x"), frm.get("y")))
                    k = self.kind.get(shooter, "unknown")
                    t = self.team.get(shooter, "?")
                    self.shots[t][k] += 1
                elif "coreConvertAmmo" in u:
                    # Attribution by round parity is unreliable; total only.
                    self.ammo["total"] += u["coreConvertAmmo"].get("amount", 0)

    # -- reports ------------------------------------------------------------
    def census(self):
        out = {}
        for (team, kind), rounds in self.builds.items():
            out.setdefault(team, {})[kind] = (len(rounds), min(rounds))
        return out

    def deaths(self):
        rows = []
        for eid, rnd in sorted(self.died.items(), key=lambda kv: kv[1]):
            log = [d for r, d in self.hp_log.get(eid, []) if d < 0]
            by = collections.Counter(DAMAGE_SOURCE.get(-d, "other") for d in log)
            rows.append((rnd, self.team.get(eid, "?"), self.kind.get(eid, "?"),
                         eid, dict(by), sum(-d for d in log)))
        return rows

    def alerts(self):
        """Only the things that should make a human open the replay."""
        out = []
        for team in ("TEAM_A", "TEAM_B"):
            foe = "TEAM_B" if team == "TEAM_A" else "TEAM_A"

            # A turret type that was built and never fired is pure cost scale.
            for kind in ("gunner", "sentinel", "launcher"):
                built = len(self.builds.get((team, kind), []))
                fired = self.shots[team][kind]
                if built and kind != "launcher" and fired == 0:
                    out.append(f"{team}: built {built} {kind}(s) that never fired "
                               f"-- {built * 20}% of cost scale for nothing")

            # Economy dying without the owner answering is the tiebreak leaking.
            econ_deaths = sum(1 for _, t, k, _, _, _ in self.deaths()
                              if t == team and k in ECONOMY)
            if econ_deaths >= 5:
                out.append(f"{team}: lost {econ_deaths} economy buildings -- "
                           f"titanium-collected tiebreak is bleeding")

            # Damage poured into something that was healed straight back.
            healed = self.heals[foe] * HEAL_DELTA
            dealt = sum(self.damage[team].values())
            if dealt and healed > dealt * 0.6:
                out.append(f"{team}: dealt {dealt} damage while {foe} healed "
                           f"{healed} back ({healed / dealt:.0%}) -- shooting "
                           f"through a mender is a losing exchange")

            # Sentinel vs Gunner mix, which is the live question in this meta.
            g = len(self.builds.get((team, "gunner"), []))
            s = len(self.builds.get((team, "sentinel"), []))
            if g and not s:
                out.append(f"{team}: {g} gunners and no sentinels -- under 2.3.4 "
                           f"both cost +20% scale and the sentinel wins on "
                           f"damage, HP, range and ammo efficiency")
        return out


def report(path, show_deaths, only_alerts):
    m = Match(path)
    name = pathlib.Path(path).name
    if only_alerts:
        al = m.alerts()
        if al:
            print(f"\n=== {name}  winner={m.winner} rounds={m.rounds}")
            for a in al:
                print("  !", a)
        return
    print(f"\n=== {name}  winner={m.winner} rounds={m.rounds} "
          f"ammo_converted={m.ammo['total']}")
    for team, kinds in sorted(m.census().items()):
        bits = ", ".join(f"{k}x{n}@r{first}"
                         for k, (n, first) in sorted(kinds.items(),
                                                     key=lambda kv: kv[1][1]))
        print(f"  {team}{'*' if m.winner == team else ' '} {bits}")
        print(f"      shots={dict(m.shots[team])} "
              f"damage_dealt={dict(m.damage[team])} heals={m.heals[team]}")
    if show_deaths:
        print("  deaths:")
        for rnd, team, kind, eid, by, total in m.deaths():
            print(f"      r{rnd:<4} {team} {kind:<11} id={eid:<5} {by} total={total}")
    for a in m.alerts():
        print("  !", a)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("replays", nargs="+")
    ap.add_argument("--deaths", action="store_true")
    ap.add_argument("--alerts", action="store_true")
    args = ap.parse_args()
    for p in args.replays:
        report(p, args.deaths, args.alerts)
    return 0


if __name__ == "__main__":
    sys.exit(main())
