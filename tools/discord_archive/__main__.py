"""Command line for the Discord archive.

    uv run python -m tools.discord_archive ingest
    uv run python -m tools.discord_archive extract
    uv run python -m tools.discord_archive publish
    uv run python -m tools.discord_archive poll        # all three, in order
    uv run python -m tools.discord_archive query --preset game --since 2026-07-01
    uv run python -m tools.discord_archive stats

`poll` is what the timer runs. Each stage is a no-op when its input has not
moved: nothing new in the drop directory means no ingest, no messages past the
watermark means no API call, and an unchanged feed means no bytes written and
nothing to deploy.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import db, extract, filters, ingest, publish, query

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DROP = REPO_ROOT / "discord" / "exports"
DEFAULT_ARCHIVE = REPO_ROOT / "discord" / "archive.sqlite3"
DEFAULT_SITE = REPO_ROOT.parent / "portfolio"
DEFAULT_FEED = DEFAULT_SITE / "public" / "discord" / "data" / "feed.json"


def _connect(args):
    return db.connect(args.archive)


def cmd_ingest(args) -> int:
    conn = _connect(args)
    results = ingest.ingest_dir(conn, args.drop, force=args.force)
    if not results:
        print(f"no .json exports under {args.drop}")
        return 0

    inserted = updated = 0
    for result in results:
        inserted += result["inserted"]
        updated += result["updated"]
        if args.verbose or result["status"] != "skipped (unchanged)":
            name = Path(result["path"]).name
            print(
                f"{name}: {result['status']}"
                f" (+{result['inserted']} new, ~{result['updated']} edited,"
                f" ={result['same']} unchanged)"
            )
    print(f"ingested {len(results)} file(s): {inserted} new, {updated} edited")
    return 0


def cmd_extract(args) -> int:
    conn = _connect(args)
    pending = extract.channels_with_backlog(conn)
    if not pending:
        print("nothing new to extract")
        return 0

    summaries = extract.extract_all(
        conn,
        batch=args.batch,
        context=args.context,
        effort=args.effort,
        dry_run=args.dry_run,
    )
    for summary in summaries:
        if args.dry_run:
            print(f"#{summary['channel']}: would send {summary['messages']} message(s)")
            if args.verbose and "prompt_preview" in summary:
                print("--- prompt preview ---")
                print(summary["prompt_preview"])
        else:
            print(
                f"#{summary['channel']}: {summary['messages']} message(s)"
                f" in {summary['batches']} batch(es)"
                f" -> {summary['threads']} thread(s)"
            )
    return 0


def cmd_publish(args) -> int:
    conn = _connect(args)
    bundle = publish.build(conn, limit=args.limit, max_messages=args.max_messages)
    changed = publish.write(bundle, args.feed)
    threads = bundle["counts"]["threads"]
    print(f"{'wrote' if changed else 'unchanged'} {args.feed} ({threads} thread(s))")

    if args.deploy and changed:
        shipped = publish.deploy(args.site_repo, args.feed)
        print("deployed" if shipped else "nothing to deploy")
    return 0


def cmd_poll(args) -> int:
    for step in (cmd_ingest, cmd_extract, cmd_publish):
        code = step(args)
        if code:
            return code
    return 0


def cmd_query(args) -> int:
    conn = _connect(args)
    rows = query.search(
        conn,
        preset=args.preset,
        contains=args.contains,
        regex=args.regex,
        channel=args.channel,
        author=args.author,
        since=args.since,
        until=args.until,
        pinned=args.pinned,
        include_bots=not args.no_bots,
        limit=args.limit,
    )
    if not rows:
        print("no matches")
        return 0
    print(query.format_jsonl(rows) if args.jsonl else query.format_text(conn, rows))
    return 0


def cmd_stats(args) -> int:
    conn = _connect(args)
    print(json.dumps(query.stats(conn), indent=2))
    return 0


def cmd_reindex(args) -> int:
    conn = _connect(args)
    print(f"reindexed {db.rebuild_fts(conn)} message(s)")
    return 0


def _add_global_args(parser, *, defaults: bool) -> None:
    """Accept --archive/-v on both sides of the subcommand.

    On the subparsers the defaults are suppressed, so an option given before the
    subcommand is not silently overwritten by the subparser's own default.
    """
    parser.add_argument(
        "--archive",
        type=Path,
        default=DEFAULT_ARCHIVE if defaults else argparse.SUPPRESS,
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        default=False if defaults else argparse.SUPPRESS,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="discord_archive", description=__doc__)
    _add_global_args(parser, defaults=True)

    common = argparse.ArgumentParser(add_help=False)
    _add_global_args(common, defaults=False)

    subparsers = parser.add_subparsers(dest="command", required=True)

    def sub_add(name, **kwargs):
        return subparsers.add_parser(name, parents=[common], **kwargs)

    def add_ingest_args(p):
        p.add_argument("--drop", type=Path, default=DEFAULT_DROP)
        p.add_argument("--force", action="store_true", help="re-read unchanged files")

    def add_extract_args(p):
        p.add_argument("--batch", type=int, default=250, help="new messages per call")
        p.add_argument("--context", type=int, default=30, help="overlap messages")
        p.add_argument(
            "--effort", default="high", choices=["low", "medium", "high", "xhigh", "max"]
        )
        p.add_argument("--dry-run", action="store_true", help="build prompts, send none")

    def add_publish_args(p):
        p.add_argument("--feed", type=Path, default=DEFAULT_FEED)
        p.add_argument("--limit", type=int, default=200, help="threads in the feed")
        p.add_argument("--max-messages", type=int, default=40, help="per thread")
        p.add_argument("--site-repo", type=Path, default=DEFAULT_SITE)
        p.add_argument(
            "--deploy",
            action="store_true",
            help="commit, push and deploy the site (publishes to the public web)",
        )

    p = sub_add("ingest", help="read exports from the drop directory")
    add_ingest_args(p)
    p.set_defaults(func=cmd_ingest)

    p = sub_add("extract", help="turn unseen messages into threads")
    add_extract_args(p)
    p.set_defaults(func=cmd_extract)

    p = sub_add("publish", help="write the site's feed bundle")
    add_publish_args(p)
    p.set_defaults(func=cmd_publish)

    p = sub_add("poll", help="ingest, extract and publish in order")
    add_ingest_args(p)
    add_extract_args(p)
    add_publish_args(p)
    p.set_defaults(func=cmd_poll)

    p = sub_add("query", help="search the raw archive")
    p.add_argument("--preset", choices=filters.available())
    p.add_argument("--contains", help="raw FTS5 MATCH expression")
    p.add_argument("--regex", help="post-filter matched rows")
    p.add_argument("--channel")
    p.add_argument("--author")
    p.add_argument("--since", help="ISO date or timestamp")
    p.add_argument("--until")
    p.add_argument("--pinned", action="store_true")
    p.add_argument("--no-bots", action="store_true")
    p.add_argument("--limit", type=int, default=100)
    p.add_argument("--jsonl", action="store_true")
    p.set_defaults(func=cmd_query)

    p = sub_add("stats", help="counts, coverage and token spend")
    p.set_defaults(func=cmd_stats)

    p = sub_add("reindex", help="rebuild the full-text index")
    p.set_defaults(func=cmd_reindex)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
