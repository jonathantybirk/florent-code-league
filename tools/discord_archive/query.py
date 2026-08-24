"""Ad-hoc search over the raw archive, independent of what the model extracted.

The model's threads are an opinion about the messages; this is the messages. It
exists so a question the extractor was never prompted for -- every mention of a
constant, everything one person said in a week -- can still be answered without
re-running anything or paying for a single token.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone

from . import filters


def search(
    conn,
    *,
    preset: str | None = None,
    contains: str | None = None,
    regex: str | None = None,
    channel: str | None = None,
    author: str | None = None,
    since: str | None = None,
    until: str | None = None,
    pinned: bool = False,
    include_bots: bool = True,
    limit: int = 100,
) -> list:
    where, params = [], []

    if preset or contains:
        expression = contains if contains else filters.fts_query(preset)
        where.append(
            "id IN (SELECT msg_id FROM messages_fts WHERE messages_fts MATCH ?)"
        )
        params.append(expression)

    if channel:
        where.append(
            "channel_id IN (SELECT id FROM channels WHERE name LIKE ? OR id = ?)"
        )
        params.extend([f"%{channel}%", channel])
    if author:
        where.append("(author_name LIKE ? OR author_nick LIKE ?)")
        params.extend([f"%{author}%", f"%{author}%"])
    if since:
        where.append("timestamp >= ?")
        params.append(since)
    if until:
        where.append("timestamp <= ?")
        params.append(until)
    if pinned:
        where.append("is_pinned = 1")
    if not include_bots:
        where.append("author_is_bot = 0")

    clause = f"WHERE {' AND '.join(where)}" if where else ""
    rows = conn.execute(
        f"SELECT * FROM messages {clause} ORDER BY timestamp DESC LIMIT ?",
        (*params, limit),
    ).fetchall()

    if regex:
        pattern = re.compile(regex, re.IGNORECASE)
        rows = [row for row in rows if pattern.search(row["content"] or "")]
    return rows


def format_text(conn, rows) -> str:
    names = {
        row["id"]: row["name"]
        for row in conn.execute("SELECT id, name FROM channels").fetchall()
    }
    lines = []
    for row in reversed(rows):
        stamp = (row["timestamp"] or "")[:16].replace("T", " ")
        channel = names.get(row["channel_id"]) or row["channel_id"]
        author = row["author_nick"] or row["author_name"] or "unknown"
        lines.append(f"{stamp}  #{channel}  {author}: {row['content']}")
    return "\n".join(lines)


def format_jsonl(rows) -> str:
    return "\n".join(
        json.dumps(
            {key: row[key] for key in row.keys() if key != "raw"}, ensure_ascii=False
        )
        for row in rows
    )


def stats(conn) -> dict:
    def scalar(sql, *params):
        row = conn.execute(sql, params).fetchone()
        return row[0] if row else None

    return {
        "messages": scalar("SELECT COUNT(*) FROM messages"),
        "channels": scalar("SELECT COUNT(*) FROM channels"),
        "authors": scalar("SELECT COUNT(DISTINCT author_id) FROM messages"),
        "earliest": scalar("SELECT MIN(timestamp) FROM messages"),
        "latest": scalar("SELECT MAX(timestamp) FROM messages"),
        "exports_ingested": scalar("SELECT COUNT(*) FROM ingests"),
        "threads": scalar("SELECT COUNT(*) FROM threads"),
        "extracted_messages": scalar(
            "SELECT COUNT(DISTINCT message_id) FROM thread_messages"
        ),
        "unprocessed": scalar(
            "SELECT COUNT(*) FROM messages m LEFT JOIN watermarks w"
            " ON w.channel_id = m.channel_id"
            " WHERE w.timestamp IS NULL OR m.timestamp > w.timestamp"
        ),
        "extract_runs": scalar("SELECT COUNT(*) FROM extract_runs"),
        "extract_errors": scalar(
            "SELECT COUNT(*) FROM extract_runs WHERE error IS NOT NULL"
        ),
        "tokens_in": scalar("SELECT SUM(input_tokens) FROM extract_runs"),
        "tokens_out": scalar("SELECT SUM(output_tokens) FROM extract_runs"),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
