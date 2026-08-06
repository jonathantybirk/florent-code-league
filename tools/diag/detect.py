"""Detectors for behaviour a human cannot reliably spot by watching a replay.

Each detector answers one question about one game and returns countable findings, attributed to a
unit and a round range so it can be looked at in the visualiser afterwards. The point is not to
judge whether the bot won -- the arena does that -- but to surface the rounds it wasted getting
there, which is invisible in a win/loss column.

Every detector is deliberately opponent-agnostic and map-agnostic: it asks "did this unit do
something useless", never "did this unit fail to counter bot X".
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field

from .replay import Replay


BUILDINGS = {"conveyor", "splitter", "harvester", "barrier", "core", "gunner", "sentinel", "launcher"}
TURRETS = {"gunner", "sentinel", "launcher"}


@dataclass
class Finding:
    kind: str
    unit: int
    team: str
    rounds: tuple[int, int]
    detail: str

    def __str__(self) -> str:
        a, b = self.rounds
        span = f"r{a}" if a == b else f"r{a}-{b}"
        return f"{self.kind:<18} {self.team} unit {self.unit:<4} {span:<12} {self.detail}"


@dataclass
class Report:
    team: str
    turns: int
    winner: str | None
    findings: list[Finding] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    stats: dict[str, float] = field(default_factory=dict)

    def add(self, f: Finding) -> None:
        self.findings.append(f)
        self.counts[f.kind] += 1

    def summary_line(self) -> str:
        bits = " ".join(f"{k}={v}" for k, v in sorted(self.counts.items()))
        return f"[{self.team}] turns={self.turns} {bits}" if bits else f"[{self.team}] turns={self.turns} clean"


def _passable(rep: Replay, state, pos) -> bool:
    x, y = pos
    if not (0 <= x < rep.width and 0 <= y < rep.height):
        return False
    if rep.env[y][x] == 1:                       # WALL
        return False
    for e in state.entities.values():
        if (e.x, e.y) == pos and e.kind != "conveyor" and e.kind != "splitter":
            return False
        if e.kind == "core" and x in (e.x, e.x + 1) and y in (e.y, e.y + 1):
            return False
    return True


def _bfs(rep: Replay, state, start, goals) -> int | None:
    """Shortest cardinal walk from start to any goal over currently-passable ground."""
    if start in goals:
        return 0
    seen = {start}
    q = deque([(start, 0)])
    while q:
        p, d = q.popleft()
        for dx, dy in ((0, -1), (1, 0), (0, 1), (-1, 0)):
            n = (p[0] + dx, p[1] + dy)
            if n in seen:
                continue
            if n in goals:
                return d + 1
            if _passable(rep, state, n):
                seen.add(n)
                q.append((n, d + 1))
    return None


def analyse(path: str, team: str, *, idle_run: int = 6, osc_window: int = 12,
            osc_changes: int = 4, route_slack: float = 1.6) -> Report:
    """Run every detector over one replay for one team."""
    rep = Replay(open(path, "rb").read())
    out = Report(team=team, turns=rep.total_turns, winner=rep.winner)

    # per-unit history
    idle_streak: dict[int, int] = defaultdict(int)
    idle_start: dict[int, int] = {}
    idle_total: dict[int, int] = defaultdict(int)
    pos_hist: dict[int, deque] = defaultdict(lambda: deque(maxlen=osc_window))
    born: dict[int, int] = {}
    acted_ever: dict[int, bool] = defaultdict(bool)
    exec_us: list[int] = []
    tled = 0
    ammo_starved = 0
    turret_idle: dict[int, int] = defaultdict(int)

    for t, state, ta in rep.iter_states():
        mine = {i: e for i, e in state.entities.items() if e.team == team}
        for uid in ta.ran:
            e = state.entities.get(uid)
            if e is None or e.team != team:
                continue
            born.setdefault(uid, t)
            info = ta.ran[uid]
            if info.get("execTimeUs"):
                exec_us.append(info["execTimeUs"])
            if info.get("tled"):
                tled += 1
                out.add(Finding("TLE", uid, team, (t, t), "engine flagged a timeout"))

            did = (uid in ta.moves or uid in ta.builds or uid in ta.attacks
                   or uid in ta.heals or any(f[0] == (e.x, e.y) for f in ta.fires))
            if e.kind == "core":
                did = did or bool(ta.convert_ammo.get(team)) or any(
                    p.team == team for p in ta.placed)
            if did:
                acted_ever[uid] = True
                if idle_streak[uid] >= idle_run:
                    out.add(Finding("IDLE_RUN", uid, team,
                                    (idle_start[uid], t - 1),
                                    f"{idle_streak[uid]} consecutive rounds with no action"))
                idle_streak[uid] = 0
            else:
                if idle_streak[uid] == 0:
                    idle_start[uid] = t
                idle_streak[uid] += 1
                idle_total[uid] += 1

            if e.kind == "builder_bot":
                pos_hist[uid].append((e.x, e.y))

            # a turret that never fires is a dead investment
            if e.kind in ("gunner", "sentinel"):
                fired = any(f[0] == (e.x, e.y) for f in ta.fires)
                if not fired:
                    turret_idle[uid] += 1

        # ammo starvation: turrets exist but the pool is empty
        ps = state.players.get(team)
        if ps is not None and ps.ammo <= 0:
            if any(e.kind in ("gunner", "sentinel") for e in mine.values()):
                ammo_starved += 1

    # ---- post-pass detectors ------------------------------------------------
    for uid, hist in pos_hist.items():
        if len(hist) < osc_window:
            continue
        uniq = set(hist)
        if len(uniq) <= 2 and len(hist) >= osc_window:
            out.add(Finding("OSCILLATION", uid, team, (0, 0),
                            f"occupied only {len(uniq)} distinct tiles over the last "
                            f"{len(hist)} sampled rounds: {sorted(uniq)}"))

    for uid, n in idle_total.items():
        if n and rep.total_turns:
            frac = n / rep.total_turns
            if frac >= 0.5:
                out.add(Finding("MOSTLY_IDLE", uid, team, (born.get(uid, 0), rep.total_turns),
                                f"idle {n}/{rep.total_turns} rounds ({frac:.0%})"))

    for uid, n in turret_idle.items():
        if n >= 40:
            out.add(Finding("TURRET_SILENT", uid, team, (born.get(uid, 0), rep.total_turns),
                            f"turret did not fire on {n} rounds"))

    for uid, ever in acted_ever.items():
        if not ever:
            out.add(Finding("NEVER_ACTED", uid, team, (born.get(uid, 0), rep.total_turns),
                            "unit existed and never took a single action"))

    if ammo_starved:
        out.add(Finding("AMMO_STARVED", 0, team, (0, rep.total_turns),
                        f"owned a turret with an empty ammo pool on {ammo_starved} rounds"))

    if exec_us:
        exec_us.sort()
        out.stats["exec_us_p50"] = exec_us[len(exec_us) // 2]
        out.stats["exec_us_p99"] = exec_us[int(len(exec_us) * 0.99)]
        out.stats["exec_us_max"] = exec_us[-1]
        out.stats["tled"] = tled
    out.stats["idle_rounds"] = sum(idle_total.values())
    return out


def route_audit(path: str, team: str, slack: float = 1.6) -> list[Finding]:
    """Flag builders that took materially longer than the open path allowed.

    Measured between consecutive BUILD actions: the walk a unit actually spent versus the shortest
    cardinal path that existed when it set off. Terrain and buildings both change, so this is
    deliberately generous -- it reports only journeys that overran by `slack`x.
    """
    rep = Replay(open(path, "rb").read())
    out: list[Finding] = []
    leg_start: dict[int, tuple[int, tuple[int, int], object]] = {}
    for t, state, ta in rep.iter_states():
        for uid, target in ta.builds.items():
            e = state.entities.get(uid)
            if e is None or e.team != team:
                continue
            prev = leg_start.get(uid)
            if prev is not None:
                t0, p0, s0 = prev
                best = _bfs(rep, s0, p0, {target})
                took = t - t0
                if best is not None and best > 0 and took > best * slack:
                    out.append(Finding("ROUTE_EXCESS", uid, team, (t0, t),
                                       f"took {took} rounds for a {best}-round path "
                                       f"({took - best} wasted)"))
            leg_start[uid] = (t, (e.x, e.y), state.copy())
    return out
