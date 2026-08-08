"""Read the live feed the way it has to be read: per opponent *version*.

`live.json`'s `matchups` are rows of (our build, their version). Pooling them by
opponent name mixes builds the opponent retired days ago with the one it is
running now, and opponents re-upload constantly. On 2026-08-08 that error made
Besvikomat look like our worst matchup at 0.24 over 455 games, when against its
current v26 we were at 0.53 and the real problems were O(1) v11 and Pivot.

    uv run python tools/live_matchups.py                # current builds only
    uv run python tools/live_matchups.py --all-versions # show the pooled lie too
    uv run python tools/live_matchups.py --build gefjon # one of our builds
    uv run python tools/live_matchups.py --versions "O(1)"

Stdlib only, reads the published feed over HTTP, prints tables.
"""

from __future__ import annotations

import argparse
import collections
import json
import urllib.request

FEED = "https://lucasrgpedersen.com/botrankings/data/live.json"
# Below this many games a rate is not worth reading; five-game series swing hard
# enough that a single one can move a 20-game number by 0.25.
MIN_GAMES = 20


def load(url: str) -> dict:
    """Fetch the feed, or read it from disk when `url` is a path.

    The site sits behind Cloudflare, which refuses urllib's default agent, so
    this sends a plain browser one. A path is accepted too, for working off a
    snapshot without hammering the feed.
    """
    if not url.startswith(("http://", "https://")):
        with open(url) as handle:
            return json.load(handle)
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def our_builds(feed: dict) -> dict[str, str]:
    """key -> canonical name, for every build of ours the feed knows."""
    return {b["key"]: b["canonical"] for b in feed["bots"]
            if isinstance(b.get("canonical"), str)}


def by_opponent(feed: dict, keys: set[str] | None, current_only: bool):
    agg = collections.defaultdict(lambda: [0, 0])
    for row in feed["matchups"]:
        if keys is not None and row["key"] not in keys:
            continue
        if current_only and not row.get("opponent_build_current"):
            continue
        slot = agg[row["opponent"]]
        slot[0] += row["games_for"]
        slot[1] += row["games_for"] + row["games_against"]
    return agg


def print_opponents(feed: dict, keys: set[str] | None, show_pooled: bool) -> None:
    ranks = {o["team"]: o["rank"] for o in feed["opponents"] if o.get("team")}
    current = by_opponent(feed, keys, current_only=True)
    pooled = by_opponent(feed, keys, current_only=False)

    rows = []
    for opponent, (won, total) in current.items():
        if total < MIN_GAMES:
            continue
        pooled_won, pooled_total = pooled[opponent]
        rows.append((won / total, opponent, ranks.get(opponent, "-"), won, total,
                     pooled_won / pooled_total if pooled_total else float("nan"),
                     pooled_total))
    rows.sort()

    header = f"{'opponent':32s}{'rank':>5}{'vs CURRENT build':>21s}"
    if show_pooled:
        header += f"{'pooled (misleading)':>24s}"
    print(header)
    print("-" * len(header))
    for rate, opponent, rank, won, total, pooled_rate, pooled_total in rows:
        line = f"{opponent:32s}{str(rank):>5}   {won:4d}/{total:<5d} {rate:.2f}"
        if show_pooled:
            line += f"        {pooled_rate:.2f} over {pooled_total}"
        print(line)
    if not rows:
        print(f"(nothing with >= {MIN_GAMES} games against a current build)")


def print_versions(feed: dict, keys: set[str] | None, opponent: str) -> None:
    agg = collections.defaultdict(lambda: [0, 0])
    current = {}
    for row in feed["matchups"]:
        if row["opponent"] != opponent:
            continue
        if keys is not None and row["key"] not in keys:
            continue
        slot = agg[row["opponent_version"]]
        slot[0] += row["games_for"]
        slot[1] += row["games_for"] + row["games_against"]
        current[row["opponent_version"]] = row.get("opponent_build_current")
    print(f"our record against {opponent}, split by their version:")
    for version, (won, total) in sorted(agg.items()):
        if not total:
            continue
        mark = "  <-- current" if current.get(version) else ""
        print(f"   their v{version:<5} {won:4d}/{total:<5d} {won / total:.2f}{mark}")


def print_shrinkage(feed: dict) -> None:
    """Why a challenger's estimate is not comparable to the incumbent's."""
    team = feed["team"]["rating"]
    print(f"team rating {team:.0f} -- estimates shrink toward this, weighted by games")
    print(f"{'build':44s}{'games':>7}{'shrink':>8}{'elo':>7}{'raw':>7}")
    rows = []
    for bot in feed["bots"]:
        estimate = bot.get("estimate")
        if not estimate or not isinstance(bot.get("canonical"), str):
            continue
        rows.append((estimate.get("shrinkage", 0), bot["canonical"],
                     bot.get("live_games", 0), estimate["elo"],
                     estimate.get("elo_if_matchups_persist", estimate["elo"])))
    rows.sort()
    for shrink, name, games, elo, raw in rows:
        print(f"{name[:44]:44s}{games:7d}{shrink:8.2f}{elo:7.0f}{raw:7.0f}")
    print("\n`elo` is the shrunk estimate and `raw` is elo_if_matchups_persist.")
    print("Where they differ, the estimate is being pulled toward the team rating")
    print("and is not comparable across builds with very different game counts.")
    print("Do not assume a fixed shrinkage regime: on 2026-08-08 this column read")
    print("0.11 for a 333-game incumbent and 0.69 for a 10-game challenger in the")
    print("morning, and 1.00 for every build a few hours later. Read it, do not")
    print("rely on it -- the per-opponent table above needs no model at all.")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default=FEED)
    parser.add_argument("--build", default=None,
                        help="restrict to one of our builds, by name substring")
    parser.add_argument("--all-versions", action="store_true",
                        help="also show the pooled all-versions rate, for contrast")
    parser.add_argument("--versions", default=None, metavar="OPPONENT",
                        help="break one opponent out by their build version")
    parser.add_argument("--shrinkage", action="store_true",
                        help="show why challenger estimates are not comparable")
    args = parser.parse_args()

    feed = load(args.url)
    names = our_builds(feed)
    keys = None
    if args.build:
        keys = {k for k, name in names.items() if args.build in name}
        if not keys:
            raise SystemExit(f"no build of ours matches {args.build!r}")
        print(f"restricted to: {', '.join(sorted(names[k] for k in keys))}\n")

    if args.versions:
        print_versions(feed, keys, args.versions)
        return
    if args.shrinkage:
        print_shrinkage(feed)
        return
    print(f"feed generated {feed['generated_at']}   "
          f"team rank {feed['team']['rank']}/{feed['team']['ladder_size']} "
          f"rating {feed['team']['rating']:.0f}\n")
    print_opponents(feed, keys, show_pooled=args.all_versions)


if __name__ == "__main__":
    main()
