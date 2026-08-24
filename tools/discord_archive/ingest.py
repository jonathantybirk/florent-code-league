"""Read Discord exports out of a drop directory and into the archive.

The supported input is DiscordChatExporter's JSON format, which is the only
common export that carries *other people's* messages. Discord's own "Request my
Data" package is detected and rejected with an explanation rather than half
parsed: it contains solely the requesting account's own messages, so archiving
it would produce a store that looks populated but has none of the announcements
or opponent chatter the archive exists to hold.

Files are never moved or modified. A file is identified by the SHA-256 of its
bytes, so re-running over the same drop directory is cheap, and re-exporting a
channel with a wider date range is picked up as a new file whose overlapping
messages collapse onto the rows already present.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from . import db

DISCORD_EPOCH_MS = 1420070400000


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def normalise_ts(value: str | None) -> str | None:
    """Normalise an exporter timestamp to UTC ISO-8601, or None.

    DiscordChatExporter writes local time with an offset by default, so two
    exports taken in different timezones would otherwise sort against each
    other incorrectly.
    """
    if not value:
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def ts_from_snowflake(msg_id: str) -> str | None:
    """Recover a send time from the message ID when the field is missing."""
    try:
        ms = (int(msg_id) >> 22) + DISCORD_EPOCH_MS
    except (TypeError, ValueError):
        return None
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat()


def detect_format(payload) -> str:
    if isinstance(payload, dict) and "messages" in payload and "channel" in payload:
        return "dce"
    if isinstance(payload, list) and payload and isinstance(payload[0], dict):
        if {"ID", "Timestamp"} <= set(payload[0]):
            return "data-request"
    if isinstance(payload, dict) and "messages" in payload:
        return "dce"
    return "unknown"


def _author(msg: dict) -> dict:
    author = msg.get("author") or {}
    return {
        "author_id": str(author["id"]) if author.get("id") is not None else None,
        "author_name": author.get("name") or author.get("username"),
        "author_nick": author.get("nickname"),
        "author_is_bot": 1 if author.get("isBot") else 0,
    }


def _reply_to(msg: dict) -> str | None:
    ref = msg.get("reference") or {}
    value = ref.get("messageId") or ref.get("message_id")
    return str(value) if value else None


def to_row(msg: dict, channel_id: str, guild_id: str | None) -> dict | None:
    msg_id = msg.get("id")
    if msg_id is None:
        return None
    msg_id = str(msg_id)

    timestamp = normalise_ts(msg.get("timestamp")) or ts_from_snowflake(msg_id)
    if timestamp is None:
        return None

    row = {
        "id": msg_id,
        "channel_id": channel_id,
        "guild_id": guild_id,
        "timestamp": timestamp,
        "timestamp_edited": normalise_ts(msg.get("timestampEdited")),
        "kind": msg.get("type"),
        "is_pinned": 1 if msg.get("isPinned") else 0,
        "content": msg.get("content") or "",
        "reply_to": _reply_to(msg),
        "attachments": db.json_dump(msg.get("attachments") or []),
        "embeds": db.json_dump(msg.get("embeds") or []),
        "reactions": db.json_dump(msg.get("reactions") or []),
        "mentions": db.json_dump(msg.get("mentions") or []),
        "raw": db.json_dump(msg),
    }
    row.update(_author(msg))
    return row


def ingest_file(conn, path: Path, *, force: bool = False) -> dict:
    """Ingest one export file. Returns a per-file summary."""
    summary = {
        "path": str(path),
        "status": "ok",
        "seen": 0,
        "inserted": 0,
        "updated": 0,
        "same": 0,
    }

    digest = sha256(path)
    if not force and db.already_ingested(conn, digest):
        summary["status"] = "skipped (unchanged)"
        return summary

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        summary["status"] = f"skipped (not readable JSON: {exc})"
        return summary

    kind = detect_format(payload)
    if kind == "data-request":
        summary["status"] = (
            "skipped (Discord data-request package: contains only your own "
            "messages, not the channel)"
        )
        return summary
    if kind != "dce":
        summary["status"] = "skipped (unrecognised export format)"
        return summary

    guild = payload.get("guild") or {}
    channel = payload.get("channel") or {}
    guild_id = str(guild["id"]) if guild.get("id") is not None else None
    if channel.get("id") is None:
        summary["status"] = "skipped (export has no channel id)"
        return summary
    channel_id = str(channel["id"])

    db.upsert_guild(conn, guild)
    db.upsert_channel(conn, channel, guild_id)

    for msg in payload.get("messages") or []:
        row = to_row(msg, channel_id, guild_id)
        if row is None:
            continue
        summary["seen"] += 1
        summary[db.upsert_message(conn, row)] += 1

    db.record_ingest(
        conn,
        path=str(path),
        sha256=digest,
        ingested_at=datetime.now(timezone.utc).isoformat(),
        channel_id=channel_id,
        channel_name=channel.get("name"),
        seen=summary["seen"],
        inserted=summary["inserted"],
        updated=summary["updated"],
    )
    conn.commit()
    return summary


def ingest_dir(conn, drop: Path, *, force: bool = False) -> list[dict]:
    if not drop.exists():
        return []
    return [
        ingest_file(conn, path, force=force)
        for path in sorted(drop.rglob("*.json"))
    ]
