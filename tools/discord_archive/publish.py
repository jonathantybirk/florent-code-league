"""Render the extracted threads as the JSON bundle the site's feed page reads.

The shape mirrors `tournament/site_data.py`: a static JSON file under the site
repo's `public/`, fetched by the page at runtime. Nothing here talks to the
network -- writing the bundle and deploying the site are separate steps, so a
poll that produces no new threads changes no bytes and triggers no deploy.

Each message carries its own `url`, the canonical Discord deep link
(`/channels/<guild>/<channel>/<message>`), which opens the message in place in
the real client. The message text is included alongside it so the feed is
readable without leaving the page -- the link is for going back to the argument,
not for reading it in the first place.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

FEED_VERSION = 1


def message_url(guild_id: str | None, channel_id: str, message_id: str) -> str:
    # "@me" is what Discord itself uses when there is no guild (a DM export).
    return f"https://discord.com/channels/{guild_id or '@me'}/{channel_id}/{message_id}"


def build(conn, *, limit: int = 200, max_messages: int = 40) -> dict:
    """Assemble the feed bundle, newest thread first."""
    guild = conn.execute("SELECT id, name FROM guilds LIMIT 1").fetchone()
    guild_id = guild["id"] if guild else None

    threads = conn.execute(
        "SELECT t.*, c.name AS channel_name FROM threads t "
        "LEFT JOIN channels c ON c.id = t.channel_id "
        "ORDER BY t.last_activity_at DESC LIMIT ?",
        (limit,),
    ).fetchall()

    payload = []
    for thread in threads:
        rows = conn.execute(
            "SELECT m.* FROM thread_messages tm JOIN messages m ON m.id = tm.message_id "
            "WHERE tm.thread_id = ? ORDER BY m.timestamp, m.id",
            (thread["id"],),
        ).fetchall()
        if not rows:
            continue

        shown = rows[-max_messages:]
        payload.append(
            {
                "id": thread["id"],
                "title": thread["title"],
                "summary": thread["summary"],
                "topic": thread["topic"],
                "relevance": thread["relevance"],
                "started_at": thread["started_at"],
                "last_activity_at": thread["last_activity_at"],
                "channel": {
                    "id": thread["channel_id"],
                    "name": thread["channel_name"] or thread["channel_id"],
                },
                "message_count": len(rows),
                "truncated": len(shown) < len(rows),
                "messages": [
                    {
                        "id": row["id"],
                        "author": row["author_nick"] or row["author_name"] or "unknown",
                        "is_bot": bool(row["author_is_bot"]),
                        "timestamp": row["timestamp"],
                        "content": row["content"],
                        "attachments": len(json.loads(row["attachments"] or "[]")),
                        "url": message_url(guild_id, row["channel_id"], row["id"]),
                    }
                    for row in shown
                ],
            }
        )

    counts = {topic: 0 for topic in {t["topic"] for t in payload}} if payload else {}
    for thread in payload:
        counts[thread["topic"]] += 1

    return {
        "version": FEED_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "guild": {"id": guild_id, "name": guild["name"] if guild else None},
        "counts": {"threads": len(payload), "by_topic": counts},
        "threads": payload,
    }


def write(bundle: dict, output: Path) -> bool:
    """Write the bundle if it differs. Returns True when bytes changed.

    `generated_at` is excluded from the comparison on purpose: it changes on
    every run and would otherwise make every poll look like new content, which
    would in turn trigger a site deploy every two minutes for nothing.
    """
    output.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(bundle, ensure_ascii=False, indent=2, sort_keys=True) + "\n"

    if output.exists():
        try:
            previous = json.loads(output.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            previous = None
        if previous is not None:
            a = {k: v for k, v in previous.items() if k != "generated_at"}
            b = {k: v for k, v in bundle.items() if k != "generated_at"}
            if a == b:
                return False

    output.write_text(rendered, encoding="utf-8")
    return True


def deploy(site_repo: Path, feed: Path) -> bool:
    """Commit the feed and push the site live. Returns True if anything shipped.

    Deliberately mirrors `tournament/automation.py::_publish` -- same repo, same
    build, same wrangler deploy -- so the feed reaches the site the same way the
    ladder already does. Only the feed path is staged, so a concurrent edit
    elsewhere in the site repo is neither committed nor destroyed.
    """
    import subprocess

    def run(*args: str) -> str:
        return subprocess.run(
            args, cwd=site_repo, check=True, capture_output=True, text=True
        ).stdout

    relative = feed.resolve().relative_to(site_repo.resolve())
    run("git", "add", str(relative))

    staged = subprocess.run(
        ["git", "diff", "--cached", "--quiet", "--", str(relative)], cwd=site_repo
    )
    if staged.returncode == 0:
        return False

    run("git", "commit", "-m", "Update Discord league feed")
    run("git", "push", "origin", "main")
    run("npm", "run", "build")
    run("npm", "exec", "--yes", "wrangler@latest", "--", "deploy")
    return True
