"""Turn the scraped league match log into a central overview and a per-team activity history.

    uv run python tools/league_census/overview.py            # printed summary
    uv run python tools/league_census/overview.py --json out.json

Two things come out of it:

- **Central overview** -- every team the log has ever seen: current rating and rank, peak rating,
  win rate, how many distinct submission versions it shipped, and the span of its activity.
  Matches played is deliberately *not* the organising metric: the platform pairs teams on its own
  schedule, so a big number mostly means the bot sat on the ladder, not that anyone was working.
- **Activity through time** -- per team, per day: versions first seen, matches, and the rating
  trajectory sampled in six-hour buckets. A team that stopped uploading but kept getting paired is
  a different animal from one that went quiet, and only the version series separates them.
- **Per-team detail** -- rating history, version cadence, and the opponents it actually met.

Who ordered an unrated match is recoverable from two independent signals, and needs both:

- **Batch bursts.** Ordering a test fires several matches at once: a team runs its new build
  against five opponents and five rows appear with `createdAt` inside the same few seconds. Group
  unrated matches by creation gap, and where one team is in *every* match of a burst, that team
  ordered it. This is what catches a farm on a fixed cadence -- five matches every ten minutes,
  all sharing one team.
- **Replay links.** About a fifth of unrated matches carry a `sourceMatch{A,B}Id` pointing at an
  earlier *ladder* match of the team on that same side. That side is the one being replayed, so
  the other side ordered it. This catches one-off replays that never appear in a burst.

Neither alone is enough, and getting it wrong is not subtle: the replay signal on its own ranks
Torsko first and misses the heaviest batch orderer in the league entirely. Where both signals
speak they agree on 98.7% of matches, which is the reason to trust either. Bursts of one match
with no replay link stay unattributed.

Version numbers come from the match rows themselves (`teamAVersion`/`teamBVersion`), which is the
only league-wide source: `/api/submissions` is scoped to the authenticated team.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent


def attribute_sparring(path: Path, gap_seconds: float = 5.0) -> dict[str, str]:
    """match id -> team id that ordered it, for unrated matches we can attribute.

    See the module docstring for why this needs both signals. The burst pass groups *per team*
    rather than globally: on a busy day unrelated matches land within seconds of each other, and
    a global grouping chains them into one blob with no common team, silently dropping the
    attribution exactly when the ladder is most active. Grouping per team is immune to that.
    """
    per_team: dict[str, list[tuple[float, str]]] = defaultdict(list)
    replay: dict[str, str] = {}
    for m in load_matches(path):
        if m.get("status") != "complete" or m.get("triggeredBy") == "ladder":
            continue
        created, a_id, b_id = m.get("createdAt"), m.get("teamAId"), m.get("teamBId")
        if not (created and a_id and b_id):
            continue
        when = _seconds(created)
        per_team[a_id].append((when, m["id"]))
        per_team[b_id].append((when, m["id"]))
        src_a, src_b = m.get("sourceMatchAId"), m.get("sourceMatchBId")
        if bool(src_a) != bool(src_b):
            # the side carrying the link is the one being replayed; the other side ordered it
            replay[m["id"]] = b_id if src_a else a_id

    # A team in two or more unrated matches created within `gap_seconds` fired a batch.
    claims: dict[str, list[tuple[str, int]]] = defaultdict(list)
    for team_id, entries in per_team.items():
        entries.sort()
        group = [entries[0]]
        for entry in entries[1:]:
            if entry[0] - group[-1][0] <= gap_seconds:
                group.append(entry)
            else:
                _claim(claims, team_id, group)
                group = [entry]
        _claim(claims, team_id, group)

    out: dict[str, str] = {}
    for match_id, candidates in claims.items():
        if len(candidates) == 1:
            out[match_id] = candidates[0][0]
            continue
        # Both sides batching at once: the bigger batch is the one that scheduled this match.
        candidates.sort(key=lambda c: -c[1])
        if candidates[0][1] > candidates[1][1]:
            out[match_id] = candidates[0][0]

    for match_id, boss in replay.items():
        out.setdefault(match_id, boss)
    return out


def _claim(claims: dict, team_id: str, group: list[tuple[float, str]]) -> None:
    if len(group) < 2:
        return
    for _, match_id in group:
        claims[match_id].append((team_id, len(group)))


def _seconds(stamp: str) -> float:
    return datetime.fromisoformat(stamp.replace("Z", "+00:00")).timestamp()


def load_matches(path: Path):
    with open(path) as handle:
        for line in handle:
            line = line.strip()
            if line:
                yield json.loads(line)


def build(matches_path: Path, ladder_path: Path) -> dict:
    ordered_by = attribute_sparring(matches_path)
    ladder = json.load(open(ladder_path)) if ladder_path.exists() else []
    rank_of = {t["teamId"]: i + 1 for i, t in enumerate(ladder)}
    rating_of = {t["teamId"]: t["rating"] for t in ladder}
    meta_of = {t["teamId"]: t for t in ladder}

    stats: dict[str, dict] = defaultdict(lambda: {
        "name": None, "matches": 0, "rated": 0, "wins": 0, "losses": 0, "draws": 0,
        "versions": set(), "first": None, "last": None,
    })
    per_day: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    version_first_seen: dict[str, dict[int, str]] = defaultdict(dict)
    # Rating is sampled into six-hour buckets: the ladder moves a team dozens of times a day and
    # the shape is what matters, not every step. `ratingXBefore` is the live rating at that match
    # (unrated matches carry it unchanged), where `teamXRating` is a snapshot of *now* on every row.
    rating_bucket: dict[str, dict[str, tuple[str, float]]] = defaultdict(dict)
    version_by_day: dict[str, dict[str, int]] = defaultdict(dict)
    opponents: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(lambda: [0, 0, 0]))
    # Sparring attribution, hard evidence only (see the module docstring).
    ordered: dict[str, int] = defaultdict(int)
    replayed: dict[str, int] = defaultdict(int)
    ordered_by_day: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    ordered_targets: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    league_ordered: dict[str, int] = defaultdict(int)
    unrated_total = 0
    unrated_attributed = 0
    total = 0

    for m in load_matches(matches_path):
        if m.get("status") != "complete":
            continue
        stamp = m.get("completedAt") or m.get("createdAt")
        if not stamp:
            continue
        total += 1
        day = stamp[:10]
        winner = m.get("winnerId")

        if m.get("triggeredBy") != "ladder":
            unrated_total += 1
            bid = ordered_by.get(m["id"])
            if bid:
                unrated_attributed += 1
                league_ordered[day] += 1
                victim = "B" if bid == m.get("teamAId") else "A"
                vid = m.get(f"team{victim}Id")
                vname = m.get(f"team{victim}Name") or vid
                ordered[bid] += 1
                ordered_by_day[bid][day] += 1
                if vname:
                    ordered_targets[bid][vname] += 1
                if vid:
                    replayed[vid] += 1
        for side in ("A", "B"):
            tid = m.get(f"team{side}Id")
            if not tid:
                continue
            row = stats[tid]
            row["name"] = m.get(f"team{side}Name") or row["name"]
            row["matches"] += 1
            if m.get("rated") is not False and m.get("triggeredBy") != "unrated":
                row["rated"] += 1
            if winner is None:
                row["draws"] += 1
            elif winner == tid:
                row["wins"] += 1
            else:
                row["losses"] += 1
            ver = m.get(f"team{side}Version")
            if isinstance(ver, int):
                row["versions"].add(ver)
                seen = version_first_seen[tid]
                if ver not in seen or stamp < seen[ver]:
                    seen[ver] = stamp
            if row["first"] is None or stamp < row["first"]:
                row["first"] = stamp
            if row["last"] is None or stamp > row["last"]:
                row["last"] = stamp
            per_day[tid][day] += 1

            rating = m.get(f"rating{side}Before")
            if isinstance(rating, (int, float)):
                bucket = f"{day}T{(int(stamp[11:13]) // 6) * 6:02d}"
                prior = rating_bucket[tid].get(bucket)
                if prior is None or stamp > prior[0]:
                    rating_bucket[tid][bucket] = (stamp, float(rating))
            if isinstance(ver, int):
                version_by_day[tid][day] = max(version_by_day[tid].get(day, 0), ver)

            other = "B" if side == "A" else "A"
            opponent = m.get(f"team{other}Name") or m.get(f"team{other}Id")
            if opponent:
                slot = opponents[tid][opponent]
                slot[2] += 1
                if winner == tid:
                    slot[0] += 1
                elif winner is not None:
                    slot[1] += 1

    teams = []
    for tid, row in stats.items():
        versions = sorted(row["versions"])
        meta = meta_of.get(tid, {})
        decided = row["wins"] + row["losses"]
        uploads_by_day: dict[str, int] = defaultdict(int)
        for ver, stamp in version_first_seen[tid].items():
            uploads_by_day[stamp[:10]] += 1
        track = [(b, v) for b, (_, v) in sorted(rating_bucket[tid].items())]
        ratings = [v for _, v in track]
        opp = sorted(opponents[tid].items(), key=lambda kv: -kv[1][2])
        teams.append({
            "team_id": tid,
            "name": row["name"] or meta.get("teamName"),
            "rank": rank_of.get(tid),
            "rating": rating_of.get(tid),
            "region": meta.get("region"),
            "student": meta.get("studentStatus"),
            "members": [mem.get("name") for mem in meta.get("members", []) or []],
            "on_ladder": tid in rank_of,
            "matches": row["matches"],
            "rated_matches": row["rated"],
            "wins": row["wins"],
            "losses": row["losses"],
            "draws": row["draws"],
            "win_rate": (row["wins"] / decided) if decided else None,
            "rating_now": ratings[-1] if ratings else None,
            "rating_peak": max(ratings) if ratings else None,
            "rating_low": min(ratings) if ratings else None,
            "rating_start": ratings[0] if ratings else None,
            "rating_track": [[b, round(v, 1)] for b, v in track],
            "sparring_ordered": ordered.get(tid, 0),
            "sparring_replayed": replayed.get(tid, 0),
            "ordered_by_day": dict(sorted(ordered_by_day[tid].items())),
            "ordered_targets": [
                {"name": n, "games": g}
                for n, g in sorted(ordered_targets[tid].items(), key=lambda kv: -kv[1])[:10]
            ],
            "versions_seen": len(versions),
            "version_min": versions[0] if versions else None,
            "version_max": versions[-1] if versions else None,
            "first_match": row["first"],
            "last_match": row["last"],
            "active_days": len(per_day[tid]),
            "matches_by_day": dict(sorted(per_day[tid].items())),
            "new_versions_by_day": dict(sorted(uploads_by_day.items())),
            "version_by_day": dict(sorted(version_by_day[tid].items())),
            "opponents": [
                {"name": name, "wins": w, "losses": l, "games": g}
                for name, (w, l, g) in opp
            ],
        })
    teams.sort(key=lambda t: (t["rank"] is None, t["rank"] or 0, -(t["rating_now"] or 0)))

    all_days = sorted({d for t in teams for d in t["matches_by_day"]})
    league_by_day = {
        d: {
            "matches": sum(t["matches_by_day"].get(d, 0) for t in teams) // 2,
            "teams_playing": sum(1 for t in teams if t["matches_by_day"].get(d)),
            "new_versions": sum(t["new_versions_by_day"].get(d, 0) for t in teams),
            "teams_shipping": sum(1 for t in teams if t["new_versions_by_day"].get(d)),
            "sparring_ordered": league_ordered.get(d, 0),
        }
        for d in all_days
    }
    return {
        "matches_total": total,
        "teams_total": len(teams),
        "unrated_total": unrated_total,
        "unrated_attributed": unrated_attributed,
        "days": all_days,
        "league_by_day": league_by_day,
        "teams": teams,
    }


def _bar(value: int, peak: int, width: int = 24) -> str:
    if peak <= 0:
        return ""
    filled = max(1, round(value / peak * width)) if value else 0
    return "#" * filled


def report(data: dict, top: int) -> None:
    versions = sum(t["versions_seen"] for t in data["teams"])
    print(f"League census: {versions} submission versions from {data['teams_total']} teams, "
          f"{data['days'][0]} .. {data['days'][-1]}")
    print(f"  {data['unrated_attributed']} of {data['unrated_total']} unrated matches "
          f"attributable to whoever ordered them\n")

    print("Per day")
    peak = max(v["new_versions"] for v in data["league_by_day"].values())
    print(f"  {'day':<12}{'uploads':>9}{'shipping':>10}{'sparring':>10}  ")
    for day, v in data["league_by_day"].items():
        print(f"  {day:<12}{v['new_versions']:>9}{v['teams_shipping']:>10}"
              f"{v['sparring_ordered']:>10}  {_bar(v['new_versions'], peak)}")

    print(f"\nTeams (top {top} by ladder rank)")
    header = (f"  {'rank':>5} {'team':<30}{'rating':>8}{'peak':>8}{'win%':>7}"
              f"{'vers':>6}{'v/day':>7}{'ship':>6}{'spar':>7}  first .. last")
    print(header)
    for t in data["teams"][:top]:
        rank = t["rank"] if t["rank"] else "-"
        rating = f"{t['rating']:.0f}" if t["rating"] is not None else "-"
        peak = f"{t['rating_peak']:.0f}" if t["rating_peak"] is not None else "-"
        win = f"{t['win_rate'] * 100:.1f}" if t["win_rate"] is not None else "-"
        name = (t["name"] or t["team_id"])[:30]
        ship = len(t["new_versions_by_day"])
        rate = t["versions_seen"] / max(t["active_days"], 1)
        print(f"  {str(rank):>5} {name:<30}{rating:>8}{peak:>8}{win:>7}"
              f"{t['versions_seen']:>6}{rate:>7.1f}{ship:>6}{t['sparring_ordered']:>7}  "
              f"{t['first_match'][:10]} .. {t['last_match'][:10]}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--matches", type=Path, default=HERE / "matches.jsonl")
    parser.add_argument("--ladder", type=Path, default=HERE / "ladder.json")
    parser.add_argument("--json", type=Path, default=HERE / "census.json")
    parser.add_argument("--top", type=int, default=40)
    args = parser.parse_args()

    data = build(args.matches, args.ladder)
    if args.json:
        args.json.write_text(json.dumps(data, indent=1))
    report(data, args.top)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
