"""SQLite store for the Discord archive.

The archive is lossless on purpose. Filtering is a query-time decision, so
every message keeps its original JSON in `messages.raw` alongside the parsed
columns -- a filter written six weeks from now can still reach anything the
exporter recorded, including fields this schema never bothered to promote.

Dedup is on the Discord snowflake, which is globally unique and stable. That
matters because exports overlap heavily: re-exporting a channel to pick up the
last two days re-delivers everything before it, and the same message arriving a
second time must update the row rather than double it. Edits are the reason the
conflict clause writes rather than ignores -- a message whose `content` changed
after the previous export should land as its current text.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS guilds (
    id          TEXT PRIMARY KEY,
    name        TEXT
);

CREATE TABLE IF NOT EXISTS channels (
    id          TEXT PRIMARY KEY,
    guild_id    TEXT,
    category    TEXT,
    name        TEXT,
    topic       TEXT
);

CREATE TABLE IF NOT EXISTS messages (
    id               TEXT PRIMARY KEY,
    channel_id       TEXT NOT NULL,
    guild_id         TEXT,
    author_id        TEXT,
    author_name      TEXT,
    author_nick      TEXT,
    author_is_bot    INTEGER NOT NULL DEFAULT 0,
    timestamp        TEXT NOT NULL,
    timestamp_edited TEXT,
    kind             TEXT,
    is_pinned        INTEGER NOT NULL DEFAULT 0,
    content          TEXT NOT NULL DEFAULT '',
    reply_to         TEXT,
    attachments      TEXT NOT NULL DEFAULT '[]',
    embeds           TEXT NOT NULL DEFAULT '[]',
    reactions        TEXT NOT NULL DEFAULT '[]',
    mentions         TEXT NOT NULL DEFAULT '[]',
    raw              TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_messages_ts      ON messages(timestamp);
CREATE INDEX IF NOT EXISTS idx_messages_channel ON messages(channel_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_messages_author  ON messages(author_name);

-- Standalone rather than external-content FTS. The content is small (Discord
-- text), and a standalone table cannot silently desynchronise from `messages`
-- the way a trigger-maintained external index can.
CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
    msg_id UNINDEXED,
    content
);

-- One row per export file actually read, so a re-run can skip files whose
-- bytes have not changed and `stats` can show where the archive came from.
CREATE TABLE IF NOT EXISTS ingests (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    path          TEXT NOT NULL,
    sha256        TEXT NOT NULL,
    ingested_at   TEXT NOT NULL,
    channel_id    TEXT,
    channel_name  TEXT,
    seen          INTEGER NOT NULL DEFAULT 0,
    inserted      INTEGER NOT NULL DEFAULT 0,
    updated       INTEGER NOT NULL DEFAULT 0
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_ingests_sha ON ingests(sha256);

-- Everything below is the derived layer: what the model made of the archive.
-- It is rebuildable. Dropping these tables and re-running the extractor costs
-- API calls but loses nothing, which is the property that makes it safe to
-- change the prompt or the schema and re-process history.

CREATE TABLE IF NOT EXISTS threads (
    id               TEXT PRIMARY KEY,
    channel_id       TEXT NOT NULL,
    title            TEXT NOT NULL,
    summary          TEXT NOT NULL DEFAULT '',
    topic            TEXT NOT NULL DEFAULT 'other',
    relevance        TEXT NOT NULL DEFAULT '',
    started_at       TEXT,
    last_activity_at TEXT,
    created_at       TEXT NOT NULL,
    updated_at       TEXT NOT NULL,
    model            TEXT
);

CREATE INDEX IF NOT EXISTS idx_threads_activity ON threads(last_activity_at DESC);

CREATE TABLE IF NOT EXISTS thread_messages (
    thread_id  TEXT NOT NULL,
    message_id TEXT NOT NULL,
    PRIMARY KEY (thread_id, message_id)
);

CREATE INDEX IF NOT EXISTS idx_thread_messages_msg ON thread_messages(message_id);

-- How far the extractor has read, per channel. Kept separate from the ingest
-- log because the two advance independently: re-reading an export does not
-- re-spend API calls, and re-running extraction does not re-read files.
CREATE TABLE IF NOT EXISTS watermarks (
    channel_id   TEXT PRIMARY KEY,
    timestamp    TEXT NOT NULL,
    message_id   TEXT,
    updated_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS extract_runs (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id         TEXT,
    started_at         TEXT NOT NULL,
    finished_at        TEXT,
    from_ts            TEXT,
    to_ts              TEXT,
    new_messages       INTEGER NOT NULL DEFAULT 0,
    context_messages   INTEGER NOT NULL DEFAULT 0,
    threads_touched    INTEGER NOT NULL DEFAULT 0,
    input_tokens       INTEGER,
    output_tokens      INTEGER,
    cache_read_tokens  INTEGER,
    model              TEXT,
    error              TEXT
);
"""

