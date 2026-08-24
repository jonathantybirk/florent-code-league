"""Scrape the *whole* league match log, not just ours.

`florent-code-league-ci/tournament/live-cache.jsonl` is filtered by `teamIds=<us>`, so it can
only ever answer questions about our own matches. Team activity over time -- who was uploading
and playing, when, and how much -- needs the unfiltered feed.

    uv run python tools/league_census/scrape.py            # resume/extend the cache
    uv run python tools/league_census/scrape.py --full     # ignore the stop set, walk to the end

The log is append-only and ordered by completion time descending, so a warm run pages from the
newest match until it hits one already cached, and a cold run pages until the cursor runs out.
Both directions are needed: new matches land at the top, but a previous run may have been cut
short partway down, so the walk also continues past the oldest cached match.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

CACHE = Path(__file__).resolve().parent / "matches.jsonl"


def load(path: Path) -> dict[str, dict]:
    rows: dict[str, dict] = {}
    if path.exists():
        with open(path) as handle:
            for line in handle:
                line = line.strip()
                if line:
                    row = json.loads(line)
                    rows[row["id"]] = row
    return rows


def save(path: Path, rows: dict[str, dict]) -> None:
    ordered = sorted(rows.values(), key=lambda r: r.get("completedAt") or "", reverse=True)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w") as handle:
        for row in ordered:
            handle.write(json.dumps(row, separators=(",", ":")) + "\n")
    tmp.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache", type=Path, default=CACHE)
    parser.add_argument("--max-pages", type=int, default=100000)
    parser.add_argument("--full", action="store_true",
                        help="do not stop at the first known match; walk the entire log")
    parser.add_argument("--save-every", type=int, default=100, help="pages between checkpoints")
    args = parser.parse_args()

    from fcode.api import api_get

    rows = load(args.cache)
    known = set(rows)
    print(f"cache: {len(rows)} matches", file=sys.stderr)

    cursor: str | None = None
    added = 0
    started = time.time()
    for page_no in range(1, args.max_pages + 1):
        params = {"limit": "100"}
        if cursor:
            params["cursor"] = cursor
        for attempt in range(5):
            try:
                data = api_get("/api/matches", params)
                break
            except Exception as error:  # noqa: BLE001 -- the feed 5xxs under load
                print(f"  retry {attempt + 1}: {error}", file=sys.stderr)
                time.sleep(2 * (attempt + 1))
        else:
            print("giving up after five retries", file=sys.stderr)
            break

        page = data.get("matches", []) or []
        cursor = data.get("nextCursor")
        if not page:
            break

        fresh = [m for m in page if m["id"] not in known]
        for match in fresh:
            rows[match["id"]] = match
            known.add(match["id"])
        added += len(fresh)

        # A page entirely already-known means we have rejoined the cached run. Keep going only
        # when --full, or when the cache has a hole further down (unknown, so --full is the
        # honest way to close one).
        if not fresh and not args.full:
            print("reached cached matches", file=sys.stderr)
            break

        if page_no % args.save_every == 0:
            save(args.cache, rows)
            rate = page_no / max(time.time() - started, 1e-9)
            print(f"  page {page_no}: {len(rows)} cached, +{added}, "
                  f"oldest {page[-1].get('completedAt')}, {rate:.1f} pages/s", file=sys.stderr)
        if not cursor:
            print("end of log", file=sys.stderr)
            break

    save(args.cache, rows)
    print(f"done: {len(rows)} matches (+{added}) in {time.time() - started:.0f}s", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
