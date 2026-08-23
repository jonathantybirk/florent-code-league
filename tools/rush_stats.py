"""Summarize rush timing from a rush_analysis.json produced by analyze_rush.py."""

from __future__ import annotations

import argparse
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path


def describe(values: list) -> str:
    values = [v for v in values if v is not None]
    if not values:
        return "n=0"
    s = sorted(values)
    q = lambda f: s[min(len(s) - 1, int(f * len(s)))]  # noqa: E731
    sd = statistics.stdev(s) if len(s) > 1 else 0.0
    return (
        f"n={len(s):3d}  mean={statistics.mean(s):6.1f}  sd={sd:5.1f}  "
        f"min={s[0]:4} p25={q(.25):4} med={statistics.median(s):6.1f} "
        f"p75={q(.75):4} p90={q(.90):4} max={s[-1]:4}"
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("report", type=Path)
    ap.add_argument("--opponent-view", action="store_true",
                    help="also summarize the opponents in the same games")
    args = ap.parse_args()

    report = json.loads(args.report.read_text())
    games = report["games"]
    name = report.get("team_name") or report["team_id"]

    subj, opp = [], []
    for g in games:
        side = g["subject_side"]
        subj.append((g, g["teams"][side]))
        opp.append((g, g["teams"][1 - side]))

    print(f"=== {name}: {len(games)} games from {report['matches']} ladder matches ===\n")

    # Coverage / sanity
    no_turret = [g for g, t in subj if t["first_damage_turret"] is None]
    print(f"games with no damage turret at all: {len(no_turret)}")
    sizes = Counter("{}x{}".format(g["width"], g["height"]) for g, _ in subj)
    print("map sizes:", sizes.most_common())
    print()

    metrics = [
        ("first bot past 25% of the way", "first_bot_leaves_home"),
        ("first bot crosses midfield", "first_bot_enemy_half"),
        ("FIRST DAMAGE TURRET (rush start)", "first_damage_turret"),
        ("first turret in enemy half", "first_forward_turret"),
        ("first turret within 5 of enemy core", "first_turret_near_enemy_core"),
        ("first enemy building destroyed", "first_kill"),
        ("game length (turns)", None),
    ]
    for label, key in metrics:
        vals = [g["turns"] if key is None else t[key] for g, t in subj]
        print(f"{label:38s} {describe(vals)}")
    print()

    if args.opponent_view:
        print("--- opponents in the same games ---")
        for label, key in metrics:
            vals = [g["turns"] if key is None else t[key] for g, t in opp]
            print(f"{label:38s} {describe(vals)}")
        print()

    # Prep phase: what exists when the rush turret goes down
    print("--- state at the moment the first damage turret is placed ---")
    counts = Counter()
    eco = 0
    for _, t in subj:
        st = t["state_at_rush"]
        if not st:
            continue
        for k, v in st["counts"].items():
            counts[k] += v
        if st["counts"].get("harvester") or st["counts"].get("conveyor"):
            eco += 1
    n = len([1 for _, t in subj if t["state_at_rush"]])
    print(f"avg entities owned at rush: " +
          ", ".join(f"{k}={v / n:.2f}" for k, v in counts.most_common()))
    print(f"games with any harvester/conveyor built before the rush: {eco}/{n}")
    print(f"titanium banked at rush: {describe([t['state_at_rush']['titanium'] for _, t in subj if t['state_at_rush']])}")
    print(f"placement frac (0=own core, 1=enemy core): "
          f"{describe([t['state_at_rush']['frac'] for _, t in subj if t['state_at_rush']])}")
    print(f"distance to enemy core at rush: "
          f"{describe([t['state_at_rush']['enemy_core_dist'] for _, t in subj if t['state_at_rush']])}")
    print()

    # First turret kind
    print("--- opening turret kind ---")
    kinds = Counter()
    for _, t in subj:
        builds = t["turret_builds"]
        if builds:
            kinds[builds[0][1]] += 1
    print(dict(kinds))
    print(f"turrets built per game: {describe([len(t['turret_builds']) for _, t in subj])}")
    print()

    # Rush timing vs map size / core separation
    print("--- rush start by core separation ---")
    buckets = defaultdict(list)
    for g, t in subj:
        sep = g["core_separation"]
        if sep is None or t["first_damage_turret"] is None:
            continue
        b = "<=15" if sep <= 15 else "16-25" if sep <= 25 else ">25"
        buckets[b].append(t["first_damage_turret"])
    for b in ("<=15", "16-25", ">25"):
        if buckets[b]:
            print(f"  sep {b:6s} {describe(buckets[b])}")
    print()

    # Win rate vs rush timing
    print("--- outcome ---")
    wins = sum(1 for g, _ in subj if g["replay_winner"] == g["subject_side"])
    print(f"record: {wins}W {len(subj) - wins}L  ({wins / len(subj):.0%})")
    print(f"win conditions: {Counter(g['replay_win_condition'] for g, _ in subj).most_common()}")
    early = [t["first_damage_turret"] for g, t in subj
             if g["replay_winner"] == g["subject_side"] and t["first_damage_turret"] is not None]
    late = [t["first_damage_turret"] for g, t in subj
            if g["replay_winner"] != g["subject_side"] and t["first_damage_turret"] is not None]
    print(f"  rush turn in wins:   {describe(early)}")
    print(f"  rush turn in losses: {describe(late)}")
    print()

    print("--- per-opponent rush start (median) ---")
    per = defaultdict(list)
    for g, t in subj:
        if t["first_damage_turret"] is not None:
            per[g["opponent"]].append(t["first_damage_turret"])
    for opponent, vals in sorted(per.items(), key=lambda kv: statistics.median(kv[1])):
        print(f"  {opponent:16s} n={len(vals):3d} median={statistics.median(vals):6.1f} "
              f"range={min(vals)}-{max(vals)}")


if __name__ == "__main__":
    main()