MESSAGE_COLUMNS = (
    "id", "channel_id", "guild_id", "author_id", "author_name", "author_nick",
    "author_is_bot", "timestamp", "timestamp_edited", "kind", "is_pinned",
    "content", "reply_to", "attachments", "embeds", "reactions", "mentions",
    "raw",
)


def connect(path: Path) -> sqlite3.Connection:
    """Open the archive, creating it and its schema if absent."""
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(SCHEMA)
    return conn


def upsert_guild(conn: sqlite3.Connection, guild: dict) -> None:
    if not guild.get("id"):
        return
    conn.execute(
        "INSERT INTO guilds (id, name) VALUES (?, ?) "
        "ON CONFLICT(id) DO UPDATE SET name=excluded.name",
        (str(guild["id"]), guild.get("name")),
    )


def upsert_channel(conn: sqlite3.Connection, channel: dict, guild_id: str | None) -> None:
    if not channel.get("id"):
        return
    conn.execute(
        "INSERT INTO channels (id, guild_id, category, name, topic) "
        "VALUES (?, ?, ?, ?, ?) "
        "ON CONFLICT(id) DO UPDATE SET "
        "  guild_id=COALESCE(excluded.guild_id, channels.guild_id),"
        "  category=COALESCE(excluded.category, channels.category),"
        "  name=COALESCE(excluded.name, channels.name),"
        "  topic=COALESCE(excluded.topic, channels.topic)",
        (
            str(channel["id"]),
            guild_id,
            channel.get("category"),
            channel.get("name"),
            channel.get("topic"),
        ),
    )


def upsert_message(conn: sqlite3.Connection, row: dict) -> str:
    """Insert or refresh one message. Returns 'inserted', 'updated' or 'same'.

    'same' is the common case on overlapping exports and is worth separating
    from 'updated' -- it is how you tell a redundant re-export from one that
    actually carried edits.
    """
    prior = conn.execute(
        "SELECT content, timestamp_edited, is_pinned, reactions FROM messages WHERE id = ?",
        (row["id"],),
    ).fetchone()

    conn.execute(
        f"INSERT INTO messages ({', '.join(MESSAGE_COLUMNS)}) "
        f"VALUES ({', '.join('?' * len(MESSAGE_COLUMNS))}) "
        "ON CONFLICT(id) DO UPDATE SET "
        + ", ".join(f"{c}=excluded.{c}" for c in MESSAGE_COLUMNS if c != "id"),
        tuple(row[c] for c in MESSAGE_COLUMNS),
    )

    if prior is None:
        _index(conn, row["id"], row["content"])
        return "inserted"

    changed = (
        prior["content"] != row["content"]
        or prior["timestamp_edited"] != row["timestamp_edited"]
        or prior["is_pinned"] != row["is_pinned"]
        or prior["reactions"] != row["reactions"]
    )
    if prior["content"] != row["content"]:
        _index(conn, row["id"], row["content"])
    return "updated" if changed else "same"


def _index(conn: sqlite3.Connection, msg_id: str, content: str) -> None:
    conn.execute("DELETE FROM messages_fts WHERE msg_id = ?", (msg_id,))
    conn.execute(
        "INSERT INTO messages_fts (msg_id, content) VALUES (?, ?)", (msg_id, content)
    )


def already_ingested(conn: sqlite3.Connection, sha: str) -> bool:
    return (
        conn.execute("SELECT 1 FROM ingests WHERE sha256 = ?", (sha,)).fetchone()
        is not None
    )


def record_ingest(conn: sqlite3.Connection, **fields) -> None:
    cols = ", ".join(fields)
    conn.execute(
        f"INSERT INTO ingests ({cols}) VALUES ({', '.join('?' * len(fields))}) "
        "ON CONFLICT(sha256) DO NOTHING",
        tuple(fields.values()),
    )


def rebuild_fts(conn: sqlite3.Connection) -> int:
    """Recreate the search index from `messages`.

    Only needed if the index is ever suspected of drifting, or after editing
    rows by hand. Returns the number of messages indexed.
    """
    conn.execute("DELETE FROM messages_fts")
    rows = conn.execute("SELECT id, content FROM messages").fetchall()
    conn.executemany(
        "INSERT INTO messages_fts (msg_id, content) VALUES (?, ?)",
        [(r["id"], r["content"]) for r in rows],
    )
    conn.commit()
    return len(rows)


def json_dump(value) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
