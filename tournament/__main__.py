"""Tournament CLI.

    uv run python -m tournament discover --ref x/jon --prefix bots/jon
    uv run python -m tournament plan --tid smoke --bots vanguard,undertow --maps screen
    uv run python -m tournament run  --tid smoke --jobs 8
    uv run python -m tournament rate --tid smoke

    uv run python -m tournament hpc push   --tid smoke --bootstrap
    uv run python -m tournament hpc submit --tid smoke
    uv run python -m tournament hpc watch  --tid smoke
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from tournament import plan as planning
from tournament import registry


def _add_tid(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--tid", required=True, help="tournament id (names the run directory)")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="tournament", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    discover = sub.add_parser("discover", help="scan a git ref for bots and write bots.toml")
    discover.add_argument("--ref", default="x/jon", help="branch, tag or commit to scan")
    discover.add_argument("--prefix", default="bots", help="path prefix to scan under")
    discover.add_argument("--name-depth", type=int, default=1)
    discover.add_argument("--out", type=Path, default=registry.REGISTRY_PATH)
    discover.add_argument(
        "--append", action="store_true", help="keep existing entries and add to them"
    )

    listing = sub.add_parser("bots", help="show the registry")

    planner = sub.add_parser("plan", help="stage bots and build a schedule")
    _add_tid(planner)
    planner.add_argument("--bots", default=None, help="comma list of bot_ids, names, or tag:<tag>")
    planner.add_argument(
        "--vs",
        default=None,
        help=(
            "challenger mode: --bots play everyone listed here, plus each other, instead of a "
            "full round robin. Use to add new bot versions without re-running unchanged pairings"
        ),
    )
    planner.add_argument(
        "--dedupe-from",
        default=None,
        help=(
            "comma list of finished tournament ids. Bots already shown to play identically are "
            "pruned to one representative, so a challenger is not run against four copies of the "
            "same bot for four times the compute"
        ),
    )
    planner.add_argument(
        "--maps",
        default="official",
        help="official | generated | secret | official_secret | all | screen | comma list",
    )
    planner.add_argument("--seeds", default="1", help="comma list of engine seeds")
    planner.add_argument(
        "--tle",
        type=int,
        default=0,
        help="rating-match per-turn ms limit; keep 0 (compliance probes are configured separately)",
    )
    planner.add_argument(
        "--compliance-only",
        action="store_true",
        help="stage only the short timing probes; do not schedule rating matches",
    )

    runner = sub.add_parser("run", help="play outstanding matches locally")
    _add_tid(runner)
    runner.add_argument("--jobs", type=int, default=0, help="worker processes (default: min(cpu,8))")
    runner.add_argument("--limit", type=int, default=0, help="stop after N matches")
    runner.add_argument("--force", action="store_true", help="replay matches that already have results")

    merger = sub.add_parser("merge", help="fold result JSONs into matches.csv")
    _add_tid(merger)

    checker = sub.add_parser("compliance", help="show the persistent 10 ms timing checks")
    _add_tid(checker)

    rater = sub.add_parser("rate", help="compute mElo + Nash ratings and print the table")
    _add_tid(rater)
    rater.add_argument("--k", type=int, default=1, help="mElo_2k half-rank (paper uses k=1)")
    rater.add_argument("--matrix", action="store_true", help="also print the win-rate cross table")
    rater.add_argument(
        "--pool",
        default=None,
        help=(
            "comma list of other tournament ids whose matches.csv to fold in. Ratings need one "
            "win matrix, so pool a challenger run with the round robin it extends"
        ),
    )

    dupes = sub.add_parser(
        "duplicates", help="find bots that are the same player under two names"
    )
    _add_tid(dupes)
    dupes.add_argument(
        "--tolerance",
        type=float,
        default=0.0,
        help="largest win-rate gap still counted as identical (0 = exact twins, 0.05 = near)",
    )
    dupes.add_argument("--pool", default=None, help="comma list of other tournament ids to fold in")
    dupes.add_argument(
        "--no-code", action="store_true", help="skip the git .py hash check (behaviour only)"
    )

    hpc = sub.add_parser("hpc", help="run the tournament on DTU HPC")
    hpc_sub = hpc.add_subparsers(dest="hpc_command", required=True)
    for name, helptext in [
        ("push", "upload package + run directory"),
        ("submit", "submit the LSF job array"),
        ("status", "array progress"),
        ("fetch", "pull results down and merge"),
        ("watch", "fetch on a loop until done"),
        ("logs", "tail recent error logs"),
        ("cancel", "bkill every array for this tournament"),
    ]:
        command = hpc_sub.add_parser(name, help=helptext)
        _add_tid(command)
        if name == "push":
            command.add_argument("--bootstrap", action="store_true", help="create the remote venv")
        if name == "submit":
            command.add_argument(
                "--all",
                dest="include_done",
                action="store_true",
                help=(
                    "re-submit every match, including those that already have a result. "
                    "By default finished matches are skipped"
                ),
            )
            command.add_argument(
                "--chunk",
                type=int,
                default=None,
                help=(
                    "matches per array element (default: the `chunk` value in hpc.toml, 20). "
                    "A match is ~1.3s but each element costs ~4s of startup, so batching is far "
                    "more efficient; use --chunk 1 for one individually retryable job per match"
                ),
            )
        if name == "watch":
            command.add_argument("--interval", type=int, default=60)
        if name == "logs":
            command.add_argument("--lines", type=int, default=40)

    return parser


def cmd_discover(args) -> int:
    from tournament.discover import discover

    specs = discover(args.ref, args.prefix, name_depth=args.name_depth)
    if args.append and args.out.exists():
        existing = registry.load(args.out, validate=False)
        known = {(s.name, s.commit) for s in existing}
        specs = existing + [s for s in specs if (s.name, s.commit) not in known]

    registry.dump(
        specs,
        args.out,
        header=(
            "Tournament roster. Each bot is pinned by name AND commit; ratings are only\n"
            f"meaningful if the code behind a name cannot drift.\n"
            f"Generated by: python -m tournament discover --ref {args.ref} --prefix {args.prefix}\n"
            "Edit freely -- commits may be short, they re-resolve on load."
        ),
    )
    print(f"wrote {len(specs)} bots to {args.out}")
    for spec in specs:
        print(f"  {spec.bot_id:<28} {spec.path}")
    return 0


def cmd_bots(args) -> int:
    specs = registry.load()
    print(f"{len(specs)} bots")
    for spec in specs:
        tags = ",".join(spec.tags)
        print(f"  {spec.bot_id:<28} {spec.path:<40} {tags}")
    return 0


def _known_duplicates(tids: str):
    """Behaviour groups from finished tournaments, plus code-identical groups from git."""
    from tournament import duplicates
    from tournament.merge import read

    rows: list[dict] = []
    seen: set[str] = set()
    for tid in (part.strip() for part in tids.split(",")):
        if not tid:
            continue
        for row in read(planning.run_dir(tid)):
            if row["match_id"] not in seen:
                seen.add(row["match_id"])
                rows.append(row)
    return duplicates.behaviour_groups(rows) if rows else []


def cmd_plan(args) -> int:
    from tournament import duplicates

    roster = registry.load()
    specs = registry.select(roster, args.bots)
    compliance_specs = list(specs)
    if args.compliance_only and args.vs:
        raise ValueError("--compliance-only cannot be combined with --vs")
    versus = registry.select(roster, args.vs) if args.vs else None
    seeds = tuple(int(part) for part in args.seeds.split(",") if part.strip())

    if args.dedupe_from:
        groups = _known_duplicates(args.dedupe_from) + duplicates.code_groups(roster)
        target = versus if versus is not None else specs
        # Never prune a bot the user explicitly entered as a challenger -- comparing a new version
        # against its own predecessor is usually the entire point of the run.
        protected = {s.bot_id for s in specs} if versus is not None else set()
        keep = [s for s in target if s.bot_id not in protected]
        pruned, dropped = duplicates.prune(keep, groups)
        pruned += [s for s in target if s.bot_id in protected]
        if dropped:
            print(f"pruned {len(dropped)} duplicate bot(s) from the field:")
            for gone, kept in dropped:
                print(f"  {gone:<28} -> covered by {kept}")
        if versus is not None:
            versus = pruned
        else:
            specs = pruned

    rating_specs = [] if args.compliance_only else specs
    destination, matches = planning.plan(
        args.tid,
        rating_specs,
        args.maps,
        seeds,
        args.tle,
        versus=versus,
        compliance_specs=compliance_specs,
    )
    rating_matches = [match for match in matches if match.kind == "rating"]
    compliance_matches = [match for match in matches if match.kind == "compliance"]
    pairs = len(planning.pairings(rating_specs, versus))
    if args.compliance_only:
        print(f"{args.tid}: compliance only -> 0 rating matches")
    elif versus:
        print(
            f"{args.tid}: {len(specs)} challengers vs {len(versus)} roster bots, "
            f"{pairs} pairs, {len(rating_matches) // max(pairs, 1)} games per pair "
            f"-> {len(rating_matches)} rating matches"
        )
    else:
        print(
            f"{args.tid}: {len(specs)} bots, {pairs} pairs, "
            f"{len(rating_matches) // max(pairs, 1)} games per pair "
            f"-> {len(rating_matches)} rating matches"
        )
    print(
        f"  + {len(compliance_matches)} compliance matches "
        f"for {len(compliance_specs)} named bot(s)"
    )
    print(f"  staged at {destination}")
    return 0


def cmd_run(args) -> int:
    from tournament.local import run_all
    from tournament.merge import merge

    destination = planning.run_dir(args.tid)
    run_all(destination, jobs=args.jobs, force=args.force, limit=args.limit)
    path, rows = merge(destination)
    print(f"{rows} results -> {path}")
    return 0


def cmd_merge(args) -> int:
    from tournament.merge import merge

    path, rows = merge(planning.run_dir(args.tid))
    print(f"{rows} results -> {path}")
    return 0


def cmd_compliance(args) -> int:
    from tournament import compliance
    from tournament.merge import merge

    destination = planning.run_dir(args.tid)
    merge(destination)
    rows = compliance.read_summary(destination)
    print(compliance.render(rows))
    print(f"\nwrote {destination / 'compliance.csv'}")
    return 0


def _pooled(tid: str, pool: str | None) -> tuple[list[dict], dict[str, dict]]:
    """Rows and bot metadata for a tournament plus any pooled ones, deduplicated by match_id."""
    from tournament.merge import read

    destination = planning.run_dir(tid)
    rows = read(destination)
    meta = {bot["bot_id"]: bot for bot in planning.load_manifest(destination)["bots"]}
    for other in (part.strip() for part in (pool or "").split(",")):
        if not other:
            continue
        other_dir = planning.run_dir(other)
        # match_id already covers (bots, map, seed, tle), so pooling cannot double-count.
        known = {row["match_id"] for row in rows}
        added = [row for row in read(other_dir) if row["match_id"] not in known]
        rows.extend(added)
        meta.update({bot["bot_id"]: bot for bot in planning.load_manifest(other_dir)["bots"]})
        print(f"pooled {len(added)} matches from {other}")
    return rows, meta


def cmd_duplicates(args) -> int:
    from tournament import duplicates
    from tournament.registry import BotSpec

    rows, meta = _pooled(args.tid, args.pool)
    specs = None
    if not args.no_code:
        specs = [
            BotSpec(name=b["name"], commit=b["commit"], path=b["path"]) for b in meta.values()
        ]
    groups = duplicates.detect(rows, specs, tolerance=args.tolerance)
    print(duplicates.render(groups))

    output = planning.run_dir(args.tid) / "duplicates.csv"
    duplicates.write_csv(groups, output)
    print(f"\nwrote {output}")
    return 0


def cmd_rate(args) -> int:
    # Imported here, not at module scope: this is the only path that pulls in numpy/scipy, and
    # `run` must never do so. See tournament/run_match.py.
    from tournament import duplicates, report
    from tournament.rating import evaluate

    destination = planning.run_dir(args.tid)
    rows, meta = _pooled(args.tid, args.pool)

    dropped = sum(1 for row in rows if row.get("status") != "ok")
    if len(rows) - dropped < 1:
        print("no successful matches to rate", file=sys.stderr)
        return 1

    ratings = evaluate(rows, k=args.k)
    output = destination / "ratings.csv"
    records = report.write_csv(ratings, meta, output)
    print(report.render(ratings, records, dropped))

    # Always run behaviour-level duplicate detection: a duplicate is the single most common way
    # for this table to be misleading, and an exact tie in melo_r is otherwise unexplained.
    groups = duplicates.behaviour_groups(rows)
    if groups:
        print()
        print(duplicates.render(groups))
        duplicates.write_csv(groups, destination / "duplicates.csv")

    print(f"\nwrote {output}")

    from tournament import compliance

    compliance_rows = compliance.read_summary(destination)
    if compliance_rows:
        print("\n10 ms timing compliance (9 ms = close):")
        print(compliance.render(compliance_rows))

    if args.matrix:
        print()
        width = max(len(bot) for bot in ratings.bots) + 1
        print(" " * width + "".join(f"{bot.split('@')[0][:7]:>8}" for bot in ratings.bots))
        for i, bot in enumerate(ratings.bots):
            cells = "".join(
                "       ." if i == j else f"{100 * ratings.win_prob[i, j]:>7.1f}%"
                for j in range(len(ratings.bots))
            )
            print(f"{bot:<{width}}{cells}")
    return 0


def cmd_hpc(args) -> int:
    from tournament import hpc

    settings = hpc.config()
    if args.hpc_command == "push":
        hpc.push(args.tid, settings, bootstrap=args.bootstrap)
    elif args.hpc_command == "submit":
        hpc.submit(args.tid, settings, chunk=args.chunk, include_done=args.include_done)
    elif args.hpc_command == "cancel":
        hpc.cancel(args.tid, settings)
    elif args.hpc_command == "status":
        hpc.status(args.tid, settings)
    elif args.hpc_command == "fetch":
        hpc.fetch(args.tid, settings)
    elif args.hpc_command == "watch":
        hpc.watch(args.tid, settings, interval=args.interval)
    elif args.hpc_command == "logs":
        hpc.logs(args.tid, settings, lines=args.lines)
    return 0


HANDLERS = {
    "discover": cmd_discover,
    "bots": cmd_bots,
    "plan": cmd_plan,
    "run": cmd_run,
    "merge": cmd_merge,
    "compliance": cmd_compliance,
    "rate": cmd_rate,
    "duplicates": cmd_duplicates,
    "hpc": cmd_hpc,
}


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return HANDLERS[args.command](args)
    except (registry.RegistryError, FileNotFoundError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    except Exception as error:  # noqa: BLE001
        from tournament.hpc import HpcError

        if isinstance(error, HpcError):
            print(f"error: {error}", file=sys.stderr)
            return 1
        raise


if __name__ == "__main__":
    raise SystemExit(main())
